"""Tests for hierarchy model."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from ayon_core.tools.common_models import hierarchy


def _rest_folder(
    folder_id: str,
    parent_id: str | None,
    path: str,
    active: bool | None = True,
) -> dict[str, Any]:
    """Flat folder item as returned by 'get_rest_folders'.

    Args:
        folder_id (str): Folder id.
        parent_id (str | None): Parent folder id.
        path (str): Folder path without leading slash.
        active (bool | None): Folder active state. 'None' leaves the key
            out, like older servers do.

    Returns:
        dict[str, Any]: Flat folder item.

    """
    folder = {
        "id": folder_id,
        "parentId": parent_id,
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "label": None,
        "folderType": "Folder",
        "status": "open",
    }
    if active is not None:
        folder["active"] = active
    return folder


@pytest.fixture
def get_folder_ids(monkeypatch):
    def _get_folder_ids(folders: list[dict[str, Any]]) -> set[str]:
        monkeypatch.setattr(
            hierarchy.ayon_api,
            "get_rest_folders",
            Mock(return_value=folders),
        )
        model = hierarchy.HierarchyModel(Mock())
        return set(model.get_folder_items("demo", None))
    return _get_folder_ids


def test_inactive_root_hides_descendants(get_folder_ids):
    folders = [
        _rest_folder("root", None, "root", active=False),
        _rest_folder("child", "root", "root/child"),
        _rest_folder("grandchild", "child", "root/child/grandchild"),
        _rest_folder("other", None, "other"),
    ]
    assert get_folder_ids(folders) == {"other"}


def test_inactive_nested_folder_hides_subtree(get_folder_ids):
    folders = [
        # Children listed before parents to not rely on response order
        _rest_folder("grandchild", "inactive", "root/inactive/grandchild"),
        _rest_folder("inactive", "root", "root/inactive", active=False),
        _rest_folder("sibling", "root", "root/sibling"),
        _rest_folder("root", None, "root"),
    ]
    assert get_folder_ids(folders) == {"root", "sibling"}


def test_missing_active_is_kept(get_folder_ids):
    folders = [
        _rest_folder("root", None, "root", active=None),
        _rest_folder("child", "root", "root/child", active=None),
    ]
    assert get_folder_ids(folders) == {"root", "child"}
