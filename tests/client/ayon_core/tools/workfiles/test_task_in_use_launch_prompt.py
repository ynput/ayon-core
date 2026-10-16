"""Test task in-use prompt shown before an application is launched."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from qtpy import QtWidgets  # noqa: E402

from ayon_core.pipeline.workfile import task_usage  # noqa: E402
from ayon_core.pipeline.workfile.task_usage import (  # noqa: E402
    TaskUsageItem,
)
from ayon_core.tools.workfiles.widgets import (  # noqa: E402
    task_in_use_dialog,
)
from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (  # noqa: E402, E501
    ask_to_launch_on_task_in_use,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
CLIENT_ROOT = REPO_ROOT / "client"

_SESSION = {
    "session_id": "other-user",
    "username": "artist2",
    "machine": "machine",
    "site_id": "site-1",
    "host_name": "maya",
    "workfile": "sh010_anim_v001.ma",
    "opened_at": "2026-01-01T12:00:00+00:00",
    "updated_at": "2026-01-01T12:00:00+00:00",
}

# Click a button of the dialog instead of the user
_CLICK_BUTTON = """
def click_button(dialog, label):
    for button in dialog.findChildren(QtWidgets.QAbstractButton):
        if button.text() == label and not button.isHidden():
            button.click()
            return dialog.result()
    dialog.reject()
    return dialog.result()
"""
exec(_CLICK_BUTTON)


@pytest.fixture
def clicked_button(qtbot, monkeypatch):
    """Label of button that is clicked when the dialog is executed."""
    label = ["Launch anyway"]
    monkeypatch.setattr(
        QtWidgets.QDialog,
        "exec_",
        lambda dialog: click_button(dialog, label[0]),  # noqa: F821
    )
    monkeypatch.setattr(
        task_usage, "get_task_usage_user_full_names", lambda items: {}
    )
    return label


@pytest.mark.parametrize(
    "button, workfile, expected",
    [
        ("Version up", "/work/sh010_anim_v001.ma", (True, True)),
        ("Launch anyway", "/work/sh010_anim_v001.ma", (True, False)),
        ("Cancel", "/work/sh010_anim_v001.ma", (False, False)),
        # Version up is not offered for a different workfile, the dialog
        #   is rejected if the button is not available
        ("Version up", "/work/sh010_anim_v002.ma", (False, False)),
        ("Version up", None, (False, False)),
        ("Launch anyway", None, (True, False)),
    ]
)
def test_ask_to_launch(clicked_button, button, workfile, expected):
    clicked_button[0] = button
    items = [TaskUsageItem(**_SESSION)]
    assert ask_to_launch_on_task_in_use(items, workfile) == expected


def test_ask_to_launch_in_other_thread(clicked_button):
    """Dialog can't be shown from a thread without Qt application."""
    results = []
    thread = threading.Thread(
        target=lambda: results.append(
            ask_to_launch_on_task_in_use([TaskUsageItem(**_SESSION)])
        )
    )
    thread.start()
    thread.join(10)
    assert results == [None]


def test_ask_to_launch_without_display(clicked_button, monkeypatch):
    """Qt application is not created if it could not show anything."""
    monkeypatch.setattr(
        task_in_use_dialog.QtWidgets.QApplication,
        "instance",
        staticmethod(lambda: None),
    )
    monkeypatch.setattr(
        task_in_use_dialog.platform, "system", lambda: "Linux"
    )
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert not task_in_use_dialog._can_show_dialog()

    monkeypatch.setenv("DISPLAY", ":0")
    assert task_in_use_dialog._can_show_dialog()


# Process that only launches an application does not have Qt application
_LAUNCH_PROCESS = """
import json
import sys

from qtpy import QtWidgets

from ayon_core.pipeline.workfile import task_usage
from ayon_core.pipeline.workfile.task_usage import TaskUsageItem
from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (
    ask_to_launch_on_task_in_use,
)
{click_button}

label, session, workfile = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3]
QtWidgets.QDialog.exec_ = lambda dialog: click_button(dialog, label)
task_usage.get_task_usage_user_full_names = lambda items: {{}}
assert QtWidgets.QApplication.instance() is None
answer = ask_to_launch_on_task_in_use([TaskUsageItem(**session)], workfile)
print(json.dumps(answer))
""".format(click_button=_CLICK_BUTTON)


@pytest.mark.parametrize(
    "button, expected",
    [
        ("Version up", [True, True]),
        ("Launch anyway", [True, False]),
        ("Cancel", [False, False]),
    ]
)
def test_ask_to_launch_in_launch_process(button, expected):
    """The process gets the answer and ends correctly.

    Process used to crash on exit because threads that load avatars of
    users were still running.
    """
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = os.pathsep.join([
        str(CLIENT_ROOT),
        str(CLIENT_ROOT / "ayon_core" / "vendor" / "python"),
        env.get("PYTHONPATH", ""),
    ])
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            _LAUNCH_PROCESS,
            button,
            json.dumps(_SESSION),
            "/work/sh010_anim_v001.ma",
        ],
        env=env,
        capture_output=True,
        timeout=120,
    )
    stdout = process.stdout.decode(errors="replace")
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    assert json.loads(stdout.strip().splitlines()[-1]) == expected
