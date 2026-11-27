"""Tests for the configurable USD asset/shot contributions collector."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from ayon_core.plugins.publish import extract_usd_parent_contributions as mod
from ayon_core.plugins.publish.extract_usd_parent_contributions import (
    CollectUSDAssetContributions,
    find_nearest_parent_folder_of_type,
)

ENTITY_URI = "ayon://test/sq01?product=usdSequence&version=1&representation=usd"

FOLDER_TYPES_BY_PATH = {
    "/ep01": "Episode",
    "/ep01/sq01": "Sequence",
    "/ep01/sq01/sq01a": "Sequence",
    "/ep01/sq01/sq01a/sh010": "Shot",
}


class _Context:
    def __init__(self, data: dict):
        self.data = data


class _Instance:
    """Minimal stand-in for a `pyblish.api.Instance`."""
    def __init__(self, data: dict, context_data: dict | None = None):
        self.data = data
        self.context = _Context(context_data or {})


def _get_folders(project_name, folder_paths, folder_types):
    return [
        {"path": path, "folderType": folder_type}
        for path, folder_type in FOLDER_TYPES_BY_PATH.items()
        if path in folder_paths and folder_type in folder_types
    ]


def _contribution_settings(**overrides) -> dict:
    settings = {
        "name": "sequence.manifest",
        "order": 10,
        "type": "sublayer",
        "reference": {"target_prim_path": "/{default_prim_name}"},
        "variant": {
            "target_prim_path": "/{default_prim_name}",
            "variant_set_name": "model",
            "variant_name": "main",
            "variant_default_policy": "never",
        },
        "only_if_existing": False,
        "load_from": "source_path",
        "source_path": ENTITY_URI,
        "search_product": {
            "folder_type": "Sequence",
            "product_name": "usdSequence",
            "version": "latest",
            "representation_name": "usd",
            "as_ayon_entity_uri": True,
        },
    }
    settings.update(overrides)
    return settings


@pytest.fixture
def plugin() -> CollectUSDAssetContributions:
    return CollectUSDAssetContributions()


@pytest.fixture
def instance(tmp_path) -> _Instance:
    publish_dir = tmp_path / "publish" / "usdShot" / "v001"
    publish_dir.mkdir(parents=True, exist_ok=True)
    return _Instance(
        data={
            "folderPath": "/ep01/sq01/sq01a/sh010",
            "productName": "usdShot",
            "publishDir": str(publish_dir),
            "anatomyData": {
                "project": {"name": "test"},
                "folder": {"name": "sh010", "path": "/ep01/sq01/sq01a/sh010"},
            },
        },
        context_data={"projectName": "test"},
    )


class TestFindNearestParentFolderOfType:
    @patch.object(mod.ayon_api, "get_folders", side_effect=_get_folders)
    def test_nearest_parent_per_folder_type(self, _mock_get_folders):
        folders = find_nearest_parent_folder_of_type(
            "test", "/ep01/sq01/sq01a/sh010", {"Sequence", "Episode"}
        )
        assert {folder["path"] for folder in folders} == {
            "/ep01", "/ep01/sq01/sq01a"
        }

    @patch.object(mod.ayon_api, "get_folders", side_effect=_get_folders)
    def test_source_folder_is_not_its_own_parent(self, mock_get_folders):
        folders = find_nearest_parent_folder_of_type(
            "test", "/ep01/sq01/sq01a", {"Sequence"}
        )
        assert [folder["path"] for folder in folders] == ["/ep01/sq01"]
        assert mock_get_folders.call_args.kwargs["folder_paths"] == {
            "/ep01", "/ep01/sq01"
        }

    @patch.object(mod.ayon_api, "get_folders", side_effect=_get_folders)
    def test_root_folder_has_no_parents(self, mock_get_folders):
        assert find_nearest_parent_folder_of_type(
            "test", "/ep01", {"Episode"}
        ) == []
        mock_get_folders.assert_not_called()


class TestSourceExists:
    def test_absolute_path(self, plugin, instance, tmp_path):
        existing = tmp_path / "existing.usd"
        existing.write_text("#usda 1.0")
        assert plugin._source_exists(str(existing), instance)
        assert not plugin._source_exists(
            str(tmp_path / "missing.usd"), instance
        )

    def test_relative_path_is_anchored_to_publish_dir(
        self, plugin, instance, tmp_path, monkeypatch
    ):
        """Relative paths resolve from the published USD layer, not cwd."""
        cwd = tmp_path / "cwd"
        cwd.mkdir(exist_ok=True)
        monkeypatch.chdir(cwd)

        # A file relative to the current working directory is irrelevant
        (cwd / "only_in_cwd.usd").write_text("#usda 1.0")
        assert not plugin._source_exists("./only_in_cwd.usd", instance)
        assert not plugin._source_exists("only_in_cwd.usd", instance)

        publish_dir = instance.data["publishDir"]
        with open(os.path.join(publish_dir, "sibling.usd"), "w") as stream:
            stream.write("#usda 1.0")
        assert plugin._source_exists("./sibling.usd", instance)
        assert plugin._source_exists("sibling.usd", instance)

        parent_dir = os.path.dirname(publish_dir)
        with open(os.path.join(parent_dir, "parent.usd"), "w") as stream:
            stream.write("#usda 1.0")
        assert plugin._source_exists("../parent.usd", instance)
        assert not plugin._source_exists("../missing.usd", instance)

    def test_relative_path_without_publish_dir(
        self, plugin, instance, tmp_path, monkeypatch
    ):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "file.usd").write_text("#usda 1.0")
        del instance.data["publishDir"]
        assert not plugin._source_exists("./file.usd", instance)

    def test_entity_uri_is_resolved(self, plugin, instance, tmp_path):
        existing = tmp_path / "existing.usd"
        existing.write_text("#usda 1.0")
        with patch.object(
            mod, "resolve_entity_uri", return_value=str(existing)
        ) as mock_resolve:
            assert plugin._source_exists(ENTITY_URI, instance)
            mock_resolve.assert_called_once_with(ENTITY_URI)

    @pytest.mark.parametrize("resolved", [None, "/does/not/exist.usd"])
    def test_entity_uri_unresolved(self, plugin, instance, resolved):
        with patch.object(mod, "resolve_entity_uri", return_value=resolved):
            assert not plugin._source_exists(ENTITY_URI, instance)


class TestGetSource:
    def test_source_path_is_formatted(self, plugin, instance):
        settings = _contribution_settings(
            source_path=(
                "ayon://{project[name]}{folder[path]}"
                "?product=usdManifest&version=latest&representation=usd"
            )
        )
        assert plugin._get_source(settings, instance) == (
            "ayon://test/ep01/sq01/sq01a/sh010"
            "?product=usdManifest&version=latest&representation=usd"
        )

    @patch.object(mod.ayon_api, "get_folders", side_effect=_get_folders)
    def test_search_product_as_entity_uri(
        self, _mock_get_folders, plugin, instance
    ):
        settings = _contribution_settings(load_from="search_product")
        assert plugin._get_source(settings, instance) == (
            "ayon://test/ep01/sq01/sq01a"
            "?product=usdSequence&version=latest&representation=usd"
        )

    @patch.object(mod.ayon_api, "get_folders", side_effect=_get_folders)
    def test_search_product_without_matching_parent(
        self, _mock_get_folders, plugin, instance
    ):
        settings = _contribution_settings(load_from="search_product")
        settings["search_product"]["folder_type"] = "Asset"
        assert plugin._get_source(settings, instance) is None

    def test_unknown_source_type(self, plugin, instance):
        settings = _contribution_settings(load_from="unknown")
        with pytest.raises(ValueError):
            plugin._get_source(settings, instance)


class TestGetContribution:
    """Contribution dataclasses require the USD libraries."""

    @pytest.fixture(autouse=True)
    def _require_usd(self):
        pytest.importorskip("pxr")

    def test_sublayer(self, plugin, instance):
        from ayon_core.pipeline.usdlib import SublayerContribution

        contribution = plugin._get_contribution(
            _contribution_settings(), instance
        )
        assert contribution == SublayerContribution(
            source=ENTITY_URI, layer_id="sequence.manifest", order=10
        )

    def test_reference(self, plugin, instance):
        from ayon_core.pipeline.usdlib import ReferenceContribution

        contribution = plugin._get_contribution(
            _contribution_settings(type="reference"), instance
        )
        assert contribution == ReferenceContribution(
            source=ENTITY_URI,
            layer_id="sequence.manifest",
            order=10,
            target_prim_path="/sh010",
        )

    def test_variant(self, plugin, instance):
        from ayon_core.pipeline.usdlib import VariantContribution

        contribution = plugin._get_contribution(
            _contribution_settings(type="variant"), instance
        )
        assert contribution == VariantContribution(
            source=ENTITY_URI,
            layer_id="sequence.manifest",
            order=10,
            target_prim_path="/sh010",
            variant_set_name="model",
            variant_name="main",
            variant_default_policy="never",
        )

    def test_missing_source_is_skipped_if_only_existing(
        self, plugin, instance
    ):
        settings = _contribution_settings(
            only_if_existing=True, source_path="./missing.usd"
        )
        assert plugin._get_contribution(settings, instance) is None

        settings["only_if_existing"] = False
        assert plugin._get_contribution(settings, instance) is not None
