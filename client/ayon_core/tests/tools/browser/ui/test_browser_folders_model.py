"""Tests for the Browser's standard-item folders model."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from qtpy import QtCore

from ayon_core.tools.browser.ui.folders_model import (
    FOLDER_ID_ROLE,
    FOLDER_PATH_FILTER_ROLE,
    FOLDER_TYPE_ROLE,
    BrowserFoldersModel,
    FetchData,
)
from ayon_core.tools.common_models import FolderItem, FolderTypeItem

PROJECT_NAME = "demo"


def _folder_items(
    folders: dict[str, tuple[str | None, str]],
    folder_types: dict[str, str] | None = None,
) -> dict[str, FolderItem]:
    """Build folder items from ``{id: (parent_id, label)}``."""
    folder_types = folder_types or {}
    paths: dict[str, str] = {}

    def _path(folder_id: str) -> str:
        if folder_id not in paths:
            parent_id = folders[folder_id][0]
            parent_path = _path(parent_id) if parent_id else ""
            paths[folder_id] = f"{parent_path}/{folder_id}"
        return paths[folder_id]

    return {
        folder_id: FolderItem(
            entity_id=folder_id,
            parent_id=parent_id,
            name=folder_id,
            path=_path(folder_id),
            folder_type=folder_types.get(folder_id, "Folder"),
            label=label,
            status="In progress",
        )
        for folder_id, (parent_id, label) in folders.items()
    }


def _model(qtbot) -> BrowserFoldersModel:
    ui_controller = Mock()
    ui_controller.current_project = PROJECT_NAME
    model = BrowserFoldersModel(ui_controller, Mock())
    model._last_project_name = PROJECT_NAME
    return model


def _fill(
    model: BrowserFoldersModel,
    folder_items: dict[str, FolderItem],
    project_name: str = PROJECT_NAME,
) -> None:
    folder_type_items = [
        FolderTypeItem(name=name, short=name[:2], icon="folder")
        for name in {item.folder_type for item in folder_items.values()}
    ]
    model._on_data_fetched(
        FetchData(
            project_name=project_name,
            folder_items_by_id=folder_items,
            folder_type_items=folder_type_items,
            status_items=[],
        )
    )


def _tree(model, parent=None) -> dict[str, dict]:
    """Return the model's hierarchy as nested ``{id: children}``."""
    parent = parent or QtCore.QModelIndex()
    result = {}
    for row in range(model.rowCount(parent)):
        index = model.index(row, 0, parent)
        result[index.data(FOLDER_ID_ROLE)] = _tree(model, index)
    return result


_HIERARCHY = {
    "assets": (None, "Assets"),
    "char": ("assets", "Characters"),
    "hero": ("char", "Hero"),
    "shots": (None, "Shots"),
}


def test_fill_builds_hierarchy_with_filter_text(qtbot):
    model = _model(qtbot)

    _fill(model, _folder_items(_HIERARCHY))

    assert _tree(model) == {
        "assets": {"char": {"hero": {}}},
        "shots": {},
    }
    hero = model.get_index_by_id("hero")
    # Both the name-based path and the label-based path are searchable.
    assert hero.data(FOLDER_PATH_FILTER_ROLE) == (
        "/assets/char/hero /assets/characters/hero"
    )


def test_update_keeps_existing_items(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))
    hero_item = model.itemFromIndex(model.get_index_by_id("hero"))
    resets = Mock()
    model.modelReset.connect(resets)

    _fill(model, _folder_items(_HIERARCHY))

    # Same item objects, no model reset - so the view keeps its
    # expanded and selected state.
    assert model.itemFromIndex(model.get_index_by_id("hero")) is hero_item
    resets.assert_not_called()


def test_update_removes_deleted_folders(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))
    hierarchy = dict(_HIERARCHY)
    del hierarchy["char"]
    del hierarchy["hero"]

    _fill(model, _folder_items(hierarchy))

    assert _tree(model) == {"assets": {}, "shots": {}}
    assert not model.get_index_by_id("hero").isValid()


def test_update_moves_folder_with_its_children(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))
    hero_item = model.itemFromIndex(model.get_index_by_id("hero"))
    hierarchy = dict(_HIERARCHY)
    hierarchy["char"] = ("shots", "Characters")

    _fill(model, _folder_items(hierarchy))

    assert _tree(model) == {
        "assets": {},
        "shots": {"char": {"hero": {}}},
    }
    assert model.itemFromIndex(model.get_index_by_id("hero")) is hero_item


def test_update_moves_folder_out_of_deleted_parent(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))
    hierarchy = dict(_HIERARCHY)
    del hierarchy["char"]
    hierarchy["hero"] = ("shots", "Hero")

    _fill(model, _folder_items(hierarchy))

    assert _tree(model) == {"assets": {}, "shots": {"hero": {}}}


def test_update_relabel_updates_display_and_filter_text(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))
    hierarchy = dict(_HIERARCHY)
    hierarchy["char"] = ("assets", "Characters v2")

    _fill(model, _folder_items(hierarchy))

    assert model.get_index_by_id("char").data() == "Characters v2"
    assert "characters v2" in model.get_index_by_id("hero").data(
        FOLDER_PATH_FILTER_ROLE
    )


def test_update_folder_type_change(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(
        _HIERARCHY, {"hero": "Asset", "shots": "Episode"}
    ))

    # Same set of project folder types, only the folder's own type
    # differs - so the folder must be detected as changed by itself.
    _fill(model, _folder_items(
        _HIERARCHY, {"hero": "Episode", "shots": "Asset"}
    ))

    hero = model.get_index_by_id("hero")
    assert hero.data(FOLDER_TYPE_ROLE) == "Episode"


def test_result_for_other_project_is_ignored(qtbot):
    model = _model(qtbot)
    _fill(model, _folder_items(_HIERARCHY))

    _fill(model, _folder_items({"other": (None, "Other")}), "other")

    assert "other" not in _tree(model)


def test_fill_emits_reset_finished(qtbot):
    model = _model(qtbot)
    finished = Mock()
    model.reset_finished.connect(finished)

    _fill(model, _folder_items(_HIERARCHY))

    finished.assert_called_once_with()
