"""Shared folders and tasks models load asynchronously, latest wins."""

from __future__ import annotations

import sys
import threading
import types

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

import pytest
from qtpy import QtCore

from ayon_core.ui.components import async_loader
from ayon_core.tools.common_models.hierarchy import FolderItem, TaskItem
from ayon_core.tools.utils.folders_widget import FoldersQtModel
from ayon_core.tools.utils.tasks_widget import ITEM_NAME_ROLE, TasksQtModel
from ayon_core.tools.utils.lib import run_in_main_thread


class _TaskQueue:
    """Collects tasks instead of running them in worker threads."""

    def __init__(self):
        self.tasks = []

    def enqueue(self, task):
        self.tasks.append(task)

    def run(self, task):
        self.tasks.remove(task)
        result = task.function()
        if not task.is_cancelled():
            task.callback(result)


@pytest.fixture
def task_queue(qapp, monkeypatch):
    queue = _TaskQueue()
    monkeypatch.setattr(async_loader, "get_task_queue", lambda: queue)
    return queue


def _task(task_id, folder_id, name):
    return TaskItem(
        task_id=task_id,
        name=name,
        label=None,
        task_type="Generic",
        task_type_order=0,
        parent_id=folder_id,
        tags=[],
        status="Not ready",
        full_label=name,
    )


class _Controller:
    def __init__(self):
        self.tasks_by_folder = {
            "f1": [_task("t1", "f1", "modeling")],
            "f2": [_task("t2", "f2", "compositing")],
        }
        self.folders = {
            "f1": FolderItem(
                "f1", None, "f1", "/f1", "Folder", "F1", "Not ready"
            ),
        }

    def get_task_items(self, project_name, folder_id, sender=None):
        return self.tasks_by_folder[folder_id]

    def get_folder_items(self, project_name, sender=None):
        return self.folders


def _task_names(model):
    return [
        model.index(row, 0).data(ITEM_NAME_ROLE)
        for row in range(model.rowCount())
    ]


def test_tasks_of_latest_folder_win(task_queue):
    model = TasksQtModel(_Controller())
    refreshed = []
    model.refreshed.connect(lambda: refreshed.append(True))

    model.set_context("demo", "f1")
    first = task_queue.tasks[-1]
    first_result = first.function()
    model.set_context("demo", "f2")
    assert model.is_refreshing

    # Result for 'f1' arrives after 'f2' was requested
    first.callback(first_result)
    assert refreshed == []

    task_queue.run(task_queue.tasks[-1])
    assert _task_names(model) == ["compositing"]
    assert refreshed == [True]
    assert not model.is_refreshing


def test_deselected_folder_shows_invalid_selection(task_queue):
    model = TasksQtModel(_Controller())
    model.set_context("demo", "f1")
    task_queue.run(task_queue.tasks[-1])

    model.set_context("demo", None)

    assert not model.is_loading()
    assert model.rowCount() == 1
    assert model.index(0, 0).data() == "Select a folder"


def test_folders_model_emits_refreshed_after_load(task_queue):
    model = FoldersQtModel(_Controller())
    refreshed = []
    model.refreshed.connect(lambda: refreshed.append(model.is_refreshing))

    model.set_project_name("demo")
    assert model.is_refreshing
    assert model.is_loading()
    task_queue.run(task_queue.tasks[-1])

    assert refreshed == [False]
    assert model.has_content
    assert model.get_item_id_by_path("/f1") == "f1"


def test_run_in_main_thread_from_worker(qtbot):
    called_in = []
    worker = threading.Thread(
        target=lambda: run_in_main_thread(
            lambda: called_in.append(threading.current_thread())
        )
    )
    worker.start()
    worker.join()

    qtbot.waitUntil(lambda: bool(called_in), timeout=5000)
    assert called_in == [threading.main_thread()]


def test_run_in_main_thread_is_direct_in_main_thread(qapp):
    called = []
    run_in_main_thread(lambda: called.append(True))
    assert called == [True]


def test_status_column_has_real_items(task_queue):
    model = FoldersQtModel(_Controller())
    model.set_project_name("demo")
    task_queue.run(task_queue.tasks[-1])

    status_index = model.index(0, 1)
    assert status_index.data(QtCore.Qt.ToolTipRole) == "Not ready"
    assert model.flags(status_index) & QtCore.Qt.ItemIsSelectable
