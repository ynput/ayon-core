"""Tests for the user avatars of workfiles in the launcher."""

from __future__ import annotations

import threading

import pytest
from qtpy import QtCore, QtWidgets

from ayon_core.tools.common_models import UserItem
from ayon_core.tools.launcher.abstract import WorkfileItem
from ayon_core.tools.launcher.models import workfiles as backend_workfiles
from ayon_core.tools.launcher.ui import workfiles_page
from ayon_core.ui.components import user_avatars
from ayon_core.ui.components.task_queue import shutdown_task_queue


def _workfile_item(idx: int, updated_by: str | None) -> WorkfileItem:
    return WorkfileItem(
        workfile_id=str(idx),
        filename=f"sh010_comp_v{idx:03d}.nk",
        exists=True,
        host_name="nuke",
        icon=None,
        version=idx,
        updated_at_time=1000.0 * idx,
        file_size=1024,
        updated_by=updated_by,
    )


class _Controller:
    def __init__(self, workfile_items: list[WorkfileItem]) -> None:
        self.workfile_items = workfile_items
        self.users_thread_ids: list[int] = []

    def register_event_callback(self, topic, callback) -> None:
        pass

    def get_grouped_host_names(self) -> list[str]:
        return []

    def get_workfile_items(self, project_name, task_id):
        return self.workfile_items

    def get_user_items_by_name(self, project_name):
        self.users_thread_ids.append(threading.get_ident())
        return {"roy": UserItem("roy", "Roy Nieterau", None, None, True)}


@pytest.fixture
def task_queue(qapp):
    yield
    shutdown_task_queue()


@pytest.fixture
def avatar_tasks(monkeypatch):
    """Avatars are requested, but never downloaded."""
    tasks = []

    class _Queue:
        def enqueue(self, task) -> None:
            tasks.append(task)

    monkeypatch.setattr(user_avatars, "get_task_queue", _Queue)
    return tasks


def _refresh(qtbot, model: workfiles_page.WorkfilesModel) -> None:
    with qtbot.waitSignal(model.refreshed, timeout=5000):
        model._on_selection_task_changed(
            {"project_name": "demo", "folder_id": "f", "task_id": "t"}
        )


def _index_by_filename(model, filename: str, column: int):
    for row in range(model.rowCount()):
        if model.index(row, 0).data(QtCore.Qt.DisplayRole) == filename:
            return model.index(row, column)
    raise AssertionError(f"Missing row of {filename}")


def test_modified_column_has_user_of_last_change(qtbot, task_queue):
    controller = _Controller([
        _workfile_item(1, "roy"),
        _workfile_item(2, "unknown.user"),
        _workfile_item(3, None),
    ])
    model = workfiles_page.WorkfilesModel(controller)
    _refresh(qtbot, model)

    index = _index_by_filename(model, "sh010_comp_v001.nk", 1)
    # Timestamp is still what the column displays and sorts by
    assert index.data(QtCore.Qt.DisplayRole) == 1000.0
    assert index.data(workfiles_page.UPDATED_BY_ROLE) == "roy"
    assert index.data(QtCore.Qt.ToolTipRole) == "Roy Nieterau"

    # Username is used for a user that is not on the project anymore
    index = _index_by_filename(model, "sh010_comp_v002.nk", 1)
    assert index.data(QtCore.Qt.ToolTipRole) == "unknown.user"

    index = _index_by_filename(model, "sh010_comp_v003.nk", 1)
    assert index.data(workfiles_page.UPDATED_BY_ROLE) is None
    assert index.data(QtCore.Qt.ToolTipRole) is None
    # Other columns have no tooltip
    index = _index_by_filename(model, "sh010_comp_v001.nk", 0)
    assert index.data(QtCore.Qt.ToolTipRole) is None

    # Users were queried outside of the main thread
    assert controller.users_thread_ids
    assert threading.get_ident() not in controller.users_thread_ids


def test_users_are_not_queried_without_a_user(qtbot, task_queue):
    controller = _Controller([_workfile_item(1, None)])
    model = workfiles_page.WorkfilesModel(controller)
    _refresh(qtbot, model)

    assert model.rowCount() == 1
    assert controller.users_thread_ids == []


def test_delegate_paints_avatar_in_modified_column(
    qtbot, task_queue, avatar_tasks
):
    controller = _Controller([
        _workfile_item(1, "roy"),
        _workfile_item(2, None),
    ])
    model = workfiles_page.WorkfilesModel(controller)
    _refresh(qtbot, model)
    delegate = workfiles_page.WorkfilesDelegate(
        user_avatars.UserAvatarCache(model)
    )

    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(
        option, _index_by_filename(model, "sh010_comp_v001.nk", 1)
    )
    assert not option.icon.isNull()
    assert option.text
    # The avatar itself is downloaded in the background
    assert [task.name for task in avatar_tasks] == ["fetch_avatar:roy"]

    option = QtWidgets.QStyleOptionViewItem()
    delegate.initStyleOption(
        option, _index_by_filename(model, "sh010_comp_v002.nk", 1)
    )
    assert option.icon.isNull()


def test_backend_fills_user_of_last_change(monkeypatch, tmp_path):
    queried_fields = []

    class _Anatomy:
        def __init__(self, project_name, project_entity=None) -> None:
            pass

        def fill_root(self, rootless_path: str) -> str:
            return rootless_path.replace("{root}", str(tmp_path))

    class _BackendController:
        def get_project_entity(self, project_name):
            return {"name": project_name}

        def get_addons_manager(self):
            return {}

    def get_workfiles_info(project_name, task_ids, fields):
        queried_fields.extend(fields)
        for idx, updated_by in enumerate(("roy", None), 1):
            yield {
                "id": str(idx),
                "path": f"{{root}}/sh010_comp_v{idx:03d}.nk",
                "data": {"host_name": "nuke", "version": idx},
                "updatedAt": None,
                "updatedBy": updated_by,
            }

    monkeypatch.setattr(backend_workfiles, "Anatomy", _Anatomy)
    monkeypatch.setattr(
        backend_workfiles.ayon_api, "get_workfiles_info", get_workfiles_info
    )
    model = backend_workfiles.WorkfilesModel(_BackendController())

    items = model.get_workfile_items("demo", "task-id")

    assert "updatedBy" in queried_fields
    assert [item.updated_by for item in items] == ["roy", None]
