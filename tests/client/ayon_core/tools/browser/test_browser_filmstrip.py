"""Tests for the hover-scrub filmstrips of Browser thumbnails."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from types import SimpleNamespace
from typing import Callable

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.browser.ui import _browser_filmstrip as filmstrip

KEYS = [("project", "version", f"{idx:032x}") for idx in range(10)]


@pytest.fixture
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def loads(monkeypatch, qapp):
    """Record the filmstrips requested from the server.

    Uses a new loader and memory cache, filmstrips are enabled and loaded
    without the hover delay. Loads block until ``release`` is set.
    """
    calls: list[filmstrip._SourceKey] = []
    release = threading.Event()

    def _load(key):
        calls.append(key)
        release.wait(10)
        return None, filmstrip.DEFAULT_MAX_AGE

    monkeypatch.delenv("AYON_BROWSER_DISABLE_FILMSTRIPS", raising=False)
    monkeypatch.setattr(filmstrip, "server_supports_filmstrips", lambda: True)
    monkeypatch.setattr(filmstrip, "HOVER_INTENT_DELAY_MS", 0)
    monkeypatch.setattr(filmstrip, "_load_filmstrip", _load)
    monkeypatch.setattr(filmstrip, "_memory_cache", OrderedDict())
    monkeypatch.setattr(filmstrip, "_loader", None)
    yield SimpleNamespace(calls=calls, release=release)
    release.set()
    if filmstrip._loader is not None:
        filmstrip._loader._queue.stop()


def _spin(
    qapp: QtWidgets.QApplication,
    condition: Callable[[], bool],
    timeout: float = 5.0,
) -> bool:
    end = time.time() + timeout
    while not condition() and time.time() < end:
        qapp.processEvents(QtCore.QEventLoop.ProcessEventsFlag.AllEvents, 10)
        time.sleep(0.005)
    return condition()


@pytest.fixture
def overlay(qapp):
    """Overlay on a thumbnail widget."""
    host = QtWidgets.QWidget()
    host.resize(160, 90)
    yield filmstrip.FilmstripOverlay(host)
    host.deleteLater()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("disabled_env", "server_supported"),
    [
        pytest.param("1", True, id="disabled_by_env"),
        pytest.param(
            None, False, id="old_server",
            marks=pytest.mark.server_compat("1.17.2"),
        ),
    ],
)
def test_nothing_requested_when_disabled(
    qapp, loads, overlay, monkeypatch, disabled_env, server_supported
) -> None:
    if disabled_env is not None:
        monkeypatch.setenv("AYON_BROWSER_DISABLE_FILMSTRIPS", disabled_env)
    monkeypatch.setattr(
        filmstrip, "server_supports_filmstrips", lambda: server_supported
    )
    overlay.set_source(*KEYS[0])

    overlay.scrub(0.5)
    overlay.show_popup()
    _spin(qapp, lambda: False, 0.1)

    assert loads.calls == []
    assert not overlay.isVisible()


@pytest.mark.unit
def test_answers_without_filmstrip_stay_cached(qapp, monkeypatch) -> None:
    monkeypatch.setattr(filmstrip, "_memory_cache", OrderedDict())
    max_filmstrips = filmstrip.MAX_MEMORY_FILMSTRIPS
    image = QtGui.QImage(10, 10, QtGui.QImage.Format.Format_RGB32)
    without = [("project", "version", f"a{idx}") for idx in range(20)]
    with_filmstrip = [
        ("project", "version", f"b{idx}") for idx in range(max_filmstrips + 2)
    ]

    for key in without:
        filmstrip._store_filmstrip(key, None, filmstrip.DEFAULT_MAX_AGE)
    for key in with_filmstrip:
        data = filmstrip.FilmstripData("file", image, 20, 5)
        filmstrip._store_filmstrip(key, data, filmstrip.DEFAULT_MAX_AGE)

    assert all(filmstrip._peek_filmstrip(key) for key in without)
    cached = [key for key in with_filmstrip if filmstrip._peek_filmstrip(key)]
    assert cached == with_filmstrip[2:]
