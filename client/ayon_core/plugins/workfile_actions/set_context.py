from __future__ import annotations

from typing import Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
)


class SetContextAction(WorkfileSimpleActionPlugin):
    """Change current context of the host to the selected task.

    Only the context is changed, the current workfile stays opened as is.
        Disabled by default, can be enabled in settings.
    """
    identifier = "core.set-context"
    settings_category = "core"
    # Disabled if settings of the plugin are not available
    enabled = False

    label = "Set context"
    order = 50
    icon = MaterialSymbolsIcon("my_location")
    tooltip = "Change current context to the selected task"
    description = (
        "Change current context of the application to the selected task."
        " The opened workfile is not changed."
    )

    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        if not selection.folder_id or not selection.task_id:
            return False

        folder_entity = selection.get_folder_entity()
        task_entity = selection.get_task_entity()
        if not folder_entity or not task_entity:
            return False

        # Hide the action if the task is already the current context
        context = self.host.get_current_context()
        return (
            context["folder_path"] != folder_entity["path"]
            or context["task_name"] != task_entity["name"]
        )

    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> WorkfileActionResult | None:
        folder_entity = selection.get_folder_entity()
        task_entity = selection.get_task_entity()
        if not folder_entity or not task_entity:
            return WorkfileActionResult(
                "Failed to find folder and task of the selection.",
                success=False,
            )

        self.host.set_current_context(
            folder_entity,
            task_entity,
            project_entity=selection.get_project_entity(),
            anatomy=selection.get_project_anatomy(),
        )
        task_label = task_entity.get("label") or task_entity["name"]
        return WorkfileActionResult(
            f"Context changed to {folder_entity['path']} > {task_label}",
            refresh=True,
        )
