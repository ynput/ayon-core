import os
import collections

from typing import Optional, Any

from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


class CopyFileActionPlugin(LoaderActionPlugin):
    """Copy published file path to clipboard"""
    identifier = "core.copy-action"

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        repres = []
        if selection.selected_type == "representation":
            repres = selection.entities.get_representations(
                selection.selected_ids
            )

        if selection.selected_type == "version":
            repres = selection.entities.get_versions_representations(
                selection.selected_ids
            )

        output = []
        if not repres:
            return output

        repre_ids_by_name = collections.defaultdict(set)
        for repre in repres:
            repre_ids_by_name[repre["name"]].add(repre["id"])

        for repre_name, repre_ids in repre_ids_by_name.items():
            output.append(
                LoaderActionItem(
                    identifier="copy-path",
                    label=repre_name,
                    group_label="Copy file path",
                    data={"representation_ids": list(repre_ids)},
                    icon={
                        "type": "material-symbols",
                        "name": "content_copy",
                        "color": "#999999",
                    }
                )
            )
            output.append(
                LoaderActionItem(
                    identifier="copy-file",
                    label=repre_name,
                    group_label="Copy file",
                    data={"representation_ids": list(repre_ids)},
                    icon={
                        "type": "material-symbols",
                        "name": "file_copy",
                        "color": "#999999",
                    }
                )
            )
        return output

    def execute_action(
        self,
        identifier: str,
        selection: LoaderActionSelection,
        data: dict,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        from qtpy import QtWidgets, QtCore

        repre_id = next(iter(data["representation_ids"]))
        repre = next(iter(selection.entities.get_representations({repre_id})))
        path = get_representation_path_with_anatomy(
            repre, selection.get_project_anatomy()
        )
        self.log.info(f"Added file path to clipboard: {path}")

        clipboard = QtWidgets.QApplication.clipboard()
        if not clipboard:
            return LoaderActionResult(
                "Failed to copy file path to clipboard.",
                success=False,
            )

        if identifier == "copy-path":
            # Set to Clipboard
            clipboard.setText(os.path.normpath(path))

            return LoaderActionResult(
                "Path stored to clipboard...",
                success=True,
            )

        # Build mime data for clipboard
        data = QtCore.QMimeData()
        url = QtCore.QUrl.fromLocalFile(path)
        data.setUrls([url])

        # Set to Clipboard
        clipboard.setMimeData(data)

        return LoaderActionResult(
            "File added to clipboard...",
            success=True,
        )
