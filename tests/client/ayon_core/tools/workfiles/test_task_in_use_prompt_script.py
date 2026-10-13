"""Test script that shows task in-use prompt before application launch."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("qtpy")

REPO_ROOT = Path(__file__).resolve().parents[5]
CLIENT_ROOT = REPO_ROOT / "client"
SCRIPT_PATH = CLIENT_ROOT / "ayon_core" / "scripts" / "task_in_use_prompt.py"

# Run the script with a button clicked instead of the user
_RUN_SCRIPT = """
import runpy
import sys

from qtpy import QtCore, QtWidgets

BUTTON, SCRIPT_PATH = sys.argv[1], sys.argv[2]


def exec_(self):
    def click():
        for button in self.findChildren(QtWidgets.QAbstractButton):
            if button.text() == BUTTON and not button.isHidden():
                button.click()
                return
        self.reject()

    QtCore.QTimer.singleShot(100, click)
    loop = QtCore.QEventLoop()
    self.finished.connect(loop.quit)
    self.show()
    loop.exec_()
    return self.result()


QtWidgets.QDialog.exec_ = exec_
runpy.run_path(SCRIPT_PATH, run_name="__main__")
"""

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


@pytest.mark.parametrize(
    "button, workfile, expected",
    [
        (
            "Version up",
            "sh010_anim_v001.ma",
            {"confirmed": True, "version_up": True},
        ),
        (
            "Launch anyway",
            "sh010_anim_v001.ma",
            {"confirmed": True, "version_up": False},
        ),
        (
            "Cancel",
            "sh010_anim_v001.ma",
            {"confirmed": False, "version_up": False},
        ),
        # Version up is not offered for a different workfile, the dialog
        #   is rejected if the button is not available
        (
            "Version up",
            "sh010_anim_v002.ma",
            {"confirmed": False, "version_up": False},
        ),
    ]
)
def test_prompt_script(tmp_path, button, workfile, expected):
    """The script stores answer of the user and ends correctly.

    The process used to crash on exit because of threads that load avatars
    of users. Failed process was handled as if the user did not answer, so
    the application was launched with the original workfile.
    """
    json_path = tmp_path / f"prompt_{button.replace(' ', '_')}_{workfile}.json"
    json_path.write_text(
        json.dumps({"items": [_SESSION], "workfile": workfile})
    )
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONPATH"] = os.pathsep.join([
        str(CLIENT_ROOT),
        str(CLIENT_ROOT / "ayon_core" / "vendor" / "python"),
        env.get("PYTHONPATH", ""),
    ])
    # Server is not available, names and avatars of users are not received
    env.pop("AYON_SERVER_URL", None)
    env.pop("AYON_API_KEY", None)
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            _RUN_SCRIPT,
            button,
            str(SCRIPT_PATH),
            str(json_path),
        ],
        env=env,
        capture_output=True,
        timeout=120,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    assert json.loads(json_path.read_text()) == expected
