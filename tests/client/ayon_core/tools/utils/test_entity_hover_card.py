"""Tests for hover card of folders and tasks."""

from __future__ import annotations

import threading
from dataclasses import dataclass

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.utils import entity_hover_card
from ayon_core.tools.utils.entity_hover_card import (
    FACT_COLUMNS,
    MAX_FACT_ROWS,
    MAX_FACT_ROWS_WITH_DESCRIPTION,
    EntityHoverCard,
    EntityHoverCardHandler,
    EntityHoverFact,
    EntityHoverInfo,
    get_folder_hover_info,
    get_task_hover_info,
)
from ayon_core.ui.components.task_queue import shutdown_task_queue

ENTITY_ID_ROLE = QtCore.Qt.UserRole + 1


@dataclass
class _TypeItem:
    name: str
    icon: str


@dataclass
class _StatusItem:
    name: str
    short: str
    icon: str
    color: str


@pytest.fixture
def task_queue(qapp):
    # Avatars of users are loaded using the task queue
    yield
    shutdown_task_queue()


def _folder_entity(**attrib):
    return {
        "id": "folder-1",
        "name": "sh010",
        "label": None,
        "folderType": "Shot",
        "path": "/shots/sq01/sh010",
        "status": "In progress",
        "tags": ["hero", "fx"],
        "attrib": attrib,
    }


def _task_entity(assignees, **attrib):
    return {
        "id": "task-1",
        "name": "anim",
        "label": "Animation",
        "taskType": "Animation",
        "status": "In progress",
        "tags": [],
        "assignees": assignees,
        "attrib": attrib,
    }


def _info(description="", facts_count=8):
    return EntityHoverInfo(
        label="sh010",
        type_name="Shot",
        type_icon="movie",
        parents=["shots", "sq01"],
        description=description,
        facts=[
            EntityHoverFact("timer", f"Fact {idx}")
            for idx in range(facts_count)
        ],
    )


def test_folder_info_starts_with_frames_and_fps():
    info = get_folder_hover_info(
        "demo",
        _folder_entity(
            frameStart=1001,
            frameEnd=1050,
            fps=24.0,
            resolutionWidth=1920,
            resolutionHeight=1080,
            description="Hero shot",
        ),
        _TypeItem("Shot", "movie"),
        _StatusItem("In progress", "PRG", "play_arrow", "#5bb8f5"),
        "/path/to/thumbnail.jpg",
    )

    assert info.label == "sh010"
    assert info.type_icon == "movie"
    assert info.parents == ["shots", "sq01"]
    assert info.description == "Hero shot"
    assert info.thumbnail_path == "/path/to/thumbnail.jpg"
    assert [fact.text for fact in info.facts] == [
        "1001-1050 (50f)",
        "24 fps",
        "In progress",
        "hero, fx",
        "1920x1080",
    ]
    # Status fact uses icon and color of the status
    assert info.facts[2].icon == "play_arrow"
    assert info.facts[2].color == "#5bb8f5"


def test_folder_info_of_top_folder_without_items():
    folder_entity = _folder_entity()
    folder_entity["path"] = "/assets"
    folder_entity["tags"] = []

    info = get_folder_hover_info("demo", folder_entity)

    # Project is used when the folder does not have parents
    assert info.parents == ["demo"]
    assert info.type_icon == "folder"
    assert info.thumbnail_path == ""
    assert info.facts == []


def test_task_info_has_assignee_with_avatar(monkeypatch):
    monkeypatch.setattr(
        entity_hover_card,
        "_get_user_full_names",
        lambda usernames: [name.title() for name in usernames],
    )

    info = get_task_hover_info(
        "demo",
        _task_entity(
            ["john", "jane"],
            frameStart=1001,
            frameEnd=1010,
            fps=25.0,
            priority="urgent",
        ),
        "/shots/sq01/sh010",
        _TypeItem("Animation", "directions_run"),
        _StatusItem("In progress", "PRG", "play_arrow", "#5bb8f5"),
    )

    assert info.label == "Animation"
    assert info.parents == ["shots", "sq01", "sh010"]
    assert [fact.text for fact in info.facts] == [
        "1001-1010 (10f)",
        "25 fps",
        "John +1",
        "In progress",
        "Urgent",
    ]
    assignee_fact = info.facts[2]
    assert assignee_fact.username == "john"
    assert assignee_fact.user_full_name == "John"


