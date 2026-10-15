"""Tests for `ayon_core.pipeline.context_tools.install_ayon_plugins`.

Host-less processes must still get the addon loader plugin paths: the tray
opens the Browser and calls `install_ayon_plugins()` without a host name,
and addons like OpenRV, DJV and xStudio serve their 'global' loader folder
for `host_name=None`.
"""
import pytest

from ayon_core.pipeline import context_tools


class _FakeAddonsManager:
    """Record which plugin path collectors ran, and with which host name."""

    def __init__(self):
        self.collected = {}

    def _record(self, plugin_type, host_name):
        self.collected.setdefault(plugin_type, []).append(host_name)

    def collect_publish_plugin_paths(self, host_name):
        self._record("publish", host_name)
        return []

    def collect_create_plugin_paths(self, host_name):
        self._record("create", host_name)
        return []

    def collect_load_plugin_paths(self, host_name):
        self._record("load", host_name)
        return ["/fake/load"]

    def collect_inventory_action_paths(self, host_name):
        self._record("inventory", host_name)
        return []


@pytest.fixture
def install_env(monkeypatch):
    """Replace everything `install_ayon_plugins` touches outside itself."""
    manager = _FakeAddonsManager()
    registered = {"loaders": [], "creators": [], "inventory": []}

    monkeypatch.setattr(context_tools, "_get_addons_manager", lambda: manager)
    monkeypatch.setattr(
        context_tools, "initialize_ayon_connection", lambda: None)
    monkeypatch.setattr(context_tools, "load_addons", lambda: None)
    monkeypatch.setattr(
        context_tools,
        "register_loader_plugin_path",
        registered["loaders"].append,
    )
    monkeypatch.setattr(
        context_tools,
        "register_creator_plugin_path",
        registered["creators"].append,
    )
    monkeypatch.setattr(
        context_tools,
        "register_inventory_action_path",
        registered["inventory"].append,
    )
    monkeypatch.setattr(
        context_tools.pyblish.api,
        "register_plugin_path",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        context_tools.pyblish.api,
        "register_discovery_filter",
        lambda *args, **kwargs: None,
    )
    # Keep the anatomy/root part out of the test, it needs a server.
    monkeypatch.delenv("AYON_PROJECT_NAME", raising=False)

    return manager, registered


def test_load_plugin_paths_registered_without_host(install_env, monkeypatch):
    """The host-less tray Browser still gets addon loader plugins.

    Regression: `install_ayon_plugins` skipped *all* host specific plugin
    registration when no host name was set, which also dropped the loader
    plugin paths and made addon loaders disappear from the Browser.
    """
    manager, registered = install_env
    monkeypatch.setattr(context_tools, "get_current_host_name", lambda: None)

    context_tools.install_ayon_plugins()

    assert manager.collected["load"] == [None]
    assert registered["loaders"] == ["/fake/load"]

    # The other plugin types genuinely need a host.
    assert "publish" not in manager.collected
    assert "create" not in manager.collected
    assert "inventory" not in manager.collected


def test_host_plugin_paths_registered_with_host(install_env, monkeypatch):
    """With a host name every plugin type is collected, as before."""
    manager, registered = install_env
    monkeypatch.setattr(
        context_tools, "get_current_host_name", lambda: "openrv")

    context_tools.install_ayon_plugins()

    assert manager.collected["load"] == ["openrv"]
    assert manager.collected["publish"] == ["openrv"]
    assert manager.collected["create"] == ["openrv"]
    assert manager.collected["inventory"] == ["openrv"]
    assert registered["loaders"] == ["/fake/load"]


def test_explicit_host_name_is_used(install_env):
    """An explicitly passed host name wins over the environment."""
    manager, _registered = install_env

    context_tools.install_ayon_plugins(host_name="openrv")

    assert manager.collected["load"] == ["openrv"]
