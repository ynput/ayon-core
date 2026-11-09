"""Tests for refreshing folders of 'HierarchyModel' from more threads."""

from __future__ import annotations

import threading
import time
from unittest.mock import Mock

from ayon_core.tools.common_models.hierarchy import HierarchyModel

PROJECT_NAME = "demo"
FOLDERS = {"folder_id": Mock()}


def _model() -> HierarchyModel:
    model = HierarchyModel(Mock())
    model._query_folders = Mock(
        side_effect=lambda _project_name: time.sleep(0.2) or FOLDERS
    )
    return model


def test_concurrent_callers_wait_for_one_query():
    model = _model()
    results = []

    def _get():
        results.append(model.get_folder_items(PROJECT_NAME, None))

    threads = [threading.Thread(target=_get) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(5)

    model._query_folders.assert_called_once_with(PROJECT_NAME)
    assert results == [FOLDERS] * 4


def test_refresh_event_callback_does_not_deadlock():
    model = _model()
    nested = []

    def _emit_event(topic, *_args, **_kwargs):
        # Callbacks run in the refreshing thread and may ask for folders
        if topic == "folders.refresh.started":
            nested.append(model.get_folder_items(PROJECT_NAME, None))

    model._controller.emit_event.side_effect = _emit_event

    assert model.get_folder_items(PROJECT_NAME, None) == FOLDERS
    assert nested == [{}]
    model._query_folders.assert_called_once_with(PROJECT_NAME)
