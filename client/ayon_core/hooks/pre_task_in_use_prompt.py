from __future__ import annotations

import os
import json
import tempfile

from ayon_applications import (
    PreLaunchHook,
    LaunchTypes,
    ApplicationLaunchFailed,
)

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import is_headless_mode_enabled, run_ayon_launcher_process
from ayon_core.pipeline.workfile.task_usage import (
    ACKNOWLEDGED_SESSIONS_ENV_KEY,
    TaskUsageItem,
    get_task_usage_settings,
    get_other_users_task_usage_items,
)


class TaskInUsePrompt(PreLaunchHook):
    """Ask user if wants to launch application on a task that is in use.

    Other users working on the task are shown to the user who can cancel
    the launch. Confirmed sessions are passed to the launched application,
    so the user is not notified about them again there.

    The prompt is skipped for farm, remote and automated launches and in
    headless mode.
    """
    # After 'GlobalHostDataHook' which prepares context entities and before
    #   hooks that do changes on disk
    order = -90
    launch_types = {LaunchTypes.local}

    def execute(self) -> None:
        if is_headless_mode_enabled() or not self.host_name:
            return

        project_name = self.data.get("project_name")
        task_entity = self.data.get("task_entity")
        if not project_name or not task_entity:
            return

        settings = get_task_usage_settings(
            project_name,
            self.host_name,
            task_entity["taskType"],
            task_entity["name"],
            project_settings=self.data.get("project_settings"),
        )
        if not settings.enabled:
            return

        try:
            items = get_other_users_task_usage_items(
                project_name, task_entity["id"]
            )
        except Exception:
            self.log.warning(
                "Failed to receive task in-use information.", exc_info=True
            )
            return

        if not items:
            return

        if not self._confirm(items):
            usernames = ", ".join(sorted({item.username for item in items}))
            raise ApplicationLaunchFailed(
                "Launch was cancelled."
                f" Task '{task_entity['name']}' is in use by {usernames}."
            )

        self.launch_context.env[ACKNOWLEDGED_SESSIONS_ENV_KEY] = ",".join(
            item.session_id for item in items
        )

    def _confirm(self, items: list[TaskUsageItem]) -> bool:
        """Ask user in a subprocess with the dialog.

        The launch is not blocked if the dialog fails for any reason.

        Returns:
            bool: User wants to launch the application.

        """
        script_path = os.path.join(
            AYON_CORE_ROOT, "scripts", "task_in_use_prompt.py"
        )
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = tmp.name
            json.dump({"items": [item.to_data() for item in items]}, tmp)

        try:
            run_ayon_launcher_process(
                "--skip-bootstrap",
                script_path,
                tmp_path,
                add_sys_paths=True,
                creationflags=0,
            )
            with open(tmp_path, "r") as stream:
                return bool(json.load(stream).get("confirmed", True))

        except Exception:
            self.log.warning(
                "Failed to show task in-use prompt.", exc_info=True
            )
            return True

        finally:
            os.remove(tmp_path)
