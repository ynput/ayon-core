"""Tests for the shared addons manager in 'ayon_core.addon.base'."""
from __future__ import annotations

import threading

import pytest

from ayon_core.addon import base


@pytest.fixture
def init_calls(monkeypatch):
    """Reset the shared manager and count addons initializations."""
    monkeypatch.setattr(base._AddonsManagerCache, "manager", None)
    monkeypatch.setattr(base._AddonsManagerCache, "initializing", None)

    calls = []

    def _initialize_addons(self):
        calls.append(self)

    monkeypatch.setattr(
        base.AddonsManager, "initialize_addons", _initialize_addons
    )
    monkeypatch.setattr(
        base.AddonsManager, "connect_addons", lambda self: None
    )
    return calls


@pytest.mark.unit
def test_returns_same_manager(init_calls):
    manager = base.get_addons_manager()

    assert base.get_addons_manager() is manager
    assert len(init_calls) == 1


@pytest.mark.unit
def test_initialized_once_across_threads(init_calls, monkeypatch):
    release = threading.Event()

    def _slow_initialize_addons(self):
        # Hold the first initialization so other threads have to wait
        release.wait(5)
        init_calls.append(self)

    monkeypatch.setattr(
        base.AddonsManager, "initialize_addons", _slow_initialize_addons
    )

    results = []

    def _worker():
        results.append(base.get_addons_manager())

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    release.set()
    for thread in threads:
        thread.join(5)

    assert len(init_calls) == 1
    assert len(results) == 8
    assert all(result is init_calls[0] for result in results)


@pytest.mark.unit
def test_reentrant_call_returns_manager_being_initialized(
    init_calls, monkeypatch
):
    nested = []

    def _initialize_addons(self):
        # E.g. an addon asking for the manager from its 'initialize'
        nested.append(base.get_addons_manager())
        init_calls.append(self)

    monkeypatch.setattr(
        base.AddonsManager, "initialize_addons", _initialize_addons
    )

    manager = base.get_addons_manager()

    assert nested == [manager]
    assert len(init_calls) == 1


@pytest.mark.unit
def test_failed_initialization_is_not_cached(init_calls, monkeypatch):
    def _failing_initialize_addons(self):
        raise RuntimeError("Server not available")

    monkeypatch.setattr(
        base.AddonsManager, "initialize_addons", _failing_initialize_addons
    )
    with pytest.raises(RuntimeError):
        base.get_addons_manager()

    assert base._AddonsManagerCache.manager is None
    assert base._AddonsManagerCache.initializing is None

    # Next call tries again
    monkeypatch.setattr(
        base.AddonsManager,
        "initialize_addons",
        lambda self: init_calls.append(self),
    )
    manager = base.get_addons_manager()
    assert init_calls == [manager]
