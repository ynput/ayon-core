"""Open project folder on disk from Loader hierarchy (folder selection)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from string import Formatter
from typing import Any, ClassVar, Optional

from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)
from ayon_core.pipeline.template_data import get_template_data


def _find_first_filled_path(path: str) -> str:
    """Truncate path at first unresolved template-like placeholder segment."""
    if not path:
        return ""

    fields = set()
    for item in Formatter().parse(path):
        _, field_name, format_spec, conversion = item
        if not field_name:
            continue
        conversion = "!{}".format(conversion) if conversion else ""
        format_spec = ":{}".format(format_spec) if format_spec else ""
        orig_key = "{{{}{}{}}}".format(field_name, conversion, format_spec)
        fields.add(orig_key)

    for field in fields:
        path = path.split(field, 1)[0]
    return path


def _open_path_in_os_explorer(path: str) -> None:
    """Open a directory in the platform file manager."""
    if sys.platform.startswith("darwin"):
        subprocess.call(("open", path))
    elif os.name == "nt":
        os.startfile(path)
    elif os.name == "posix":
        subprocess.call(("xdg-open", path))
    else:
        raise RuntimeError(f"Unsupported platform: {platform.system()}")


def _folder_workdir_on_disk(
    selection: LoaderActionSelection,
    folder_id: str,
) -> Optional[str]:
    """Resolve anatomy work-directory folder template for a folder entity."""
    folders = selection.entities.get_folders({folder_id})
    if not folders:
        return None
    folder_entity = folders[0]
    project_entity = selection.entities.get_project()
    anatomy = selection.get_project_anatomy()

    data = get_template_data(project_entity, folder_entity, None)
    template = anatomy.get_template_item("work", "default", "folder")
    workdir = template.format(data)
    valid = _find_first_filled_path(str(workdir))
    if not valid:
        return None
    valid = os.path.normpath(valid)
    if os.path.isdir(valid):
        return valid

    data.pop("task", None)
    workdir = template.format(data)
    valid = _find_first_filled_path(str(workdir))
    if valid:
        valid = os.path.normpath(valid)
        if os.path.isdir(valid):
            return valid
    return None


class OpenFolderAction(LoaderActionPlugin):
    """Open the resolved work folder on disk (demonstrates folder loader actions)."""

    identifier = "core.open-folder"
    selection_entity_types: ClassVar = frozenset({"folder"})

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        if not selection.folders_selected():
            return []
        folders = selection.get_selected_folder_entities()
        if len(folders) != 1:
            return []

        folder = folders[0]
        path = folder.get("path") or ""
        label = path.rstrip("/").rsplit("/", 1)[-1] or path or folder.get(
            "name", "Folder"
        )

        return [
            LoaderActionItem(
                label=label,
                group_label="Folder",
                order=14,
                data={"folder_id": folder["id"]},
                icon={
                    "type": "material-symbols",
                    "name": "folder_open",
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
        if data is None or not selection.folders_selected():
            return LoaderActionResult(
                "No folder action data.",
                success=False,
            )

        folder_id = data.get("folder_id")
        if not folder_id or folder_id not in selection.selected_ids:
            return LoaderActionResult(
                "Folder selection mismatch.",
                success=False,
            )

        disk_path = _folder_workdir_on_disk(selection, folder_id)
        if not disk_path:
            return LoaderActionResult(
                "Could not resolve an existing work folder on disk for this"
                " hierarchy (create the folder or check anatomy templates).",
                success=False,
            )

        self.log.info("Opening folder in explorer: %s", disk_path)
        try:
            _open_path_in_os_explorer(disk_path)
        except Exception as exc:
            self.log.warning("Failed to open folder", exc_info=True)
            return LoaderActionResult(
                f"Failed to open folder: {exc}",
                success=False,
            )

        return LoaderActionResult(
            "Opened folder in file explorer.",
            success=True,
        )