def test_card_shows_less_facts_with_description(qtbot, task_queue):
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    card = EntityHoverCard(parent)

    card.set_info(_info())
    labels = [
        label for label in card._fact_labels if not label.isHidden()
    ]
    assert len(labels) == FACT_COLUMNS * MAX_FACT_ROWS
    assert card._description_widget.isHidden()

    card.set_info(_info("Short description"))
    labels = [
        label for label in card._fact_labels if not label.isHidden()
    ]
    assert len(labels) == FACT_COLUMNS * MAX_FACT_ROWS_WITH_DESCRIPTION
    assert not card._description_widget.isHidden()


def test_card_height_follows_description(qtbot, task_queue):
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    card = EntityHoverCard(parent)

    card.set_info(_info("Short description", facts_count=4))
    short_height = card.height()
    assert len(card._description_widget._lines) == 1

    card.set_info(_info("Long description of the shot. " * 30, 4))
    long_height = card.height()
    lines = card._description_widget._lines
    assert len(lines) == entity_hover_card.DESCRIPTION_LINES
    assert lines[-1].endswith("…")
    assert long_height > short_height

    # The card gets smaller again
    card.set_info(_info("Short description", facts_count=4))
    assert card.height() == short_height


def test_card_shows_avatar_of_user(qtbot, task_queue):
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)
    card = EntityHoverCard(parent)
    info = _info(facts_count=0)
    info.facts = [
        EntityHoverFact(
            "person", "John Doe", username="john", user_full_name="John Doe"
        ),
    ]
    requested = []
    pixmap = QtGui.QPixmap(16, 16)
    pixmap.fill(QtGui.QColor("red"))
    card._avatar_cache.pixmap = (
        lambda *args: requested.append(args) or pixmap
    )

    card.set_info(info)

    assert requested == [
        ("john", "John Doe", entity_hover_card.AVATAR_SIZE)
    ]
    # Avatar is loaded again when it was downloaded
    card._on_avatar_updated("other")
    assert len(requested) == 1
    card._on_avatar_updated("john")
    assert len(requested) == 2


def _create_view(qtbot):
    window = QtWidgets.QWidget()
    qtbot.addWidget(window)
    view = QtWidgets.QTreeView(window)
    model = QtGui.QStandardItemModel()
    for entity_id in ("a", "b"):
        item = QtGui.QStandardItem(entity_id)
        item.setData(entity_id, ENTITY_ID_ROLE)
        model.appendRow(item)
    view.setModel(model)
    # Window must be referenced, otherwise it is deleted with the view
    return window, view, model


def test_handler_loads_info_in_thread_once(qtbot, task_queue):
    _window, view, model = _create_view(qtbot)
    calls = []

    def _getter(entity_id):
        calls.append((entity_id, threading.get_ident()))
        return _info()

    handler = EntityHoverCardHandler(view, ENTITY_ID_ROLE, _getter)
    index = model.index(0, 0)

    assert not handler.show_for_index(index)

    view.entered.emit(index)
    qtbot.waitUntil(lambda: "a" in handler._info_by_id, timeout=5000)
    assert calls[0][0] == "a"
    assert calls[0][1] != threading.get_ident()

    # Entering the item again does not load the information again
    view.viewportEntered.emit()
    view.entered.emit(index)
    qtbot.wait(entity_hover_card.FETCH_DELAY * 3)
    assert len(calls) == 1

    assert handler.show_for_index(index)
    assert handler._card.isVisible()
    handler.reset_hover()
    assert not handler._card.isVisible()


def test_handler_clear_cache_ignores_running_task(qtbot, task_queue):
    _window, view, model = _create_view(qtbot)
    blocker = threading.Event()
    calls = []

    def _getter(entity_id):
        calls.append(entity_id)
        blocker.wait(10)
        return _info()

    handler = EntityHoverCardHandler(view, ENTITY_ID_ROLE, _getter)
    view.entered.emit(model.index(0, 0))
    qtbot.waitUntil(lambda: calls == ["a"], timeout=5000)

    handler.clear_cache()
    blocker.set()
    qtbot.waitUntil(lambda: not handler._tasks, timeout=5000)

    assert handler._info_by_id == {}
