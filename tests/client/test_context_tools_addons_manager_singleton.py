"""Unit-test lazy singleton locking without real AddonsManager / AYON server."""

from __future__ import annotations

import threading

import pytest


def test_get_addons_manager_constructs_once_under_contention(monkeypatch):
    """Concurrent first callers must take the lock exactly once for construction."""
    from ayon_core.pipeline import context_tools as ct

    ct._addons_manager = None
    constructed = {"count": 0}
    sentinel = object()

    class _FakeManager:
        def __init__(self, *args, **kwargs):
            constructed["count"] += 1

    monkeypatch.setattr(ct, "AddonsManager", _FakeManager)

    n = 24
    barrier = threading.Barrier(n)
    refs: list[object] = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        m = ct._get_addons_manager()
        with lock:
            refs.append(m)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert constructed["count"] == 1
    first = refs[0]
    assert all(m is first for m in refs)

    # force=True rebuild under same lock (no torn read)
    ct._addons_manager = sentinel
    rebuilt = ct._get_addons_manager(force=True)
    assert rebuilt is not sentinel
    assert isinstance(rebuilt, _FakeManager)
    assert constructed["count"] == 2
    assert ct._get_addons_manager() is rebuilt
