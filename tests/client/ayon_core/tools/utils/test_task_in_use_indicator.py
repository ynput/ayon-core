"""Test indicator of workfiles that are in use."""
from __future__ import annotations

import pytest

pytest.importorskip("pytestqt")

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

from ayon_core.pipeline.workfile.task_usage import (  # noqa: E402
    TaskUsageItem,
)
from ayon_core.tools.utils import task_in_use_indicator  # noqa: E402
from ayon_core.tools.utils.task_in_use_indicator import (  # noqa: E402
    OTHER_USER_COLOR,
    SAME_USER_COLOR,
    TaskInUseIndicator,
    group_items_by_workfile,
    is_in_use_by_user,
)

USERNAME_ROLE = QtCore.Qt.UserRole + 1


def _item(
    session_id: str, username: str, workfile: str | None
) -> TaskUsageItem:
    return TaskUsageItem(
        session_id=session_id,
        username=username,
        machine="machine",
        site_id="site-1",
        host_name="maya",
        workfile=workfile,
        opened_at="2026-01-01T12:00:00+00:00",
        updated_at="2026-01-01T12:00:00+00:00",
    )


def test_group_items_by_workfile():
    first = _item("a", "artist1", "sh010_anim_v001.ma")
    same_file = _item("b", "artist2", "SH010_anim_v001.ma")
    other_file = _item("c", "artist3", "sh010_anim_v002.ma")
    no_file = _item("d", "artist4", None)

    assert group_items_by_workfile(
        [first, same_file, other_file, no_file]
    ) == {
        "sh010_anim_v001.ma": [first, same_file],
        "sh010_anim_v002.ma": [other_file],
    }
    assert group_items_by_workfile([]) == {}


def test_is_in_use_by_user():
    items = [_item("a", "artist1", "a.ma"), _item("b", "artist2", "a.ma")]
    assert is_in_use_by_user(items, "artist2")
    assert not is_in_use_by_user(items, "artist3")
    assert not is_in_use_by_user(items, None)


@pytest.fixture
def indicator(qtbot, monkeypatch):
    """Indicator on a view with 2 workfiles, without server requests."""
    requests = []

    class _TaskQueue:
        def clear_context_tasks(self, context_id):
            pass

        def enqueue(self, task):
            requests.append(task)

    monkeypatch.setattr(
        task_in_use_indicator, "get_task_queue", lambda: _TaskQueue()
    )

    view = QtWidgets.QTreeView()
    qtbot.addWidget(view)
    model = QtGui.QStandardItemModel()
    for filename, username in (
        ("sh010_anim_v001.ma", "artist1"),
        ("sh010_anim_v002.ma", "artist1"),
    ):
        name_item = QtGui.QStandardItem(filename)
        name_item.setData(username, USERNAME_ROLE)
        model.appendRow([name_item, QtGui.QStandardItem(username)])
    view.setModel(model)
    return TaskInUseIndicator(view, 1, USERNAME_ROLE), model, requests


def test_indicator_requests_in_background(indicator, qtbot):
    indicator, model, requests = indicator

    session = _item("a", "artist2", "SH010_anim_v002.ma")
    fetched = []

    def _fetch():
        fetched.append(1)
        return [session], {"artist2": "Artist Two"}

    indicator.set_context("task-1", _fetch)
    # Nothing is requested in the call that changes the context
    assert requests == [] and fetched == []
    qtbot.waitUntil(lambda: len(requests) == 1, timeout=2000)
    # The function is called by the task queue in a worker thread
    assert fetched == []
    result = requests[0].function()
    assert fetched == [1]

    with qtbot.waitSignal(indicator.sessions_changed, timeout=1000):
        requests[0].callback(result)
    assert indicator.get_sessions(model.index(0, 1)) == []
    assert indicator.get_sessions(model.index(1, 1)) == [session]
    assert indicator.get_sessions(model.index(1, 0)) == [session]


def test_indicator_ignores_outdated_and_failed_requests(indicator, qtbot):
    indicator, model, requests = indicator
    session = _item("a", "artist2", "sh010_anim_v001.ma")
    result = ([session], {})

    def _fetch():
        return result

    indicator.set_context("task-1", _fetch)
    qtbot.waitUntil(lambda: len(requests) == 1, timeout=2000)
    # Task did change before the sessions were received
    indicator.set_context("task-2", _fetch)
    requests[0].callback(result)
    assert indicator.get_sessions(model.index(0, 1)) == []

    qtbot.waitUntil(lambda: len(requests) == 2, timeout=2000)
    requests[1].callback(result)
    assert indicator.get_sessions(model.index(0, 1)) == [session]
    # Failed request keeps known sessions
    indicator.refresh()
    qtbot.waitUntil(lambda: len(requests) == 3, timeout=2000)
    requests[2].callback(None)
    assert indicator.get_sessions(model.index(0, 1)) == [session]

    # Sessions are dropped when the task changes
    indicator.set_context(None)
    assert indicator.get_sessions(model.index(0, 1)) == []
    # Nothing is requested without a task
    qtbot.wait(150)
    assert len(requests) == 3


def test_indicator_failed_fetch_function(indicator, qtbot):
    indicator, model, requests = indicator

    def _failing():
        raise RuntimeError("Server is not available")

    indicator.set_context("task-1", _failing)
    qtbot.waitUntil(lambda: len(requests) == 1, timeout=2000)
    assert requests[0].function() is None


def test_indicator_ring_color(indicator):
    indicator, model, _ = indicator
    indicator._items_by_filename = {
        "sh010_anim_v001.ma": [_item("a", "artist1", "sh010_anim_v001.ma")],
        "sh010_anim_v002.ma": [_item("b", "artist2", "sh010_anim_v002.ma")],
    }
    colors = []
    indicator._get_ring_pixmap = lambda icon, color: (
        colors.append(color) or QtGui.QPixmap(4, 4)
    )
    pixmap = QtGui.QPixmap(20, 20)
    pixmap.fill(QtCore.Qt.black)
    for row in range(2):
        option = QtWidgets.QStyleOptionViewItem()
        option.icon = QtGui.QIcon(pixmap)
        indicator.decorate_avatar(option, model.index(row, 1))
    # Workfile opened by its author, workfile opened by other user
    assert colors == [SAME_USER_COLOR, OTHER_USER_COLOR]
