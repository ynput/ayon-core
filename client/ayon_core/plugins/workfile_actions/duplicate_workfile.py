from __future__ import annotations

from typing import Optional, Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
)


class DuplicateWorkfileAction(WorkfileSimpleActionPlugin):
    """Duplicate selected workfile.

    The workfiles tool does ask for the version and comment of the new
        workfile.
    """
    identifier = "core.duplicate-workfile"
    settings_category = "core"

    label = "Duplicate"
    order = 30
    icon = MaterialSymbolsIcon("file_copy")
    tooltip = "Duplicate selected workfile"
    description = (
        "Copy the selected workfile to a different version"
        " or with a different comment."
    )
    # Available only in the context menu
    quick_action = False

    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        if not selection.is_workarea() or not selection.has_workfile():
            return False

        workfile_info = selection.workfile_info
        return workfile_info is None or workfile_info.available

    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        self.request_duplicate_workfile(selection.filepath)
        return None
