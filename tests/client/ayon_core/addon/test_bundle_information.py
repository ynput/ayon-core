"""Tests for loading bundle information in 'ayon_core.addon.base'."""
from __future__ import annotations

import pytest

from ayon_core.addon import base


@pytest.mark.unit
@pytest.mark.parametrize(
    "env, expected_variant",
    [
        ({}, "production"),
        ({"AYON_USE_STAGING": "1"}, "staging"),
        ({"AYON_USE_DEV": "1"}, None),
    ],
)
def test_load_bundle_information_sends_variant(
    connection, monkeypatch, env, expected_variant
):
    """Settings request must include the settings variant.

    Without the variant the server resolves a project bundle against the
    'production' variant, so a project frozen only for 'staging' returns
    404 with no 'addons' key and the addons fail to load.

    """
    # Dev mode uses bundle name as variant
    if expected_variant is None:
        expected_variant = connection.project_bundle
    monkeypatch.setenv("AYON_BUNDLE_NAME", connection.project_bundle)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    info = base._load_bundle_information()

    assert [addon.name for addon in info.addons] == ["core", "applications"]
    query = connection.get_query(connection.requests[0])
    assert query["variant"] == [expected_variant]
    assert query["bundle_name"] == [connection.studio_bundle]
    assert query["project_bundle_name"] == [connection.project_bundle]
