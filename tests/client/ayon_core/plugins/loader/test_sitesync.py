"""Tests for the Site Sync loader action plugin."""
from __future__ import annotations

import json
from typing import Any

import pytest

from ayon_core.pipeline.actions import (
    LoaderActionsContext,
    LoaderActionSelection,
    SelectionEntitiesCache,
)
from ayon_core.plugins.loader import sitesync as mod
from ayon_core.plugins.loader.sitesync import SiteSyncActionPlugin

PROJECT_NAME = "test_project"
ACTIVE_SITE = "local_site"
REMOTE_SITE = "studio"

# Local and remote sync progress by representation id
SYNC_STATE = {
    "repre_local": (1, 0),
    "repre_remote": (0, 1),
    "repre_both": (1, 1),
    "repre_none": (0, 0),
}


class _FakeSiteSyncAddon:
    def __init__(self, enabled=True, project_enabled=True):
        self.enabled = enabled
        self.project_enabled = project_enabled
        self.added: list[tuple[str, str]] = []
        self.removed: list[tuple[str, str, bool]] = []

    def is_project_enabled(self, project_name, single=False):
        return self.project_enabled

    def get_active_site(self, project_name):
        return ACTIVE_SITE

    def get_remote_site(self, project_name):
        return REMOTE_SITE

    def get_representations_sync_state(
        self, project_name, representation_ids, local_site, remote_site
    ):
        return {
            repre_id: SYNC_STATE[repre_id]
            for repre_id in representation_ids
            if repre_id in SYNC_STATE
        }

    def add_site(self, project_name, representation_id, site_name, force):
        self.added.append((representation_id, site_name))

    def remove_site(
        self, project_name, representation_id, site_name, remove_local_files
    ):
        self.removed.append(
            (representation_id, site_name, remove_local_files)
        )

    def is_representation_on_site(
        self, project_name, representation_id, site_name
    ):
        return False


class _FakeAddonsManager:
    def __init__(self, addon):
        self.addons = []
        self._addon = addon

    def get(self, name):
        if name == "sitesync":
            return self._addon
        return None


class _FakeContext:
    def __init__(self, addon):
        self._addons_manager = _FakeAddonsManager(addon)

    def get_addons_manager(self):
        return self._addons_manager

    def get_host_name(self):
        return None


def _make_selection(
    repre_ids: set[str],
    selected_type: str = "representation",
    product_type: str = "render",
) -> LoaderActionSelection:
    representations_by_id = {
        repre_id: {"id": repre_id, "versionId": "version_id"}
        for repre_id in SYNC_STATE
    }
    entities_cache = SelectionEntitiesCache(
        PROJECT_NAME,
        products_by_id={
            "product_id": {"id": "product_id", "productType": product_type}
        },
        versions_by_id={
            "version_id": {"id": "version_id", "productId": "product_id"}
        },
        representations_by_id=representations_by_id,
    )
    return LoaderActionSelection(
        PROJECT_NAME,
        repre_ids,
        selected_type,
        entities_cache=entities_cache,
    )


def _items_by_action(items) -> dict[str, Any]:
    return {item.data["action"]: item for item in items}


@pytest.mark.parametrize(
    "addon",
    [
        None,
        _FakeSiteSyncAddon(enabled=False),
        _FakeSiteSyncAddon(project_enabled=False),
    ],
)
def test_no_items_without_enabled_sitesync(addon):
    plugin = SiteSyncActionPlugin(_FakeContext(addon))
    selection = _make_selection(set(SYNC_STATE))
    assert plugin.get_action_items(selection) == []


def test_no_items_for_versions():
    plugin = SiteSyncActionPlugin(_FakeContext(_FakeSiteSyncAddon()))
    selection = _make_selection({"version_id"}, selected_type="version")
    assert plugin.get_action_items(selection) == []


def test_action_items_match_sync_state():
    plugin = SiteSyncActionPlugin(_FakeContext(_FakeSiteSyncAddon()))
    items = plugin.get_action_items(_make_selection(set(SYNC_STATE)))

    by_action = _items_by_action(items)
    assert set(by_action) == {"download", "upload", "remove"}
    assert by_action["download"].label == "Download"

    repre_ids = {
        action: set(item.data["representation_ids"])
        for action, item in by_action.items()
    }
    assert repre_ids["download"] == {"repre_remote", "repre_both"}
    assert repre_ids["upload"] == {"repre_local", "repre_both"}
    assert repre_ids["remove"] == {"repre_local", "repre_both"}
    # Data is sent through the UI so it must be serializable
    for item in items:
        json.dumps(item.data)


def test_only_download_when_nothing_is_local():
    plugin = SiteSyncActionPlugin(_FakeContext(_FakeSiteSyncAddon()))
    items = plugin.get_action_items(_make_selection({"repre_remote"}))
    assert set(_items_by_action(items)) == {"download"}


@pytest.mark.parametrize(
    "action, expected_site",
    [("download", ACTIVE_SITE), ("upload", REMOTE_SITE)],
)
def test_execute_adds_site(action, expected_site):
    addon = _FakeSiteSyncAddon()
    plugin = SiteSyncActionPlugin(_FakeContext(addon))
    repre_ids = ["repre_both", "repre_local"]

    result = plugin.execute_action(
        _make_selection(set(repre_ids)),
        {"action": action, "representation_ids": repre_ids},
        {},
    )

    assert sorted(addon.added) == sorted(
        (repre_id, expected_site) for repre_id in repre_ids
    )
    assert addon.removed == []
    assert result.success


def test_execute_remove_from_local():
    addon = _FakeSiteSyncAddon()
    plugin = SiteSyncActionPlugin(_FakeContext(addon))

    plugin.execute_action(
        _make_selection({"repre_local"}),
        {"action": "remove", "representation_ids": ["repre_local"]},
        {},
    )

    assert addon.removed == [("repre_local", ACTIVE_SITE, True)]
    assert addon.added == []


def test_execute_workfile_syncs_linked_representations(monkeypatch):
    def _get_versions_links(project_name, version_ids, **kwargs):
        return {
            "version_id": [
                {"entityType": "version", "entityId": "linked_version"},
                {"entityType": "folder", "entityId": "some_folder"},
            ]
        }

    def _get_representations(project_name, version_ids, fields):
        assert version_ids == {"linked_version"}
        return [{"id": "linked_repre"}]

    monkeypatch.setattr(
        mod.ayon_api, "get_versions_links", _get_versions_links
    )
    monkeypatch.setattr(
        mod.ayon_api, "get_representations", _get_representations
    )
    addon = _FakeSiteSyncAddon()
    plugin = SiteSyncActionPlugin(_FakeContext(addon))

    plugin.execute_action(
        _make_selection({"repre_remote"}, product_type="workfile"),
        {"action": "download", "representation_ids": ["repre_remote"]},
        {},
    )

    assert addon.added == [
        ("repre_remote", ACTIVE_SITE),
        ("linked_repre", ACTIVE_SITE),
    ]


def test_plugin_is_discovered_from_core():
    """Browser and legacy Loader both get the actions through discovery."""
    context = LoaderActionsContext(
        studio_settings={},
        addons_manager=_FakeAddonsManager(_FakeSiteSyncAddon()),
        host=None,
    )
    plugin = context._get_plugins().get("core.sitesync")
    # Discovery imports the file again, compare by name instead of class
    assert type(plugin).__name__ == SiteSyncActionPlugin.__name__
