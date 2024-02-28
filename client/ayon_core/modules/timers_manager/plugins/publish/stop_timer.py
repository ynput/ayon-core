"""
Requires:
    context -> project_settings
    context -> ayonAddonsManager
"""


import pyblish.api


class StopTimer(pyblish.api.ContextPlugin):
    label = "Stop Timer"
    order = pyblish.api.ExtractorOrder - 0.49
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

        timers_manager.stop_timer_with_webserver(self.log)
