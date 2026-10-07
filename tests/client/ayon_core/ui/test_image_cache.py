"""Tests for ImageCache (SQLite backend)."""

from __future__ import annotations

import multiprocessing
import sqlite3
import threading
import time
from pathlib import Path
from typing import Iterator

import pytest

from ayon_core.ui.image_cache import ImageCache, _DB_FILENAME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source_file(directory: Path, name: str = "src.png") -> Path:
    """Write a tiny source image file and return its path."""
    p = directory / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)
    return p


def _fresh_cache(tmp_path: Path, max_mb: int = 10) -> ImageCache:
    """Create an ImageCache instance that bypasses the singleton."""
    instance = object.__new__(ImageCache)
    instance._initialize(tmp_path, max_mb)
    return instance


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def src_dir(tmp_path: Path) -> Path:
    d = tmp_path / "sources"
    d.mkdir()
    return d


@pytest.fixture
def cache(cache_dir: Path) -> Iterator[ImageCache]:
    ic = _fresh_cache(cache_dir)
    yield ic
    ic._close_all_connections()


# ---------------------------------------------------------------------------
# Basic get() behaviour
# ---------------------------------------------------------------------------


def test_get_cache_miss(cache: ImageCache, src_dir: Path) -> None:
    """file_closure is called on miss; file lands in cache; DB has an entry."""
    src = _make_source_file(src_dir)
    calls: list[int] = []

    def closure() -> Path:
        calls.append(1)
        return src

    result = cache.get("key1", closure)

    assert len(calls) == 1
    assert Path(result).exists()
    row = (
        cache._get_conn()
        .execute("SELECT file_path FROM cache WHERE key = ?", ("key1",))
        .fetchone()
    )
    assert row is not None
    assert Path(row[0]) == Path(result)


def test_get_cache_hit(cache: ImageCache, src_dir: Path) -> None:
    """Second get() for the same key does NOT call file_closure again."""
    src = _make_source_file(src_dir)
    calls: list[int] = []

    def closure() -> Path:
        calls.append(1)
        return src

    first = cache.get("key1", closure)
    second = cache.get("key1", closure)

    assert len(calls) == 1
    assert first == second


def test_get_missing_file_reloads(cache: ImageCache, src_dir: Path) -> None:
    """If the cached file is deleted from disk, get() re-caches it."""
    src = _make_source_file(src_dir)
    calls: list[int] = []

    def closure() -> Path:
        calls.append(1)
        return src

    first = cache.get("key1", closure)
    Path(first).unlink()

    second = cache.get("key1", closure)

    assert len(calls) == 2
    assert Path(second).exists()


# ---------------------------------------------------------------------------
# has()
# ---------------------------------------------------------------------------


def test_has_returns_true(cache: ImageCache, src_dir: Path) -> None:
    src = _make_source_file(src_dir)
    cache.get("key1", lambda: src)
    assert cache.has("key1") is True


def test_has_returns_false(cache: ImageCache) -> None:
    assert cache.has("nonexistent") is False


def test_has_missing_file(cache: ImageCache, src_dir: Path) -> None:
    src = _make_source_file(src_dir)
    cached = cache.get("key1", lambda: src)
    Path(cached).unlink()
    assert cache.has("key1") is False


# ---------------------------------------------------------------------------
# get_path()
# ---------------------------------------------------------------------------


def test_get_path_returns_path(cache: ImageCache, src_dir: Path) -> None:
    src = _make_source_file(src_dir)
    cache.get("key1", lambda: src)

    before = (
        cache._get_conn()
        .execute("SELECT access_count FROM cache WHERE key = ?", ("key1",))
        .fetchone()[0]
    )

    result = cache.get_path("key1")

    after = (
        cache._get_conn()
        .execute("SELECT access_count FROM cache WHERE key = ?", ("key1",))
        .fetchone()[0]
    )

    assert result is not None
    assert Path(result).exists()
    assert after == before + 1


def test_get_path_returns_none(cache: ImageCache) -> None:
    assert cache.get_path("nonexistent") is None


# ---------------------------------------------------------------------------
# Eviction
# ---------------------------------------------------------------------------


def test_eviction_lru(cache_dir: Path, src_dir: Path) -> None:
    """Oldest-accessed entries are evicted first when the cache is full."""
    # 1 MB max; each fake file is ~600 KB → two fit, third triggers eviction
    ic = _fresh_cache(cache_dir, max_mb=1)
    try:
        chunk = b"\x00" * (600 * 1024)

        def make_src(name: str) -> Path:
            p = src_dir / name
            p.write_bytes(chunk)
            return p

        # key_a is accessed earliest
        src_a = make_src("a.bin")
        src_b = make_src("b.bin")
        src_c = make_src("c.bin")

        ic.get("key_a", lambda: src_a)
        time.sleep(0.01)
        ic.get("key_b", lambda: src_b)
        time.sleep(0.01)
        # Adding key_c pushes total > 1 MB → key_a should be evicted
        ic.get("key_c", lambda: src_c)

        assert not ic.has("key_a"), "key_a should have been evicted"
        assert ic.has("key_b") or ic.has("key_c"), (
            "At least one recent entry must survive"
        )
    finally:
        ic._close_all_connections()


