"""Placeholder plugins can opt out of discovery with 'skip_discovery'.

Only a class that defines 'skip_discovery = True' itself is skipped,
subclasses are still discovered unless they define it again.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderPlugin,
    deregister_workfile_build_plugin,
    discover_workfile_build_plugins,
    register_workfile_build_plugin,
)


class _BasePlaceholderPlugin(PlaceholderPlugin):
    """Host base class that should not be used as a plugin."""
    skip_discovery = True

    def create_placeholder(self, placeholder_data):
        pass

    def update_placeholder(self, placeholder_item, placeholder_data):
        pass

    def collect_placeholders(self):
        return []

    def populate_placeholder(self, placeholder):
        pass


class _ConcretePlaceholderPlugin(_BasePlaceholderPlugin):
    """Inherits 'skip_discovery' but does not define it."""


class _SkippedPlaceholderPlugin(_BasePlaceholderPlugin):
    skip_discovery = True


class _ReenabledPlaceholderPlugin(_SkippedPlaceholderPlugin):
    skip_discovery = False


PLUGINS = (
    _BasePlaceholderPlugin,
    _ConcretePlaceholderPlugin,
    _SkippedPlaceholderPlugin,
    _ReenabledPlaceholderPlugin,
)
EXPECTED = {_ConcretePlaceholderPlugin, _ReenabledPlaceholderPlugin}


@pytest.fixture
def registered_plugins():
    for plugin in PLUGINS:
        register_workfile_build_plugin(plugin)
    yield
    for plugin in PLUGINS:
        deregister_workfile_build_plugin(plugin)


def test_placeholder_plugin_defines_skip_discovery():
    assert PlaceholderPlugin.__dict__.get("skip_discovery") is True


def test_discover_skips_only_defining_class(registered_plugins):
    discovered = set(discover_workfile_build_plugins())

    assert EXPECTED <= discovered
    assert _BasePlaceholderPlugin not in discovered
    assert _SkippedPlaceholderPlugin not in discovered


def test_builder_discovery_skips_plugins(registered_plugins):
    builder = SimpleNamespace(_host=object())

    classes = set(
        AbstractTemplateBuilder.get_placeholder_plugin_classes(builder)
    )

    assert EXPECTED <= classes
    assert _BasePlaceholderPlugin not in classes
    assert _SkippedPlaceholderPlugin not in classes


def test_host_provided_plugins_skip_plugins():
    host = SimpleNamespace(
        get_workfile_build_placeholder_plugins=lambda: list(PLUGINS)
    )
    builder = SimpleNamespace(_host=host)

    classes = AbstractTemplateBuilder.get_placeholder_plugin_classes(builder)

    assert set(classes) == EXPECTED
