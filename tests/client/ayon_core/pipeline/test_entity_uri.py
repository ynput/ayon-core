"""Tests for AYON entity URI helpers."""
import pytest

from ayon_core.pipeline.entity_uri import (
    construct_ayon_entity_uri,
    parse_ayon_entity_uri,
)


class TestParseAyonEntityUri:
    @pytest.mark.parametrize("scheme", ["ayon", "ayon+entity"])
    def test_parse_supported_schemes(self, scheme):
        uri = (
            f"{scheme}://test/char/villain"
            "?product=modelMain&version=2&representation=usd"
        )
        assert parse_ayon_entity_uri(uri) == {
            "project": "test",
            "folderPath": "/char/villain",
            "product": "modelMain",
            "version": 2,
            "representation": "usd",
        }

    @pytest.mark.parametrize("version", ["latest", "latestDone", "hero"])
    def test_parse_keeps_named_version(self, version):
        uri = (
            f"ayon://test/hero?product=modelMain&version={version}"
            "&representation=usd"
        )
        assert parse_ayon_entity_uri(uri)["version"] == version

    @pytest.mark.parametrize("path", [
        "/path/to/file.usd",
        "./relative/file.usd",
        "C:/path/to/file.usd",
        "https://test/hero?product=modelMain",
    ])
    def test_parse_non_entity_uri(self, path):
        assert not parse_ayon_entity_uri(path)


class TestConstructAyonEntityUri:
    @staticmethod
    def _construct(version):
        return construct_ayon_entity_uri(
            project_name="test",
            folder_path="/char/villain",
            product="modelMain",
            version=version,
            representation_name="usd",
        )

    @pytest.mark.parametrize("version, expected", [
        (2, 2),
        # Digits as string, e.g. from settings
        ("2", 2),
        ("latest", "latest"),
        ("latestDone", "latestDone"),
        ("hero", "hero"),
        # Negative versions are hero versions
        (-1, "hero"),
        ("-1", "hero"),
    ])
    def test_construct_roundtrip(self, version, expected):
        uri = self._construct(version)
        assert parse_ayon_entity_uri(uri) == {
            "project": "test",
            "folderPath": "/char/villain",
            "product": "modelMain",
            "version": expected,
            "representation": "usd",
        }

    @pytest.mark.parametrize("folder_path", [
        "/char/villain",
        "char/villain",
        "/char/villain/",
    ])
    def test_construct_single_slash_before_folder_path(self, folder_path):
        uri = construct_ayon_entity_uri(
            project_name="test",
            folder_path=folder_path,
            product="modelMain",
            version=2,
            representation_name="usd",
        )
        assert uri == (
            "ayon://test/char/villain"
            "?product=modelMain&version=2&representation=usd"
        )

    @pytest.mark.parametrize("version", ["", "foo", "v002", "1.5"])
    def test_construct_invalid_value(self, version):
        with pytest.raises(ValueError):
            self._construct(version)

    @pytest.mark.parametrize("version", [None, 1.5, ["latest"]])
    def test_construct_invalid_type(self, version):
        with pytest.raises(TypeError):
            self._construct(version)
