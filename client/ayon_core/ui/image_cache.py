from __future__ import annotations

import atexit
import hashlib
import logging
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import weakref
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

_DB_FILENAME = "cache_metadata.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache (
    key           TEXT PRIMARY KEY,
    file_path     TEXT NOT NULL,
    size_bytes    INTEGER NOT NULL,
    access_count  INTEGER DEFAULT 1,
    last_accessed REAL NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache(last_accessed);
"""


def _parse_positive_int(value: int | str, label: str) -> int:
    """Parse and validate a positive integer value.

    Args:
        value: The value to parse.
        label: Human-readable name for error messages.

    Returns:
        The parsed positive integer.

    Raises:
        ValueError: If *value* cannot be parsed or is not positive.
    """
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{label} must be a positive integer, got {value!r}"
        ) from exc
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer, got {value!r}")
    return result


class ImageCache:
    """Process- and thread-safe LRU image cache backed by SQLite.

    Stores image files on disk and tracks metadata in a SQLite database.
    Eviction is based on least-recently-used (LRU) access time.

    Concurrency model:
        - Each thread gets its own ``sqlite3.Connection`` via
          ``threading.local()``.  SQLite WAL journal mode allows multiple
          readers to proceed concurrently across both threads and OS processes;
          writers are serialised by SQLite's internal file-level locking, with
          a 10-second busy-timeout handling contention.
        - Cache-miss work (calling *file_closure* and copying the file) is
          serialised **per cache key** via a per-key ``threading.Lock``.
          Threads requesting different keys proceed fully in parallel; threads
          requesting the same key during a miss wait for exactly one download
          to complete and then read the already-populated entry.

    Environment variables:
        AYON_IMG_CACHE_DIR: Parent directory for the AYON_IMG_CACHE folder.
                            Defaults to the system temp directory.
        AYON_IMG_CACHE_SIZE: Override default cache size in MB.
        AYON_IMG_CACHE_CLEAR_ON_STARTUP: Clear all cache files on startup.

    Attributes:
        cache_path (Path): Directory where cached files are stored.
        max_size_in_MB (int): Maximum cache size in megabytes.
        max_size_bytes (int): Maximum cache size in bytes.
    """

    _instance: ImageCache | None = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(
        cls,
        cache_path: str | Path | None = None,
        max_size_in_MB: int = 500,
    ) -> ImageCache:
        """Return the singleton cache instance, creating it if needed.

        NOTE: `cache_path` and `max_size_in_MB` are only used on the first
              call. Subsequent calls return the same instance regardless of
              the arguments.

        Args:
            cache_path: Directory path for storing cached files.
            max_size_in_MB: Maximum cache size in megabytes.

        Returns:
            The singleton ImageCache instance.

        Raises:
            ValueError: If max_size_in_MB is not positive.
        """
        with cls._lock:
            if cls._instance is not None:
                return cls._instance
            if max_size_in_MB <= 0:
                raise ValueError("max_size_in_MB must be positive")
            instance = object.__new__(cls)
            instance._initialize(cache_path, max_size_in_MB)
            cls._instance = instance
            return cls._instance

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    @staticmethod
    def _check_sqlite_version() -> None:
        """Raise RuntimeError if the runtime SQLite is too old.

        WAL journal mode requires SQLite ≥ 3.7.0 (released 2010).  Any
        reasonably modern Python 3 installation satisfies this requirement,
        but distributions that link CPython against a very old system SQLite
        could fail at the PRAGMA call without a clear error message.  This
        check surfaces the problem at initialisation time.

        Raises:
            RuntimeError: If the runtime SQLite version is below 3.7.0.
        """
        min_version = (3, 7, 0)
        if sqlite3.sqlite_version_info < min_version:
            raise RuntimeError(
                "ImageCache requires SQLite >= "
                f"{'.'.join(map(str, min_version))};"
                f" found {sqlite3.sqlite_version}"
            )

    def _get_tmp_dir(self) -> Path:
        tmp = Path(os.environ.get("AYON_IMG_CACHE_DIR", tempfile.gettempdir()))
        tmp = tmp / "AYON_IMG_CACHE"
        tmp.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(tmp, 0o700)
        logger.info(f"AYON image cache: {tmp} ({self.max_size_in_MB} MB)")
        return tmp

    def _initialize(
        self,
        cache_path: str | Path | None,
        max_size_in_MB: int,
    ) -> None:
        """Initialise the cache instance.

        Args:
            cache_path: Directory path for storing cached files.
            max_size_in_MB: Maximum cache size in megabytes.
        """
        self._check_sqlite_version()

        raw = os.environ.get("AYON_IMG_CACHE_SIZE")
        if raw is not None:
            self.max_size_in_MB = _parse_positive_int(
                raw, "AYON_IMG_CACHE_SIZE"
            )
        else:
            self.max_size_in_MB = _parse_positive_int(
                max_size_in_MB, "max_size_in_MB"
            )
        self.max_size_bytes = self.max_size_in_MB * 1024 * 1024

        self.cache_path = (
            Path(cache_path) if cache_path else self._get_tmp_dir()
        )
        self.cache_path.mkdir(parents=True, exist_ok=True)

        self._db_path = self.cache_path / _DB_FILENAME

        # Per-thread connection storage.
        self._local = threading.local()

        # Guards both _key_locks and _all_connections.
        self._meta_lock = threading.Lock()

        # Per-key locks that serialise cache-miss work for the same key.
        # WeakValueDictionary ensures locks are garbage-collected once no
        # thread holds a reference, preventing unbounded growth.
        self._key_locks: weakref.WeakValueDictionary[str, threading.Lock] = (
            weakref.WeakValueDictionary()
        )

        # Registry of every connection ever opened so they can all be
        # closed at process exit.
        self._all_connections: list[sqlite3.Connection] = []

        # Initialise the schema using the calling thread's connection.
        setup_conn = self._get_conn()
        self._set_wal_mode(setup_conn)
        setup_conn.execute(_CREATE_TABLE_SQL)
        setup_conn.execute(_CREATE_INDEX_SQL)
        setup_conn.commit()

        if "AYON_IMG_CACHE_CLEAR_ON_STARTUP" in os.environ:
            self._clear_all_files()

        self._validate_cache_files()
        self._cleanup_legacy_files()

        atexit.register(self._close_all_connections)

    def _clear_all_files(self) -> None:
        """Delete every file in the cache directory and reset the DB."""
        conn = self._get_conn()
        count = 0
        for entry in os.scandir(self.cache_path):
            if entry.is_file() and entry.name != self._db_path.name:
                if _DB_FILENAME in entry.path:
                    continue
                try:
                    os.remove(entry.path)
                    count += 1
                except OSError as exc:
                    logger.warning(f"Could not remove {entry.path}: {exc}")
        conn.execute("DELETE FROM cache")
        conn.commit()
        logger.info(f"AYON image cache: cleared ({count} files removed)")

    def _cleanup_legacy_files(self) -> None:
        """Remove legacy JSON metadata files left from the previous version."""
        for name in ("cache_metadata.json", "cache_metadata.json.lock"):
            legacy = self.cache_path / name
            if legacy.exists():
                try:
                    legacy.unlink()
                    logger.debug(f"Removed legacy cache file: {legacy}")
                except OSError as exc:
                    logger.warning(
                        f"Could not remove legacy file {legacy}: {exc}"
                    )

    def _set_wal_mode(
        self,
        conn: sqlite3.Connection,
        retries: int = 5,
        base_delay: float = 0.1,
    ) -> None:
        """Switch the database to WAL journal mode with retries.

        ``PRAGMA journal_mode=WAL`` requires an exclusive lock on the
        database file.  Under heavy concurrent process startup the lock
        may not be available even though ``busy_timeout`` is set, so we
        retry with linear back-off.

        Args:
            conn: The connection to use for setting WAL mode.
            retries: Maximum number of attempts.
            base_delay: Seconds to wait between attempts (multiplied
                by the attempt number).
        """
        for attempt in range(retries):
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError:
                if attempt == retries - 1:
                    raise
                time.sleep(base_delay * (attempt + 1))

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _open_connection(self) -> sqlite3.Connection:
        """Open and configure a new SQLite connection.

        WAL journal mode is **not** set here; it is a one-time,
        exclusive-lock operation performed during initialisation via
        ``_set_wal_mode``.  Once set, WAL mode is stored in the database
        file header and all subsequent connections inherit it automatically.

        Returns:
            A new ``sqlite3.Connection`` configured with busy_timeout.
        """
        return sqlite3.connect(str(self._db_path), timeout=10)

    def _get_conn(self) -> sqlite3.Connection:
        """Return the per-thread SQLite connection, creating it if needed.

        Each thread gets its own connection, which avoids the need for an
        application-level lock on reads.  New connections are registered in
        ``_all_connections`` so they can be closed at process exit.

        Returns:
            The ``sqlite3.Connection`` for the calling thread.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._open_connection()
            self._local.conn = conn
            with self._meta_lock:
                self._all_connections.append(conn)
        return conn

    def _close_all_connections(self) -> None:
        """Close every per-thread connection opened by this instance.

        Registered with ``atexit`` during initialisation.
        """
        with self._meta_lock:
            for conn in self._all_connections:
                try:
                    conn.close()
                except Exception:
                    logger.debug(
                        "Exception while closing cache DB connection",
                        exc_info=True,
                    )
            self._all_connections.clear()

    # ------------------------------------------------------------------
    # Per-key locking
    # ------------------------------------------------------------------

    def _get_key_lock(self, key: str) -> threading.Lock:
        """Return the per-key lock for *key*, creating it if needed.

        Args:
            key: The cache key.

        Returns:
            A ``threading.Lock`` dedicated to *key*.
        """
        with self._meta_lock:
            lock = self._key_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._key_locks[key] = lock
            return lock

    # ------------------------------------------------------------------
    # Internal DB helpers
    # ------------------------------------------------------------------

    def _lookup(self, key: str) -> Path | None:
        """Return the cached ``Path`` for *key* without updating metadata.

        Purges the DB row and returns ``None`` if the file is missing on disk.

        Args:
            key: The cache key to look up.

        Returns:
            Absolute ``Path`` to the cached file, or ``None`` on a miss.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT file_path FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        cached_path = Path(row[0])
        if cached_path.exists():
            return cached_path
        logger.debug(f"Cached file missing for key '{key}': purging row")
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        return None

    def _touch(self, key: str) -> None:
        """Increment the access counter and refresh last_accessed for *key*.

        This is a best-effort metadata update for LRU ordering.  If the row
        has been removed between a preceding ``_lookup`` and this call (e.g.
        by a concurrent eviction), the ``UPDATE`` matches zero rows and is
        silently discarded — LRU accuracy is not required to be exact.

        Args:
            key: The cache key to update.
        """
        conn = self._get_conn()
        conn.execute(
            "UPDATE cache "
            "SET access_count = access_count + 1, last_accessed = ? "
            "WHERE key = ?",
            (time.time(), key),
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, file_closure: Callable) -> str:
        """Return the cached file path for *key*, caching it if necessary.

        Cache hits are served via a fast path that requires no application-
        level locking; SQLite WAL mode allows concurrent reads across threads
        and processes.

        On a cache miss, a per-key lock is acquired so that only one thread
        calls *file_closure* for a given key at a time.  After acquiring the
        lock the database is re-checked: if another thread already populated
        the entry the result is returned immediately without calling the
        closure again.

        *file_closure* is called **outside** any database transaction, so a
        slow I/O operation (e.g. a network download) does not block threads
        that are requesting different keys.

        Args:
            key: Unique identifier for the cached file.
            file_closure: Callable returning the path to the source file.
                          Called only on a cache miss.

        Returns:
            Absolute path to the cached file as a string.

        Raises:
            ValueError: If *key* is empty or *file_closure* returns a path
                        that does not exist.
            IOError: If the file cannot be copied into the cache.
        """
        if not key:
            raise ValueError("Cache key cannot be empty")

        # ------------------------------------------------------------------
        # ------------------------------------------------------------------
        # Fast path: pure SELECT — concurrent reads across threads/processes
        # proceed without blocking each other in WAL mode.  _touch is a
        # separate best-effort write; LRU accuracy does not need to be exact.
        # ------------------------------------------------------------------
        cached_path = self._lookup(key)
        if cached_path is not None:
            self._touch(key)
            logger.debug(f"Cache hit for key '{key}'")
            return str(cached_path)

        # ------------------------------------------------------------------
        # Slow path: acquire the per-key lock, then double-check.
        # Only threads requesting the same key are serialised here; threads
        # requesting different keys proceed fully in parallel.
        # ------------------------------------------------------------------
        with self._get_key_lock(key):
            # Double-check: another thread may have populated the entry
            # while we were waiting for the key lock.
            cached_path = self._lookup(key)
            if cached_path is not None:
                self._touch(key)
                logger.debug(f"Cache hit for key '{key}' (after key lock)")
                return str(cached_path)

            # True miss: call the closure outside any database transaction.
            logger.debug(f"Cache miss for key '{key}', calling file_closure")
            source_path = Path(file_closure())

            if not source_path.exists():
                raise ValueError(
                    f"Loader returned non-existent file: {source_path}"
                )

            cache_filename = self._generate_cache_filename(key, source_path)
            cached_path = self.cache_path / cache_filename

            self._atomic_copy(source_path, cached_path)

            conn = self._get_conn()
            file_size = cached_path.stat().st_size
            conn.execute(
                "INSERT OR REPLACE INTO cache "
                "(key, file_path, size_bytes, access_count, last_accessed) "
                "VALUES (?, ?, ?, 1, ?)",
                (key, str(cached_path), file_size, time.time()),
            )
            conn.commit()

        # Eviction runs outside the per-key lock: it can be slow (file I/O +
        # bulk DB DELETE) and must not block other threads querying this key.
        self._evict_if_needed()

        logger.debug(f"Cached file for key '{key}': {cached_path}")
        return str(cached_path)

    def has(self, key: str) -> bool:
        """Return True if *key* is cached and its file exists on disk.

        Args:
            key: Cache key to check.

        Returns:
            True if the key is present and the file exists, else False.
        """
        return self._lookup(key) is not None

    def get_path(self, key: str) -> str | None:
        """Return the cached file path for *key* if it exists, else None.

        Updates access metadata when the entry is found.

        Args:
            key: Cache key to look up.

        Returns:
            Absolute path string to the cached file, or None.
        """
        cached_path = self._lookup(key)
        if cached_path is None:
            return None
        self._touch(key)
        return str(cached_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _atomic_copy(self, src: Path, dst: Path) -> None:
        """Copy *src* to *dst* atomically using a temp file + os.replace().

        The temporary file is created in the same directory as *dst* so that
        ``os.replace`` is an atomic rename on the same filesystem.

        Args:
            src: Source file path.
            dst: Destination file path.

        Raises:
            IOError: If the copy or rename fails.
        """
        fd, tmp_name = tempfile.mkstemp(dir=self.cache_path, suffix=".tmp")
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            shutil.copy2(src, tmp_path)
            os.replace(tmp_path, dst)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise IOError(f"Failed to cache file: {exc}") from exc

    def set_path(self, key: str, file_path: str) -> Path:
        """Manually set a cache entry for a given key and file path."""
        with self._access_lock:
            source_path = Path(file_path)
            if not source_path.exists():
                raise ValueError(
                    f"Provided file does not exist: {source_path}"
                )

            cache_filename = self._generate_cache_filename(key, source_path)
            cached_path = self.cache_path / cache_filename

            try:
                with open(source_path, "rb") as src:
                    with open(cached_path, "wb") as dst:
                        dst.write(src.read())
            except IOError as e:
                raise IOError(f"Failed to set cache file: {e}") from e

            file_size = cached_path.stat().st_size
            self._metadata[key] = {
                "file_path": str(cached_path),
                "size_bytes": file_size,
                "access_count": 0,
                "last_accessed": time.time(),
            }
            self._evict_if_needed()
            return cached_path

    def _generate_cache_filename(self, key: str, source_path: Path) -> str:
        """Build a cache filename from a SHA-256 hash of *key*.

        Args:
            key: The cache key.
            source_path: The original file (used only to preserve extension).

        Returns:
            Filename string with the original extension.
        """
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        extension = source_path.suffix
        return f"{key_hash}{extension}"

    def _evict_if_needed(self) -> None:
        """Evict LRU entries until cache size is at 90 % of the limit."""
        conn = self._get_conn()
        current_size = self._get_cache_size()

        if current_size <= self.max_size_bytes:
            return

        target_size = int(self.max_size_bytes * 0.9)
        logger.info(
            f"Cache size ({current_size} bytes) exceeds limit "
            f"({self.max_size_bytes} bytes). Evicting to {target_size} bytes"
        )

        rows = conn.execute(
            "SELECT key, file_path, size_bytes FROM cache ORDER BY "
            "last_accessed ASC"
        ).fetchall()

        keys_to_delete: list[str] = []
        for evict_key, file_path_str, size_bytes in rows:
            if current_size <= target_size:
                break
            # Acquire the per-key lock non-blocking: skip keys that are
            # currently being served by another thread so we do not delete
            # a file that a concurrent get() is about to return.
            key_lock = self._get_key_lock(evict_key)
            if not key_lock.acquire(blocking=False):
                logger.debug(
                    f"Skipping eviction of key '{evict_key}' "
                    "(lock held by another thread)"
                )
                continue
            try:
                file_path = Path(file_path_str)
                if file_path.exists():
                    file_path.unlink()
                current_size -= size_bytes
                keys_to_delete.append(evict_key)
                logger.debug(f"Evicted cache entry for key '{evict_key}'")
            except OSError as exc:
                logger.warning(f"Failed to delete cache file: {exc}")
            finally:
                key_lock.release()

        if keys_to_delete:
            placeholders = ",".join("?" * len(keys_to_delete))
            conn.execute(
                f"DELETE FROM cache WHERE key IN ({placeholders})",
                keys_to_delete,
            )
            conn.commit()

    def _get_cache_size(self) -> int:
        """Return the total size of all cached entries in bytes.

        Returns:
            Total bytes recorded in the database.
        """
        conn = self._get_conn()
        row = conn.execute(
            "SELECT COALESCE(SUM(size_bytes), 0) FROM cache"
        ).fetchone()
        return int(row[0])

    def _validate_cache_files(self) -> None:
        """Remove DB entries whose files no longer exist on disk."""
        conn = self._get_conn()
        rows = conn.execute("SELECT key, file_path FROM cache").fetchall()

        invalid_keys = [key for key, fp in rows if not Path(fp).exists()]

        if not invalid_keys:
            return

        placeholders = ",".join("?" * len(invalid_keys))
        conn.execute(
            f"DELETE FROM cache WHERE key IN ({placeholders})",
            invalid_keys,
        )
        conn.commit()
        logger.debug(f"Removed {len(invalid_keys)} invalid cache entries")


def make_activity_cache_key(
    project_name: str,
    file_id: str,
    is_thumbnail: bool = False,
) -> str:
    """Build the ImageCache key for an activity-attached file.

    Both the producer (download enqueue) and the consumer (UI refresh)
    must use this function so that they always agree on the key, and so
    that entries from different projects never collide.

    Args:
        project_name: AYON project name that owns the file.
        file_id: The AYON file identifier.
        is_thumbnail: Whether the key is for the thumbnail variant.

    Returns:
        Cache key string in the form
        ``act_<project_name>_<file_id>`` or
        ``act_thumb_<project_name>_<file_id>``.
    """
    prefix = "thumb_" if is_thumbnail else ""
    return f"act_{prefix}{project_name}_{file_id}"
