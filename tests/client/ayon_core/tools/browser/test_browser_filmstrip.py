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
from ayon_core.ui.components.entity_card import AYEntityCard

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


@pytest.mark.unit
def test_card_filmstrip_follows_card(qapp, loads) -> None:
    project_name, _, version_id = KEYS[0]
    card = AYEntityCard(image_src=f"{project_name}/{version_id}/thumb")
    try:
        # Created only when asked for
        assert card.findChild(filmstrip.FilmstripOverlay) is None

        overlay = filmstrip.get_card_filmstrip(card)

        assert overlay is not None
        assert overlay._source == KEYS[0]
        assert filmstrip.get_card_filmstrip(card) is overlay

        # The card view updates cards to show another version
        card.image_src = f"{project_name}/{KEYS[1][2]}/thumb"
        assert filmstrip.get_card_filmstrip(card) is overlay
        assert overlay._source == KEYS[1]

        card.image_src = ""
        assert filmstrip.get_card_filmstrip(card) is None
    finally:
        card.deleteLater()


@pytest.mark.unit
def test_sweep_requests_only_the_hovered_filmstrip(
    qapp, loads, overlay
) -> None:
    """Sweeping the cursor over thumbnails does not flood the server.

    At most ``FILMSTRIP_WORKERS`` requests are sent at the same time, and
    the queued requests of thumbnails the cursor left are skipped.
    """
    assert filmstrip.FILMSTRIP_WORKERS == 2
    loader = filmstrip._get_loader()
    for idx, key in enumerate(KEYS):
        overlay.set_source(*key)
        overlay.scrub(0.5)
        # Hovered past the hover delay
        assert _spin(qapp, lambda: key in loader._requests)
        # The first requests occupy both workers
        expected = min(idx + 1, 2)
        assert _spin(qapp, lambda: len(loads.calls) >= expected)
    assert len(loader._requests) == len(KEYS)

    loads.release.set()

    assert _spin(qapp, lambda: not loader._requests)
    assert sorted(loads.calls[:2]) == KEYS[:2]
    assert loads.calls[2:] == [KEYS[-1]]
    # The answer is cached, hovering it again requests nothing
    overlay.stop()
    overlay.scrub(0.5)
    _spin(qapp, lambda: False, 0.1)
    assert len(loads.calls) == 3