# ---------------------------------------------------------------------------
# _validate_cache_files()
# ---------------------------------------------------------------------------


def test_validate_cache_files(cache_dir: Path, src_dir: Path) -> None:
    """Startup validation removes DB rows whose files are gone."""
    ic = _fresh_cache(cache_dir)
    src = _make_source_file(src_dir)
    cached = ic.get("key1", lambda: src)
    ic._close_all_connections()

    # Delete the file while the cache is "down"
    Path(cached).unlink()

    # Re-open — _validate_cache_files() runs in _initialize()
    ic2 = _fresh_cache(cache_dir)
    try:
        row = (
            ic2._get_conn()
            .execute("SELECT key FROM cache WHERE key = ?", ("key1",))
            .fetchone()
        )
        assert row is None
    finally:
        ic2._close_all_connections()


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_empty_key_raises(cache: ImageCache) -> None:
    with pytest.raises(ValueError, match="empty"):
        cache.get("", lambda: Path("/nonexistent"))


def test_invalid_closure_raises(cache: ImageCache) -> None:
    with pytest.raises(ValueError, match="non-existent"):
        cache.get("key1", lambda: Path("/does/not/exist.png"))


# ---------------------------------------------------------------------------
# Atomic file write
# ---------------------------------------------------------------------------


def test_atomic_file_write(cache: ImageCache, src_dir: Path) -> None:
    """Cached file must be complete (not a partial write)."""
    content = b"\x89PNG\r\n\x1a\n" + b"\xab" * 1024
    src = src_dir / "real.png"
    src.write_bytes(content)

    result = cache.get("key1", lambda: src)

    assert Path(result).read_bytes() == content


# ---------------------------------------------------------------------------
# Thread safety
# ---------------------------------------------------------------------------


def test_concurrent_threads(cache: ImageCache, src_dir: Path) -> None:
    """Multiple threads calling get() simultaneously must not corrupt
    the DB."""
    src = _make_source_file(src_dir)
    results: list[str] = []
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        try:
            path = cache.get(f"key{idx % 3}", lambda: src)
            results.append(path)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread errors: {errors}"
    assert len(results) == 20
    # DB must be consistent — no duplicate keys
    rows = cache._get_conn().execute("SELECT key FROM cache").fetchall()
    keys = [r[0] for r in rows]
    assert len(keys) == len(set(keys))


# ---------------------------------------------------------------------------
# Legacy JSON cleanup
# ---------------------------------------------------------------------------


def test_legacy_json_cleanup(cache_dir: Path) -> None:
    """Old cache_metadata.json (and .lock) are deleted on initialisation."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    legacy_json = cache_dir / "cache_metadata.json"
    legacy_lock = cache_dir / "cache_metadata.json.lock"
    legacy_json.write_text('{"old": "data"}')
    legacy_lock.write_text("")

    ic = _fresh_cache(cache_dir)
    try:
        assert not legacy_json.exists()
        assert not legacy_lock.exists()
    finally:
        ic._close_all_connections()


# ---------------------------------------------------------------------------
# Concurrent processes
# ---------------------------------------------------------------------------


def _worker_process(cache_dir: str, key: str, src_file: str) -> None:
    """Target function for subprocess workers."""
    ic = _fresh_cache(Path(cache_dir))
    ic.get(key, lambda: Path(src_file))
    ic._close_all_connections()


def test_concurrent_processes(cache_dir: Path, src_dir: Path) -> None:
    """Multiple processes writing to the same cache must leave a valid DB."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    src = _make_source_file(src_dir)

    procs = [
        multiprocessing.Process(
            target=_worker_process,
            args=(str(cache_dir), f"proc_key_{i}", str(src)),
        )
        for i in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)

    for p in procs:
        assert p.exitcode == 0, f"Process exited with {p.exitcode}"

    # Verify DB integrity after all processes have written
    conn = sqlite3.connect(str(cache_dir / "cache_metadata.db"))
    try:
        rows = conn.execute("SELECT key FROM cache").fetchall()
        keys = [r[0] for r in rows]
        assert len(keys) == len(set(keys)), "Duplicate keys in DB"
        assert len(keys) == 4, f"Expected 4 entries, got {len(keys)}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# test AYON_IMG_CACHE_CLEAR_ON_STARTUP
# ---------------------------------------------------------------------------


def test_clear_on_startup(cache_dir: Path, src_dir: Path) -> None:
    """If AYON_IMG_CACHE_CLEAR_ON_STARTUP is set, cache files are deleted
    on init."""
    # Create some dummy cache files
    for i in range(5):
        _make_source_file(src_dir, name=f"src_{i}.png")

    # Set the environment variable and re-initialize the cache
    import os

    os.environ["AYON_IMG_CACHE_CLEAR_ON_STARTUP"] = "1"
    ic = _fresh_cache(cache_dir)
    try:
        # Only the DB file should remain
        remaining_files = list(cache_dir.iterdir())
        assert all(_DB_FILENAME in f.name for f in remaining_files), (
            f"Unexpected files in cache: {remaining_files}. "
            f"Only {_DB_FILENAME}[-wal, -shm] should remain after clear "
            "on startup"
        )
    finally:
        ic._close_all_connections()
