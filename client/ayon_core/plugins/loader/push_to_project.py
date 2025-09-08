import os
from typing import Optional, Any

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import get_ayon_launcher_args, run_detached_process

from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


class PushToProject(LoaderActionPlugin):
    identifier = "core.push-to-project"

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        folder_ids = set()
        version_ids = set()
        if selection.selected_type == "version":
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

        output = []
        if version_ids and len(folder_ids) == 1:
            output.append(
                LoaderActionItem(
                    identifier="core.push-to-project",
                    label="Push to project",
                    order=35,
                    entity_ids=version_ids,
                    entity_type="version",
                    icon={
                        "type": "material-symbols",
                        "name": "send",
                        "color": "#d8d8d8",
                    }
                )
            )
        return output

    def execute_action(
        self,
        identifier: str,
        entity_ids: set[str],
        entity_type: str,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        if len(entity_ids) > 1:
            return LoaderActionResult(
                message="Please select only one version",
                success=False,
            )

        push_tool_script_path = os.path.join(
            AYON_CORE_ROOT,
            "tools",
            "push_to_project",
            "main.py"
        )

        args = get_ayon_launcher_args(
            push_tool_script_path,
            "--project", selection.project_name,
            "--versions", ",".join(entity_ids)
        )
        run_detached_process(args)
        return LoaderActionResult(
            message="Push to project tool opened...",
            success=True,
        )
