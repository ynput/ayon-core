from __future__ import annotations

import os
from typing import Optional, Any

from ayon_core.lib import open_in_file_browser
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    WorkfileSimpleActionPlugin,
    WorkfileActionSelection,
    WorkfileActionResult,
)


def _find_existing_dir(path: str) -> Optional[str]:
    """Find the closest existing directory of the path."""
    path = os.path.normpath(path)
    while path:
        if os.path.isdir(path):
            return path
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return None


class ExploreHereAction(WorkfileSimpleActionPlugin):
    """Show selected workfile, or the work directory, in file browser."""
    identifier = "core.explore-here"
    settings_category = "core"

    label = "Explore here"
    # Keep the action at the end, same as in launcher
    order = 500
    icon = MaterialSymbolsIcon("folder_open")
    tooltip = "Show in file browser"
    description = (
        "Open file browser at the selected workfile."
        " Work directory of the task is opened if a workfile is not"
        " selected."
    )

    def is_compatible(self, selection: WorkfileActionSelection) -> bool:
        if selection.has_workfile():
            return bool(selection.filepath)

        # Without selected workfile the only known path is the work directory
        return (
            selection.is_workarea()
            and bool(selection.folder_id)
            and bool(selection.task_id)
        )

    def execute_simple_action(
        self,
        selection: WorkfileActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[WorkfileActionResult]:
        if selection.has_workfile():
            path = selection.filepath
        else:
            path = selection.get_workdir()

        if not path:
            return WorkfileActionResult(
                "Failed to find out which directory to open.",
                success=False,
            )

        if not os.path.exists(path):
            # Fallback to the closest existing directory, e.g. when work
            #   directory was not created yet
            existing_dir = _find_existing_dir(path)
            if existing_dir is None:
                return WorkfileActionResult(
                    f"Path does not exist: {path}",
                    success=False,
                )
            path = existing_dir

        self.log.info(f"Opening in file browser: {path}")
        open_in_file_browser(path)
        return None
