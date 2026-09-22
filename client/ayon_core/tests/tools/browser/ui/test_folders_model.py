"""Loading and incremental refresh of the browser folders model."""

from __future__ import annotations

import sys
import types

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

import pytest
from qtpy import QtCore

from ayon_core.tools.common_models.hierarchy import FolderItem
from ayon_core.tools.browser.ui import folders_model
from ayon_core.tools.browser.ui.folders_model import (
    FOLDER_ID_ROLE,
    FOLDER_PATH_FILTER_ROLE,
    BrowserFoldersModel,
    BrowserFoldersProxyModel,
)


class _TaskQueue:
    """Collects tasks instead of running them in worker threads."""
    def __init__(self):
        self.tasks = []

    def enqueue(self, task):
        self.tasks.append(task)


@pytest.fixture(autouse=True)
def task_queue(qapp, monkeypatch):
    queue = _TaskQueue()
    monkeypatch.setattr(folders_model, "get_task_queue", lambda: queue)
    return queue


def _folder(folder_id, parent_id, label, path):
    return FolderItem(
        entity_id=folder_id,
        parent_id=parent_id,
        name=label.lower(),
        path=path,
        folder_type="Folder",
        label=label,
        status="Not ready",
    )


def _base_folders():
    folders = [
        _folder("assets", None, "Assets", "/assets"),
        _folder("char", "assets", "Characters", "/assets/char"),
        _folder("hero", "char", "Hero", "/assets/char/hero"),
        _folder("shots", None, "Shots", "/shots"),
        _folder("sh010", "shots", "sh010", "/shots/sh010"),
    ]
    return {folder.entity_id: folder for folder in folders}


class _Controller:
    def __init__(self, folder_items):
        self.folder_items = folder_items

    def get_folder_items(self, project_name, sender=None):
        return self.folder_items

    def get_folder_type_items(self, project_name, sender=None):
        return []

    def get_project_status_items(self, project_name, sender=None):
        return []


class _UiController:
    current_project = "demo"


def _load(model):
    """Run what 'reset' does, synchronously."""
    model.reset()
    task = model._pending_task
    model._on_data_fetched(model._generation, task.function())


def _tree(model, parent=QtCore.QModelIndex()):
    output = {}
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        output[index.data()] = _tree(model, index)
    return output


def _create_model(folder_items):
    controller = _Controller(folder_items)
    model = BrowserFoldersModel(_UiController(), controller)
    return model, controller


def test_initial_load_builds_hierarchy():
    model, _ = _create_model(_base_folders())
    loading = []
    model.loading_changed.connect(loading.append)

    _load(model)

    assert _tree(model) == {
        "Assets": {"Characters": {"Hero": {}}},
        "Shots": {"sh010": {}},
    }
    assert loading == [True, False]
    assert not model.is_loading()
    index = model.get_index_by_id("hero")
    assert index.data(FOLDER_ID_ROLE) == "hero"
    assert index.data(FOLDER_PATH_FILTER_ROLE) == (
        "/assets/char/hero /assets/characters/hero"
    )
    status_index = index.sibling(index.row(), 1)
    assert status_index.data(QtCore.Qt.ToolTipRole) == "Not ready"


def test_refresh_applies_changes_in_place():
    model, controller = _create_model(_base_folders())
    _load(model)
    resets = []
    model.modelReset.connect(lambda: resets.append(True))
    hero_item = model._items_by_id["hero"]

    folders = _base_folders()
    # rename parent -> child filter path changes too
    char = folders["char"]
    folders["char"] = _folder("char", "assets", "Chars", char.path)
    # move shot under assets, add new folder and remove one
    folders["sh010"] = _folder("sh010", "assets", "sh010", "/assets/sh010")
    folders["props"] = _folder("props", "assets", "Props", "/assets/props")
    folders["sh020"] = _folder("sh020", "props", "sh020", "/assets/p/sh")
    folders.pop("shots")
    controller.folder_items = folders

    _load(model)

    assert not resets
    assert _tree(model) == {
        "Assets": {
            "Chars": {"Hero": {}},
            "sh010": {},
            "Props": {"sh020": {}},
        },
    }
    # Existing items are kept
    assert model._items_by_id["hero"] is hero_item
    assert "shots" not in model._items_by_id
    assert model.get_index_by_id("hero").data(FOLDER_PATH_FILTER_ROLE) == (
        "/assets/char/hero /assets/chars/hero"
    )


def test_refresh_without_changes_does_nothing():
    model, _ = _create_model(_base_folders())
    _load(model)
    signals = []
    model.modelReset.connect(lambda: signals.append("reset"))
    model.rowsInserted.connect(lambda *_: signals.append("inserted"))
    model.dataChanged.connect(lambda *_: signals.append("changed"))

    _load(model)

    assert signals == []


def test_outdated_result_is_ignored():
    model, controller = _create_model(_base_folders())
    model.reset()
    old_task = model._pending_task
    old_result = old_task.function()

    controller.folder_items = {
        "shots": _folder("shots", None, "Shots", "/shots"),
    }
    model.reset()
    new_task = model._pending_task
    assert old_task.is_cancelled()

    model._on_data_fetched(model._generation - 1, old_result)
    assert model.rowCount() == 0
    assert model.is_loading()

    model._on_data_fetched(model._generation, new_task.function())
    assert _tree(model) == {"Shots": {}}
    assert not model.is_loading()


def test_proxy_sorts_and_filters():
    model, _ = _create_model(_base_folders())
    proxy = BrowserFoldersProxyModel()
    proxy.setSourceModel(model)
    proxy.sort(0, QtCore.Qt.DescendingOrder)
    _load(model)

    assert [
        proxy.index(row, 0).data() for row in range(proxy.rowCount())
    ] == ["Shots", "Assets"]

    proxy.set_name_filter("characters")
    assert _tree(proxy) == {"Assets": {"Characters": {"Hero": {}}}}
