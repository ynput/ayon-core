"""Per-process cache for plugin discovery (publish + creator).

This module supports C1 (publisher plugin discovery performance). Cache entries
are **per Python process** only: separate DCC host launches do not share state.

**Cheap key vs fingerprint**

Lookups use a **cheap key** (no I/O): ``(frozenset(normalized_paths),
tuple(id(...) for registered plugins/classes))``. Each stored entry also keeps the
full **fingerprint** from :func:`fingerprint_paths` (``os.scandir`` per plugin
root). On a cheap-key hit, we recompute the fingerprint once and compare to
the stored tuple — same correctness as embedding the fingerprint in the lookup
key, but **cold misses** no longer run :func:`fingerprint_paths` before
discovery (avoids double directory work).

**Scope of cache validity**

- **Per-process only:** each launched DCC is a new interpreter; there is no
  cross-app sharing. The win is *open Publisher twice in the same session*.
- **Same process, different paths/registrations** (e.g. project switch):
  keys differ; entries coexist. An LRU cap per namespace bounds memory.
- **Plugin authors:** set ``AYON_DISABLE_PLUGIN_DISCOVERY_CACHE=1`` for
  unconditional miss. In-place ``.py`` edits invalidate via directory mtime /
  file count; in-process ``register_plugin`` / ``register_creator_plugin``
  changes invalidate via ``id(...)`` in the cheap key.
- **Symlink farms:** ``os.scandir`` may follow links; mtime semantics follow
  the resolved target. Prefer the opt-out if your layout is exotic.

Optional future **Phase 2** (not implemented): env-gated ``stat``-only quick
validation to skip full ``scandir`` on some hits — platform caveats; see
roadmap / perf notes.

Env:

- ``AYON_DISABLE_PLUGIN_DISCOVERY_CACHE`` — if set to a non-empty value that
  is not ``0`` or ``false`` (case-insensitive), cache is off.
- ``AYON_PLUGIN_DISCOVERY_CACHE_MAX`` — max entries per namespace (default 16).
  Unparseable values are ignored (default used).
"""
from __future__ import annotations

import os
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Iterable, Optional

_DEFAULT_MAX_ENTRIES = 16

# Per-namespace LRU: cheap_key -> CacheEntry
_stores: dict[str, OrderedDict[tuple, "CacheEntry"]] = {}


@dataclass
class CacheEntry:
    """Stored discovery result and the fingerprint taken after discovery."""

    fingerprint: tuple[tuple[str, int, int], ...]
    value: Any


def cache_disabled() -> bool:
    raw = os.environ.get("AYON_DISABLE_PLUGIN_DISCOVERY_CACHE")
    if raw is None or raw == "":
        return False
    lowered = raw.strip().lower()
    if lowered in {"0", "false", "no"}:
        return False
    return True


def max_entries() -> int:
    raw = os.environ.get("AYON_PLUGIN_DISCOVERY_CACHE_MAX")
    if raw is None or raw == "":
        return _DEFAULT_MAX_ENTRIES
    try:
        return max(1, int(raw.strip()))
    except ValueError:
        return _DEFAULT_MAX_ENTRIES


def fingerprint_paths(paths: Iterable[str]) -> tuple[tuple[str, int, int], ...]:
    """Return sorted fingerprint rows: (norm_dir, max_mtime_ns, py_count)."""
    rows: list[tuple[str, int, int]] = []
    for raw in paths:
        path = os.path.normpath(raw)
        if os.path.isdir(path):
            base_dir = path
            max_ns = 0
            count = 0
            try:
                with os.scandir(base_dir) as it:
                    for ent in it:
                        if not ent.is_file():
                            continue
                        name = ent.name
                        if name.startswith("_"):
                            continue
                        if not name.lower().endswith(".py"):
                            continue
                        count += 1
                        try:
                            st = ent.stat()
                            max_ns = max(max_ns, st.st_mtime_ns)
                        except OSError:
                            pass
            except OSError:
                rows.append((base_dir, 0, 0))
                continue
            rows.append((base_dir, max_ns, count))
        elif os.path.isfile(path):
            base_dir = os.path.dirname(path)
            name = os.path.basename(path)
            if (
                name.startswith("_")
                or not name.lower().endswith(".py")
            ):
                rows.append((base_dir, 0, 0))
                continue
            try:
                st = os.stat(path)
                rows.append((base_dir, st.st_mtime_ns, 1))
            except OSError:
                rows.append((base_dir, 0, 0))
        else:
            rows.append((path, 0, 0))

    rows.sort(key=lambda r: r[0])
    return tuple(rows)


def lookup_validate(
    namespace: str,
    cheap_key: tuple,
    paths: Iterable[str],
) -> Any | None:
    """Return cached value if cheap key hits and fingerprint still matches.

    If the cheap key exists but the filesystem fingerprint changed, the stale
    entry is removed and ``None`` is returned.
    """
    if cache_disabled():
        return None
    store = _stores.setdefault(namespace, OrderedDict())
    entry = store.get(cheap_key)
    if entry is None:
        return None
    fp_new = fingerprint_paths(paths)
    if fp_new == entry.fingerprint:
        store.move_to_end(cheap_key)
        return entry.value
    del store[cheap_key]
    return None


def store_after_discovery(
    namespace: str,
    cheap_key: tuple,
    paths: Iterable[str],
    value: Any,
) -> None:
    """Store value with fingerprint computed once after discovery."""
    if cache_disabled():
        return
    fp = fingerprint_paths(paths)
    entry = CacheEntry(fingerprint=fp, value=value)
    cap = max_entries()
    store = _stores.setdefault(namespace, OrderedDict())
    store[cheap_key] = entry
    store.move_to_end(cheap_key)
    while len(store) > cap:
        store.popitem(last=False)


def clear(namespace: Optional[str] = None) -> None:
    """Drop cache entries; one namespace or all."""
    if namespace is None:
        _stores.clear()
    elif namespace in _stores:
        _stores[namespace].clear()
