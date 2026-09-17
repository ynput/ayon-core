"""Tests for the Browser slicer's single-query bulk hierarchy fetch and
the folder search filter text it builds.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.control import BrowserController
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
from ayon_core.tools.common_models.hierarchy import FolderItem


@pytest.fixture(autouse=True)
def _mock_addons_manager(monkeypatch):
    addon_manager = Mock()
    addon_manager.get_enabled_addons.return_value = []
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager",
        lambda: addon_manager,
    )


def _folder_item(entity_id, parent_id, name, label=None, path=None):
    label = label or name
    return FolderItem(
        entity_id=entity_id,
        parent_id=parent_id,
        name=name,
        path=path or f"/{name}",
        folder_type="Folder",
        label=label,
        status="in progress",
    )


_HIERARCHY = {
    "assets": _folder_item("assets", None, "assets", path="/assets"),
    "char": _folder_item(
        "char", "assets", "char", label="Characters",
        path="/assets/char",
    ),
    "hero": _folder_item(
        "hero", "char", "hero", label="Hero",
        path="/assets/char/hero",
    ),
    "bg": _folder_item(
        "bg", "assets", "bg", label="Background",
        path="/assets/bg",
    ),
}


# ---------------------------------------------------------------------
# _fetch_all_folders - the single bulk hierarchy query
# ---------------------------------------------------------------------


def test_fetch_all_folders_empty_without_project():
    controller = BrowserWidgetController(BrowserController())
    assert controller._fetch_all_folders() == {}


def test_fetch_all_folders_builds_full_tree_with_filter_text(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    get_folder_items = Mock(return_value=dict(_HIERARCHY))
    monkeypatch.setattr(
        controller._loader_controller,
        "get_folder_items",
        get_folder_items,
    )

    result = controller._fetch_all_folders()

    # A single call fetches the whole hierarchy - no per-level queries.
    get_folder_items.assert_called_once_with("test_project")

    # Root level: only "assets" is a true root (parent_id is None).
    assert [n.id for n in result[None]] == ["assets"]

    assets_children = {n.id: n for n in result["assets"]}
    assert set(assets_children) == {"char", "bg"}
    # Sorted case-insensitively by label: "Background" before "Characters".
    assert [n.id for n in result["assets"]] == ["bg", "char"]

    char_node = assets_children["char"]
    assert char_node.label == "Characters"
    assert char_node.has_children is True
    assert char_node.filter_text == (
        "/assets/char /assets/characters".casefold()
    )

    bg_node = assets_children["bg"]
    assert bg_node.has_children is False

    hero_node = result["char"][0]
    assert hero_node.id == "hero"
    assert hero_node.filter_text == (
        "/assets/char/hero /assets/characters/hero".casefold()
    )
    assert hero_node.has_children is False

    # Parent tracking is populated as a side effect (used elsewhere,
    # e.g. _get_top_level_selected_folder_ids).
    assert controller._folder_parent_ids["hero"] == "char"


def test_fetch_all_folders_restricts_to_folder_id_scope(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    controller._folder_id_scope = {"assets", "char", "hero"}
    monkeypatch.setattr(
        controller._loader_controller,
        "get_folder_items",
        lambda project_name: dict(_HIERARCHY),
    )

    result = controller._fetch_all_folders()

    all_ids = {node.id for nodes in result.values() for node in nodes}
    assert all_ids == {"assets", "char", "hero"}
    assert [n.id for n in result["assets"]] == ["char"]


# ---------------------------------------------------------------------
# fetch_tree_data - category dispatch used as BulkTreeModel.fetch_all
# ---------------------------------------------------------------------


def test_fetch_tree_data_dispatches_to_bulk_folders_for_hierarchy(
    monkeypatch,
):
    controller = BrowserWidgetController(BrowserController())
    controller._current_project = "test_project"
    controller._current_category = BrowserSlicerCategory.HIERARCHY.value
    monkeypatch.setattr(
        controller._loader_controller,
        "get_folder_items",
        lambda project_name: dict(_HIERARCHY),
    )

    result = controller.fetch_tree_data()

    assert [n.id for n in result[None]] == ["assets"]


def test_fetch_tree_data_wraps_reviews_as_flat_root_level(monkeypatch):
    controller = BrowserWidgetController(BrowserController())
    controller._current_category = BrowserSlicerCategory.REVIEWS.value
    monkeypatch.setattr(
        controller,
        "_fetch_reviews",
        lambda parent_id: ["review-node"] if parent_id is None else [],
    )

    result = controller.fetch_tree_data()

    assert result == {None: ["review-node"]}
