from __future__ import annotations

from typing import Any

import ayon_api

from ayon_core.host.interfaces import CopyWorkfileOptionalData
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
    WorkfileActionSaveAsFormInputs,
    WorkfileActionSaveAsValues,
)


class DuplicateWorkfileAction(WorkfileSimpleActionPlugin):
    """Duplicate selected workfile.

    A user picks the version and comment of the new workfile in the Save As
        dialog of the workfiles tool, the workfile is copied when the dialog
        is accepted.
    """
    identifier = "core.duplicate-workfile"
    settings_category = "core"

    label = "Duplicate"
    order = 30
    icon = MaterialSymbolsIcon("control_point_duplicate")
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
    ) -> WorkfileActionResult | None:
        values = WorkfileActionSaveAsValues.from_form_values(form_values)
        if values is None:
            # Let a user pick the version and comment of the new workfile
            return WorkfileActionResult(
                show_save_as_form=WorkfileActionSaveAsFormInputs(
                    folder_id=selection.folder_id,
                    task_id=selection.task_id,
                    description=f"Copied from: {selection.filepath}",
                )
            )

        folder_entity = selection.get_folder_entity()
        if folder_entity is None or folder_entity["id"] != values.folder_id:
            folder_entity = ayon_api.get_folder_by_id(
                selection.project_name, values.folder_id
            )
        task_entity = selection.get_task_entity()
        if task_entity is None or task_entity["id"] != values.task_id:
            task_entity = ayon_api.get_task_by_id(
                selection.project_name, values.task_id
            )
        if not folder_entity or not task_entity:
            return WorkfileActionResult(
                "Failed to find folder and task of the new workfile.",
                success=False,
            )

        try:
            self.host.copy_workfile(
                selection.filepath,
                values.filepath,
                folder_entity,
                task_entity,
                version=values.version,
                comment=values.comment,
                description=values.description,
                # Duplicated workfile should not be opened
                open_workfile=False,
                prepared_data=CopyWorkfileOptionalData(
                    project_entity=selection.get_project_entity(),
                    anatomy=selection.get_project_anatomy(),
                    project_settings=selection.get_project_settings(),
                    rootless_path=values.rootless_path,
                ),
            )
        except Exception:
            self.log.warning("Duplication of workfile failed", exc_info=True)
            return WorkfileActionResult(
                "Failed to duplicate workfile", success=False
            )

        return WorkfileActionResult("Workfile duplicated").set_redirect(
            task_entity=task_entity, workfile_name=values.filename
        )
