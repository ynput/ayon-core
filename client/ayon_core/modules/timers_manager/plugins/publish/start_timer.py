"""
Requires:
    context -> project_settings
    context -> ayonAddonsManager
"""

import pyblish.api


class StartTimer(pyblish.api.ContextPlugin):
    label = "Start Timer"
    order = pyblish.api.IntegratorOrder + 1
    hosts = ["*"]

    def process(self, context):
        timers_manager = context.data["ayonAddonsManager"]["timers_manager"]
        if not timers_manager.enabled:
            self.log.debug("TimersManager is disabled")
            return

        project_settings = context.data["project_settings"]
        if not project_settings["timers_manager"]["disregard_publishing"]:
            self.log.debug("Publish is not affecting running timers.")
            return

        project_name = context.data["projectName"]
        folder_path = context.data.get("folderPath")
        task_name = context.data.get("task")
        if not project_name or not folder_path or not task_name:
            self.log.info((
                "Current context does not contain all"
                " required information to start a timer."
            ))
            return
        timers_manager.start_timer_with_webserver(
            project_name, folder_path, task_name, self.log
        )
