"""Tests for fetching project info of the Browser UI controller."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

import pytest

from ayon_core.tools.browser.ui import browser_controller
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)


@pytest.fixture
def controller(monkeypatch):
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager", Mock()
    )
    # Collect queued tasks instead of running them in the task queue
    tasks = []
    task_queue = Mock()
    task_queue.enqueue.side_effect = tasks.append
    monkeypatch.setattr(
        browser_controller, "get_task_queue", lambda: task_queue
    )
    controller = BrowserWidgetController(Mock())
    controller._apply_project_info = Mock()
    controller.tasks = tasks
    return controller


def test_result_fetched_before_reset_is_ignored(controller):
    controller._current_project = "demo"
    controller._request_project_info("demo")
    old_task = controller.tasks.pop()

    controller._on_loader_controller_reset()
    new_task = controller.tasks.pop()
    old_task.callback({"old": True})

    assert controller._get_cached_project_info("demo") is None
    controller._apply_project_info.assert_not_called()

    new_task.callback({"new": True})

    assert controller._get_cached_project_info("demo") == {"new": True}
    controller._apply_project_info.assert_called_once_with({"new": True})
