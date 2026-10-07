"""Tests for collecting launcher actions while actions are refreshed."""

from __future__ import annotations

import itertools
import threading
import time
from unittest.mock import Mock

from ayon_core.tools.launcher.models.actions import ActionsModel


def _action_class(identifier: str) -> type:
    return type(identifier, (), {
        "identifier": identifier,
        "label": identifier,
        "order": 0,
        "icon": None,
        "is_compatible": lambda self, selection: True,
    })


def test_refresh_during_collection_keeps_items_consistent():
    model = ActionsModel(Mock())
    # Each discovery finds actions with new identifiers
    counter = itertools.count()
    model._discover_action_classes = lambda: [
        _action_class(f"action_{next(counter)}")
    ]
    model._prepare_selection = Mock()
    model._get_webactions = Mock(return_value=[])

    items_collected = threading.Event()
    build_action_items = model._build_action_items

    def _slow_build_action_items(*args):
        # Refresh from another thread happens while items are collected
        action_items = build_action_items(*args)
        items_collected.set()
        time.sleep(0.2)
        return action_items

    model._build_action_items = _slow_build_action_items

    results = []
    errors = []

    def _collect():
        try:
            results.append(
                model.get_action_items("demo", None, None, None)
            )
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=_collect)
    thread.start()
    items_collected.wait(5)
    model.refresh()
    thread.join(5)

    assert errors == []
    assert len(results[0]) == 1


def test_server_queries_happen_outside_of_lock():
    controller = Mock()
    model = ActionsModel(controller)
    model._discover_action_classes = lambda: [_action_class("action")]
    lock_held = []
    controller.get_project_settings.side_effect = lambda _name: (
        lock_held.append(model._lock._is_owned()) or {}
    )

    model._get_actions_snapshot("demo")

    assert lock_held == [False]
