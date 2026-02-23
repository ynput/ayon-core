import os
from typing import Optional, Any

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import get_ayon_launcher_args, run_detached_process

from ayon_core.pipeline.actions import (
    LoaderSimpleActionPlugin,
    LoaderActionSelection,
    LoaderActionResult,
)


class PushToProject(LoaderSimpleActionPlugin):
    identifier = "core.push-to-project"
    label = "Push to project"
    order = 35
    icon = {
        "type": "material-symbols",
        "name": "send",
        "color": "#d8d8d8",
    }

    def is_compatible(
        self, selection: LoaderActionSelection
    ) -> bool:
        if not selection.versions_selected():
            return False

        version_ids = set(selection.selected_ids)
        product_ids = {
            product["id"]
            for product in selection.entities.get_versions_products(
                version_ids
            )
        }
        folder_ids = {
            folder["id"]
            for folder in selection.entities.get_products_folders(
                product_ids
            )
        }

        if len(folder_ids) == 1:
            return True
        return False

    def execute_simple_action(
        self,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        push_tool_script_path = os.path.join(
            AYON_CORE_ROOT,
            "tools",
            "push_to_project",
            "main.py"
        )

        args = get_ayon_launcher_args(
            push_tool_script_path,
            "--project", selection.project_name,
            "--versions", ",".join(selection.selected_ids)
        )
        run_detached_process(args)
        return LoaderActionResult(
            message="Push to project tool opened...",
            success=True,
        )
