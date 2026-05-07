"""Open project folder on disk from Loader hierarchy (folder selection)."""

from __future__ import annotations

import os
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


def _deepest_existing_dir(start: str) -> Optional[str]:
    """Walk parents until an existing directory is found."""
    current = os.path.normpath(start)
    visited = set()
    while current and current not in visited:
        visited.add(current)
        if os.path.isdir(current):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return None


def _resolve_open_directory(candidate: str) -> Optional[str]:
    """Match launcher OpenTaskPath: prefer exists; normalize files to parent."""
    if not candidate:
        return None
    n = os.path.normpath(candidate)
    if os.path.isdir(n):
        return n
    if os.path.isfile(n):
        parent = os.path.dirname(n)
        if os.path.isdir(parent):
            return parent
        return _deepest_existing_dir(parent)
    return _deepest_existing_dir(n)


def _open_path_in_os_explorer(path: str) -> None:
    """Open a directory in the platform file manager."""
    if sys.platform.startswith("darwin"):
        subprocess.call(("open", path))
    elif os.name == "nt":
        os.startfile(path)
    elif os.name == "posix":
        subprocess.call(("xdg-open", path))
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")


def _folder_workdir_on_disk(
    selection: LoaderActionSelection,
    folder_id: str,
) -> tuple[Optional[str], list[str]]:
    """Resolve work/default/folder anatomy path; nearest existing dir on disk.

    Returns:
        Tuple of (path to open or None, normalized candidates tried).
    """
    attempted: list[str] = []
    folders = selection.entities.get_folders({folder_id})
    if not folders:
        return None, attempted

    folder_entity = folders[0]
    project_entity = selection.entities.get_project()
    anatomy = selection.get_project_anatomy()
    data = get_template_data(project_entity, folder_entity, None)
    template = anatomy.get_template_item("work", "default", "folder")

    def try_pass(template_data: dict[str, Any]) -> Optional[str]:
        workdir = template.format(template_data)
        valid = _find_first_filled_path(str(workdir))
        if not valid:
            return None
        n = os.path.normpath(valid)
        attempted.append(n)
        return _resolve_open_directory(n)

    result = try_pass(data)
    if result:
        return result, attempted

    data.pop("task", None)
    result = try_pass(data)
    if result:
        return result, attempted

    return None, attempted


class OpenHierarchyFolderAction(LoaderActionPlugin):
    """Open work-directory folder on disk for Loader hierarchy folder selection.

    Identifier must differ from ``core.open-folder`` in ``open_file.py`` (opens
    the containing folder for a *representation* path); duplicate ids break
    discovery, and ``REPRESENTATION_PANEL_ONLY_ACTION_IDENTIFIERS`` filters the
    representation plugin id from non-representation menus.
    """

    identifier = "core.open-hierarchy-folder"
    selection_entity_types: ClassVar = frozenset({"folder"})

    _TOOLTIP = (
        "Opens the resolved work-directory folder on disk (work/default/folder "
        "anatomy), or the nearest existing parent folder if the leaf path is "
        "not created yet."
    )

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        if not selection.folders_selected():
            return []
        folders = selection.get_selected_folder_entities()
        if len(folders) != 1:
            return []

        folder = folders[0]
        return [
            LoaderActionItem(
                label="Open Folder",
                group_label=None,
                order=14,
                data={"folder_id": folder["id"]},
                tooltip=self._TOOLTIP,
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

        disk_path, attempted = _folder_workdir_on_disk(selection, folder_id)
        if not disk_path:
            for path in attempted:
                self.log.debug(
                    "OpenHierarchyFolderAction: no directory on disk at or above %s",
                    path,
                )
            return LoaderActionResult(
                "Could not find an existing folder on disk for this hierarchy "
                "(check anatomy work/default/folder templates and project "
                "roots). See log for resolved path candidates.",
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
