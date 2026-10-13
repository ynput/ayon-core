"""Ask user if wants to work on a task that is in use by other users.

Script is executed as a subprocess before an application is launched. It
receives path to a json file with sessions of other users and stores the
answer of the user to the same file.
"""
from __future__ import annotations

import sys
import json

from qtpy import QtWidgets

from ayon_core.pipeline.workfile.task_usage import (
    TaskUsageItem,
    get_same_workfile_items,
    get_task_usage_user_full_names,
)
from ayon_core.tools.utils import get_ayon_qt_app
from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (
    TaskInUseDialog,
)
from ayon_core.ui.components.task_queue import shutdown_task_queue


def main() -> None:
    json_path = sys.argv[-1]
    with open(json_path, "r") as stream:
        data = json.load(stream)

    items = []
    for item_data in data["items"]:
        item = TaskUsageItem.from_data(item_data)
        if item is not None:
            items.append(item)

    app = get_ayon_qt_app()  # noqa: F841
    dialog = TaskInUseDialog(
        items,
        get_task_usage_user_full_names(items),
        confirm_label="Launch anyway",
        version_up=bool(
            get_same_workfile_items(items, data.get("workfile"))
        ),
    )
    confirmed = dialog.exec_() == QtWidgets.QDialog.Accepted

    with open(json_path, "w") as stream:
        json.dump(
            {
                "confirmed": confirmed,
                "version_up": dialog.is_version_up_requested(),
            },
            stream,
        )

    # Avatars of users are loaded by threads of the shared task queue. It
    #   is stopped when Qt application quits, but the event loop of the
    #   application is not used here. The process would crash on exit
    #   with the threads still running.
    shutdown_task_queue()


if __name__ == "__main__":
    main()
