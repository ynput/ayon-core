"""Tests for loading bundle information in 'ayon_core.addon.base'."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest

from ayon_core.addon import base

STUDIO_BUNDLE = {"name": "Studio-Bundle"}
PROJECT_BUNDLE = {"name": "__project__demo__staging"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "env, expected_variant",
    [
        ({}, "production"),
        ({"AYON_USE_STAGING": "1"}, "staging"),
        (
            {"AYON_USE_DEV": "1", "AYON_BUNDLE_NAME": "Dev-Bundle"},
            "Dev-Bundle",
        ),
    ],
)
def test_load_bundle_information_sends_variant(
    monkeypatch, env, expected_variant
):
    """Settings request must include the settings variant.

    Without the variant the server resolves a project bundle against the
    'production' variant, so a project frozen only for 'staging' returns
    404 with no 'addons' key and the addons fail to load.

    """
    for key in ("AYON_USE_STAGING", "AYON_USE_DEV"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    requested = []

    def fake_get(endpoint):
        requested.append(endpoint)
        return SimpleNamespace(
            data={"addons": [{"name": "core", "version": "1.0.0"}]}
        )

    with patch.object(
        base, "_get_ayon_bundle_data",
        return_value=(STUDIO_BUNDLE, PROJECT_BUNDLE),
    ), patch.object(base.ayon_api, "get", side_effect=fake_get):
        info = base._load_bundle_information()

    assert info.addons == [base.BundleAddon(name="core", version="1.0.0")]
    query = parse_qs(urlparse(requested[0]).query)
    assert query["variant"] == [expected_variant]
    assert query["bundle_name"] == [STUDIO_BUNDLE["name"]]
    assert query["project_bundle_name"] == [PROJECT_BUNDLE["name"]]
