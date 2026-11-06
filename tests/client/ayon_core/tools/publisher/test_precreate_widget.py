"""Tests for the publisher pre-create attributes widget."""

from __future__ import annotations

from types import SimpleNamespace

from ayon_core.lib import BoolDef
from ayon_core.tools.publisher.widgets.precreate_widget import (
    PreCreateWidget,
)

TOPIC = "create.context.pre.create.attrs.changed"


class FakeController:
    """Minimal controller providing what 'PreCreateWidget' uses."""

    def __init__(self):
        self.callbacks = {}
        self.attr_defs_by_identifier = {}
        self.requested = []

    def register_event_callback(self, topic, callback):
        self.callbacks.setdefault(topic, []).append(callback)

    def emit(self, topic, data):
        for callback in self.callbacks.get(topic, []):
            callback(data)

    def get_pre_create_attribute_defs(self, identifier):
        self.requested.append(identifier)
        return list(self.attr_defs_by_identifier.get(identifier, []))


def test_pre_create_attrs_changed_refreshes_current_creator(qtbot):
    """Event 'identifiers' is a list; matching creator must refresh."""
    controller = FakeController()
    controller.attr_defs_by_identifier = {
        "creator.a": [BoolDef("first", default=True)],
        "creator.b": [],
    }
    widget = PreCreateWidget(controller, None)
    qtbot.addWidget(widget)

    widget.set_creator_item(SimpleNamespace(identifier="creator.a"))
    assert list(widget.current_value()) == ["first"]

    controller.attr_defs_by_identifier["creator.a"] = [
        BoolDef("first", default=True),
        BoolDef("second", default=False),
    ]
    controller.emit(TOPIC, {"identifiers": ["creator.b", "creator.a"]})

    assert sorted(widget.current_value()) == ["first", "second"]


def test_pre_create_attrs_changed_other_creator_only_clears_cache(qtbot):
    """Change of a non-current creator invalidates cache without refresh."""
    controller = FakeController()
    controller.attr_defs_by_identifier = {
        "creator.a": [BoolDef("first", default=True)],
        "creator.b": [BoolDef("other", default=True)],
    }
    widget = PreCreateWidget(controller, None)
    qtbot.addWidget(widget)

    widget.set_creator_item(SimpleNamespace(identifier="creator.b"))
    widget.set_creator_item(SimpleNamespace(identifier="creator.a"))
    controller.requested.clear()

    controller.emit(TOPIC, {"identifiers": ["creator.b"]})
    # Current creator is untouched and was not re-queried
    assert controller.requested == []
    assert list(widget.current_value()) == ["first"]

    # Switching back must query fresh definitions for the changed creator
    widget.set_creator_item(SimpleNamespace(identifier="creator.b"))
    assert controller.requested == ["creator.b"]
