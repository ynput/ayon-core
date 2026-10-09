from __future__ import annotations

import os
from typing import Optional, Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileActionPlugin,
    WorkfileActionItem,
    WorkfileActionSelection,
    WorkfileActionResult,
)


class CopyFileAction(WorkfileActionPlugin):
    """Copy path of selected workfile, or the workfile itself, to clipboard.

    Copied file can be pasted e.g. to a file browser or to a chat
        application.
    """
    identifier = "core.copy-file"
    settings_category = "core"

    order = 40
    # Available only in the context menu
    quick_action = False

    def get_action_items(
        self, selection: WorkfileActionSelection
    ) -> list[WorkfileActionItem]:
        if not selection.has_workfile() or not selection.filepath:
            return []

        return [
            WorkfileActionItem(
                label="Copy file path",
                order=self.order,
                icon=MaterialSymbolsIcon("content_copy"),
                tooltip="Copy path of the workfile to clipboard",
                quick_action=self.quick_action,
                data={"action": "copy-path"},
            ),
            WorkfileActionItem(
                label="Copy file",
                order=self.order + 1,
                icon=MaterialSymbolsIcon("file_copy"),
                tooltip="Copy the workfile to clipboard",
                description="The file can be pasted e.g. to a file browser.",
                quick_action=self.quick_action,
                data={"action": "copy-file"},
            ),
        ]

    def execute_action(
        self,
        selection: WorkfileActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        from qtpy import QtWidgets, QtCore

        path = os.path.normpath(selection.filepath)
        clipboard = QtWidgets.QApplication.clipboard()
        if not clipboard:
            return WorkfileActionResult(
                "Failed to copy to clipboard.",
                success=False,
            )

        if data["action"] == "copy-path":
            clipboard.setText(path)
            self.log.info(f"Added file path to clipboard: {path}")
            return WorkfileActionResult("Path stored to clipboard...")

        # Build mime data for clipboard
        mime_data = QtCore.QMimeData()
        mime_data.setUrls([QtCore.QUrl.fromLocalFile(path)])
        clipboard.setMimeData(mime_data)
        self.log.info(f"Added file to clipboard: {path}")
        return WorkfileActionResult("File added to clipboard...")
