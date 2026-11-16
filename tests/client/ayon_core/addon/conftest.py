"""Fake AYON server connection for addon loading tests."""
from __future__ import annotations

import collections
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from ayon_core.addon import base
from ayon_core.settings import lib as settings_lib

STUDIO_BUNDLE = "Studio-Bundle"
PROJECT_BUNDLE = "__project__demo__production"
ADDON_VERSIONS = {"core": "1.0.0", "applications": "1.2.0"}


class FakeConnection:
    """Answers requests of 'ayon_api' and records them."""

    studio_bundle = STUDIO_BUNDLE
    project_bundle = PROJECT_BUNDLE
    addon_versions = ADDON_VERSIONS

    def __init__(self):
        self.requests: list[str] = []

    def get_site_id(self) -> str:
        return "farm"

    def set_default_settings_variant(self, variant: str) -> None:
        pass

    @staticmethod
    def get_query(endpoint: str) -> dict[str, list[str]]:
        return parse_qs(urlparse(endpoint).query)

    def get_bundles(self) -> dict:
        return self.get("bundles").data

    def get(self, entrypoint: str, **kwargs) -> SimpleNamespace:
        self.requests.append(entrypoint)
        if entrypoint == "bundles":
            data = {
                "bundles": [
                    {"name": STUDIO_BUNDLE, "addons": ADDON_VERSIONS},
                    {"name": PROJECT_BUNDLE, "addons": ADDON_VERSIONS},
                ]
            }
        elif entrypoint.startswith("settings?"):
            query = parse_qs(urlparse(entrypoint).query)
            summary = query.get("summary") == ["true"]
            data = {
                "addons": [
                    {
                        "name": name,
                        "version": version,
                        "settings": (
                            {} if summary else {"environments": "{}"}
                        ),
                    }
                    for name, version in ADDON_VERSIONS.items()
                ]
            }
        else:
            raise AssertionError(f"Unexpected request '{entrypoint}'")
        return SimpleNamespace(
            data=data, status=200, raise_for_status=lambda: None
        )


@pytest.fixture
def connection(monkeypatch, tmp_path) -> FakeConnection:
    """Fake connection, empty addons directory and clean caches."""
    con = FakeConnection()
    monkeypatch.setattr(
        base.ayon_api._api, "get_server_api_connection", lambda: con
    )
    for key in ("AYON_USE_STAGING", "AYON_USE_DEV"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AYON_STUDIO_BUNDLE_NAME", STUDIO_BUNDLE)
    monkeypatch.setenv("AYON_BUNDLE_NAME", STUDIO_BUNDLE)
    # No client code of addons is imported
    monkeypatch.setenv("AYON_ADDONS_DIR", str(tmp_path))

    cache_cls = settings_lib._AyonSettingsCache
    monkeypatch.setattr(cache_cls, "variant", None)
    monkeypatch.setattr(
        cache_cls,
        "cache_by_project_name",
        collections.defaultdict(settings_lib.CacheItem.create_outdated),
    )
    monkeypatch.setattr(
        cache_cls, "addon_versions", settings_lib.CacheItem.create_outdated()
    )
    monkeypatch.setattr(base._LoadCache, "loaded", False)
    monkeypatch.setattr(base._LoadCache, "bundle_information", None)
    monkeypatch.setattr(base._LoadCache, "addon_modules", [])
    return con
