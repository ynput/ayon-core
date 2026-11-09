from __future__ import annotations

from ayon_applications import (
    PreLaunchHook,
    LaunchTypes,
    ApplicationLaunchFailed,
)

from ayon_core.lib import is_headless_mode_enabled
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

    The prompt does not offer to version up the workfile, a workfile can
    be copied correctly only by the host integration.

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

        asked, confirmed = self._confirm(items)
        if not confirmed:
            usernames = ", ".join(sorted({item.username for item in items}))
            raise ApplicationLaunchFailed(
                "Launch was cancelled."
                f" Task '{task_entity['name']}' is in use by {usernames}."
            )

        # Sessions are confirmed only if the user was asked
        if asked:
            self.launch_context.env[ACKNOWLEDGED_SESSIONS_ENV_KEY] = (
                ",".join(item.session_id for item in items)
            )

    def _confirm(self, items: list[TaskUsageItem]) -> tuple[bool, bool]:
        """Ask user with a dialog shown in current process.

        The launch is not blocked if the dialog can't be shown, e.g. if
        the application is not launched from the main thread. The user is
        notified inside the launched application in that case.

        Returns:
            tuple[bool, bool]: User was asked, and user wants to launch
                the application.

        """
        answer = None
        try:
            # Qt is imported only if the user has to be asked
            from ayon_core.tools.workfiles.widgets.task_in_use_dialog import (
                ask_to_launch_on_task_in_use,
            )

            answer = ask_to_launch_on_task_in_use(items)
        except Exception:
            self.log.warning(
                "Failed to show task in-use prompt.", exc_info=True
            )

        if answer is None:
            self.log.info(
                "Task in-use prompt was not shown."
                " Launching without the confirmation."
            )
            return False, True
        return True, answer
