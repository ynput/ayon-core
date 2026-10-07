from __future__ import annotations

import os
import copy
import json
import shutil
import tempfile
from typing import Optional

from ayon_applications import (
    PreLaunchHook,
    LaunchTypes,
    ApplicationLaunchFailed,
)

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import is_headless_mode_enabled, run_ayon_launcher_process
from ayon_core.pipeline.template_data import get_template_data
from ayon_core.pipeline.workfile import (
    get_workfile_template_key,
    find_workfile_rootless_path,
    save_workfile_info,
)
from ayon_core.pipeline.workfile.path_resolving import (
    get_next_workfile_version_path,
)
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

    If the workfile that will be opened in the application is opened by
    other user, the user can choose to version up. The workfile is then
    copied to next version, which is opened instead.

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
                project_name, task_entity["id"], settings.stale_timeout_hours
            )
        except Exception:
            self.log.warning(
                "Failed to receive task in-use information.", exc_info=True
            )
            return

        if not items:
            return

        workfile_path = self._get_workfile_to_open()
        confirmed, version_up = self._confirm(items, workfile_path)
        if not confirmed:
            usernames = ", ".join(sorted({item.username for item in items}))
            raise ApplicationLaunchFailed(
                "Launch was cancelled."
                f" Task '{task_entity['name']}' is in use by {usernames}."
            )

        if version_up and workfile_path:
            self._version_up_workfile(workfile_path)

        self.launch_context.env[ACKNOWLEDGED_SESSIONS_ENV_KEY] = ",".join(
            item.session_id for item in items
        )

    def _get_workfile_to_open(self) -> Optional[str]:
        """Existing workfile that will be opened in the application."""
        workfile_path = self.data.get("workfile_path")
        if not workfile_path and self.data.get("start_last_workfile"):
            workfile_path = self.data.get("last_workfile_path")

        if workfile_path and os.path.exists(workfile_path):
            return workfile_path
        return None

    def _confirm(
        self, items: list[TaskUsageItem], workfile_path: Optional[str]
    ) -> tuple[bool, bool]:
        """Ask user in a subprocess with the dialog.

        The launch is not blocked if the dialog fails for any reason.

        Returns:
            tuple[bool, bool]: User wants to launch the application, and
                user wants to work in next version of the workfile.

        """
        script_path = os.path.join(
            AYON_CORE_ROOT, "scripts", "task_in_use_prompt.py"
        )
        workfile = None
        if workfile_path:
            workfile = os.path.basename(workfile_path)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as tmp:
            tmp_path = tmp.name
            json.dump(
                {
                    "items": [item.to_data() for item in items],
                    "workfile": workfile,
                },
                tmp,
            )

        try:
            run_ayon_launcher_process(
                "--skip-bootstrap",
                script_path,
                tmp_path,
                add_sys_paths=True,
                creationflags=0,
            )
            with open(tmp_path, "r") as stream:
                result = json.load(stream)
            return (
                bool(result.get("confirmed", True)),
                bool(result.get("version_up", False)),
            )

        except Exception:
            self.log.warning(
                "Failed to show task in-use prompt.", exc_info=True
            )
            return True, False

        finally:
            os.remove(tmp_path)

    def _version_up_workfile(self, workfile_path: str) -> None:
        """Copy workfile to next version and open the copy instead.

        Raises:
            ApplicationLaunchFailed: If the next version could not be
                created. The user did ask to not work in the workfile.

        """
        try:
            new_path = self._copy_to_next_version(workfile_path)
        except Exception as exc:
            self.log.warning("Failed to version up workfile.", exc_info=True)
            raise ApplicationLaunchFailed(
                "Failed to version up workfile"
                f" '{os.path.basename(workfile_path)}': {exc}"
            )

        self.log.info(f"Workfile was versioned up to '{new_path}'.")
        if self.data.get("workfile_path"):
            self.data["workfile_path"] = new_path
        self.data["last_workfile_path"] = new_path
        self.launch_context.env["AYON_LAST_WORKFILE"] = new_path

    def _copy_to_next_version(self, workfile_path: str) -> str:
        project_name = self.data["project_name"]
        project_entity = self.data["project_entity"]
        folder_entity = self.data["folder_entity"]
        task_entity = self.data["task_entity"]
        anatomy = self.data["anatomy"]
        project_settings = self.data.get("project_settings")
        host_name = self.host_name

        template_key = get_workfile_template_key(
            project_name,
            task_entity["taskType"],
            host_name,
            project_settings=project_settings,
        )
        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        ).template
        template_data = copy.deepcopy(self.data.get("workdir_data"))
        if not template_data:
            template_data = get_template_data(
                project_entity,
                folder_entity,
                task_entity,
                host_name,
                settings=project_settings,
            )

        new_path, version, comment = get_next_workfile_version_path(
            workfile_path, file_template, template_data
        )
        if os.path.exists(new_path):
            raise ValueError(
                f"Workfile '{os.path.basename(new_path)}' already exists."
            )

        shutil.copy2(workfile_path, new_path)

        rootless_path = find_workfile_rootless_path(
            new_path,
            project_name,
            folder_entity,
            task_entity,
            host_name,
            project_entity=project_entity,
            project_settings=project_settings,
            anatomy=anatomy,
        )
        save_workfile_info(
            project_name,
            task_entity["id"],
            rootless_path,
            host_name,
            version=version,
            comment=comment,
        )
        return new_path
