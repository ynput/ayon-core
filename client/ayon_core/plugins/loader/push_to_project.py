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
    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        version_ids = set()
        if selection.selected_type == "version":
            version_ids = set(selection.selected_ids)

        output = []
        if len(version_ids) == 1:
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

        version_id = next(iter(entity_ids))

        args = get_ayon_launcher_args(
            push_tool_script_path,
            "--project", selection.project_name,
            "--version", version_id
        )
        run_detached_process(args)
        return LoaderActionResult(
            message="Push to project tool opened...",
            success=True,
        )
