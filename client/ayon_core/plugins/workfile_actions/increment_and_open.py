from __future__ import annotations

import os
from typing import Any

from ayon_core.host.interfaces import CopyWorkfileOptionalData
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.workfile import copy_workfile_to_context
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
)


class IncrementAndOpenAction(WorkfileSimpleActionPlugin):
    """Duplicate selected workfile to next version and open the copy.

    A user is asked what to do with unsaved changes of the current workfile
        before anything happens, so cancelling does not leave a new version
        on disk. The selected workfile is then copied to the next version
        and the copy is opened.
    """
    identifier = "core.increment-and-open"
    settings_category = "core"

    label = "Increment and open"
    order = 20
    icon = MaterialSymbolsIcon("upgrade")
    tooltip = "Duplicate to next version and open"
    description = (
        "Duplicate the selected workfile to the next available version"
        " and open the duplicated workfile."
    )

    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        if (
            not selection.is_workarea()
            or not selection.has_workfile()
            or not selection.folder_id
            or not selection.task_id
        ):
            return False

        workfile_info = selection.workfile_info
        return workfile_info is None or workfile_info.available

    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> WorkfileActionResult | None:
        src_path = selection.filepath
        if not src_path or not os.path.exists(src_path):
            return WorkfileActionResult(
                "Selected workfile does not exist on disk.",
                success=False,
            )

        folder_entity = selection.get_folder_entity()
        task_entity = selection.get_task_entity()
        if not folder_entity or not task_entity:
            return WorkfileActionResult(
                "Failed to find folder and task of the workfile.",
                success=False,
            )

        # Ask about unsaved changes before the copy is created, cancel of
        #   the form does not trigger the action again
        result = self.ask_to_save_changes(form_values)
        if isinstance(result, WorkfileActionResult):
            return result

        # Keep the comment of the source workfile
        comment = None
        workfile_info = selection.workfile_info
        if workfile_info is not None:
            comment = workfile_info.comment

        copy_workfile_to_context(
            src_path,
            folder_entity,
            task_entity,
            comment=comment,
            open_workfile=True,
            prepared_data=CopyWorkfileOptionalData(
                project_entity=selection.get_project_entity(),
                anatomy=selection.get_project_anatomy(),
                project_settings=selection.get_project_settings(),
            ),
        )
        return WorkfileActionResult(close_tool=True)
