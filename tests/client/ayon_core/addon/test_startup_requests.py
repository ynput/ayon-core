"""Requests sent to AYON server when 'ayon_core' CLI starts.

The CLI (e.g. 'extractenvironments' on a farm) resolves global
environments from studio settings and then initializes 'AddonsManager'.
Every request counts when hundreds of farm workers start at once.

"""
from __future__ import annotations

import pytest

from ayon_core.addon import base
from ayon_core.settings import lib as settings_lib


@pytest.mark.unit
def test_cli_startup_requests_studio_settings_only(connection):
    """Global environments and addons need only studio settings."""
    # Same order as 'ayon_core.cli.main'
    settings_lib.get_general_environments()
    manager = base.AddonsManager()

    assert len(connection.requests) == 1, connection.requests
    query = connection.get_query(connection.requests[0])
    assert "summary" not in query
    assert query["bundle_name"] == [connection.studio_bundle]
    assert query["variant"] == ["production"]
    assert query["site_id"] == ["farm"]

    bundle_info = base.get_bundle_information()
    assert bundle_info.addons == [
        base.BundleAddon(name=name, version=version)
        for name, version in connection.addon_versions.items()
    ]
    # Report lists server addons without client code
    assert "applications" in manager._report_by_name


@pytest.mark.unit
def test_bundle_entities_are_requested_on_access(connection, monkeypatch):
    """Bundle entities are requested only when used, e.g. in dev mode."""
    monkeypatch.setenv("AYON_BUNDLE_NAME", connection.project_bundle)

    bundle_info = base.get_bundle_information()
    assert connection.requests == [connection.requests[0]]
    query = connection.get_query(connection.requests[0])
    assert query["project_bundle_name"] == [connection.project_bundle]

    assert bundle_info.studio_bundle["name"] == connection.studio_bundle
    assert bundle_info.project_bundle["name"] == connection.project_bundle
    assert connection.requests.count("bundles") == 1
