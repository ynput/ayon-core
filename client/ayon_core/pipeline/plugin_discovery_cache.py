"""Per-process cache for plugin discovery (publish + creator).

This module supports C1 (publisher plugin discovery performance). Cache entries
are **per Python process** only: separate DCC host launches do not share state.

**Scope of cache validity**

- **Per-process only:** each launched DCC is a new interpreter; there is no
  cross-app sharing. The win is *open Publisher twice in the same session*.
- **Same process, different paths or registrations** (e.g. project switch):
  keys differ; entries coexist. An LRU cap per namespace bounds memory.
- **Plugin authors:** set ``AYON_DISABLE_PLUGIN_DISCOVERY_CACHE=1`` for
  unconditional miss. In-place ``.py`` edits invalidate via directory mtime /
  file count; in-process ``register_plugin`` / ``register_creator_plugin``
  changes invalidate via ``id(...)`` in the cache key.
- **Symlink farms:** ``os.scandir`` may follow links; mtime semantics follow
  the resolved target. Prefer the opt-out if your layout is exotic.

Env:

- ``AYON_DISABLE_PLUGIN_DISCOVERY_CACHE`` — if set to a non-empty value that
  is not ``0`` or ``false`` (case-insensitive), cache is off.
- ``AYON_PLUGIN_DISCOVERY_CACHE_MAX`` — max entries per namespace (default 16).
  Unparseable values are ignored (default used).
"""
from __future__ import annotations

import os
from collections import OrderedDict
from typing import Any, Iterable, Optional

_DEFAULT_MAX_ENTRIES = 16

_stores: dict[str, OrderedDict[tuple, Any]] = {}


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


def lookup(namespace: str, key: tuple) -> Any:
    """Return cached value or None."""
    if cache_disabled():
        return None
    store = _stores.setdefault(namespace, OrderedDict())
    if key not in store:
        return None
    store.move_to_end(key)
    return store[key]


def store(namespace: str, key: tuple, value: Any) -> None:
    """Insert or update; evict oldest when over cap (LRU on access)."""
    if cache_disabled():
        return
    cap = max_entries()
    store = _stores.setdefault(namespace, OrderedDict())
    store[key] = value
    store.move_to_end(key)
    while len(store) > cap:
        store.popitem(last=False)


def clear(namespace: Optional[str] = None) -> None:
    """Drop cache entries; one namespace or all."""
    if namespace is None:
        _stores.clear()
    elif namespace in _stores:
        _stores[namespace].clear()
