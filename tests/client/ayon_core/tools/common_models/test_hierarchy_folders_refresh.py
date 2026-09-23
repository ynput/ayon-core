"""Concurrent folder refreshes of the shared hierarchy model."""

from __future__ import annotations

import threading
import time

from ayon_core.tools.common_models.hierarchy import (
    FolderItem,
    HierarchyModel,
)

PROJECT_NAME = "demo"


class _Controller:
    def __init__(self):
        self.callbacks = []

    def emit_event(self, topic, data=None, source=None):
        for callback in self.callbacks:
            callback(topic, data)


def _folder_items():
    folder = FolderItem(
        entity_id="assets",
        parent_id=None,
        name="assets",
        path="/assets",
        folder_type="Folder",
        label="Assets",
        status="Not ready",
    )
    return {folder.entity_id: folder}


def test_concurrent_caller_waits_for_running_refresh(monkeypatch):
    model = HierarchyModel(_Controller())
    query_started = threading.Event()

    def slow_query(project_name):
        query_started.set()
        time.sleep(0.2)
        return _folder_items()

    monkeypatch.setattr(model, "_query_folders", slow_query)
    results = {}
    thread = threading.Thread(
        target=lambda: results.update(
            worker=model.get_folder_items(PROJECT_NAME, None)
        )
    )
    thread.start()
    assert query_started.wait(1)

    main_result = model.get_folder_items(PROJECT_NAME, None)
    thread.join()

    assert set(main_result) == {"assets"}
    assert set(results["worker"]) == {"assets"}


def test_reentrant_call_from_refresh_event_does_not_block(monkeypatch):
    controller = _Controller()
    model = HierarchyModel(controller)
    monkeypatch.setattr(model, "_query_folders", lambda _: _folder_items())
    nested = []

    def on_event(topic, data):
        if topic == "folders.refresh.started":
            nested.append(model.get_folder_items(PROJECT_NAME, None))

    controller.callbacks.append(on_event)

    assert set(model.get_folder_items(PROJECT_NAME, None)) == {"assets"}
    # Nested call returns the not yet filled cache instead of deadlocking
    assert nested == [{}]
