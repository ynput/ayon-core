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
    get_action_items = model._get_action_items

    def _slow_get_action_items(project_name):
        # Refresh from another thread happens right after items are
        #   collected, before action objects are used
        action_items = get_action_items(project_name)
        items_collected.set()
        time.sleep(0.2)
        return action_items

    model._get_action_items = _slow_get_action_items

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
