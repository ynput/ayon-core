"""Loader folder action: mirror folder hierarchy to another project."""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from qtpy import QtWidgets

from ayon_core.pipeline.actions import (
    LoaderActionItem,
    LoaderActionPlugin,
    LoaderActionResult,
    LoaderActionSelection,
)
from ayon_core.tools.push_to_project.models.mirror_folders import (
    MirrorFoldersError,
    mirror_folder_subtree,
)
from ayon_core.tools.push_to_project.ui.mirror_destination_dialog import (
    MirrorFoldersDestinationDialog,
)


class MirrorFoldersToProject(LoaderActionPlugin):
    """Copy folder structure from Loader selection into a destination project."""

    identifier = "core.mirror-folders-to-project"
    label = "Mirror folders to project…"
    order = 36
    selection_entity_types: ClassVar = frozenset({"folder"})

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        if not selection.folders_selected():
            return []
        folder_ids = sorted(selection.selected_ids)
        return [
            LoaderActionItem(
                label=self.label,
                group_label=None,
                order=self.order,
                data={"folder_ids": folder_ids},
                tooltip=(
                    "Create matching folders (and optionally tasks) in "
                    "another project."
                ),
                icon={
                    "type": "material-symbols",
                    "name": "drive_file_move",
                    "color": "#cccccc",
                },
            )
        ]

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: Optional[dict[str, Any]],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        if not selection.folders_selected():
            return LoaderActionResult(
                message="No folders selected.",
                success=False,
            )

        folder_ids = (data or {}).get("folder_ids")
        if not folder_ids:
            folder_ids = list(selection.selected_ids)
        if not folder_ids:
            return LoaderActionResult(
                message="No folder ids for mirror.",
                success=False,
            )

        dialog = MirrorFoldersDestinationDialog()
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return LoaderActionResult(message="Cancelled.", success=False)

        (
            dest_project,
            dest_folder_id,
            include_tasks,
            recursive,
        ) = dialog.get_values()

        if not dest_project:
            return LoaderActionResult(
                message="Select a destination project.",
                success=False,
            )

        try:
            mirror_folder_subtree(
                selection.project_name,
                list(folder_ids),
                dest_project,
                dest_folder_id,
                include_tasks=include_tasks,
                include_descendants=recursive,
            )
        except MirrorFoldersError as exc:
            self.log.warning("Mirror folders failed: %s", exc)
            return LoaderActionResult(message=str(exc), success=False)
        except NotImplementedError as exc:
            return LoaderActionResult(message=str(exc), success=False)

        return LoaderActionResult(
            message="Folders mirrored to {}.".format(dest_project),
            success=True,
        )
