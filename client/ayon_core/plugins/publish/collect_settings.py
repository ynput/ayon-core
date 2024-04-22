from pyblish import api
from ayon_core.settings import get_project_settings


class CollectSettings(api.ContextPlugin):
    """Collect Settings and store in the context."""

    order = api.CollectorOrder - 0.491
    label = "Collect Settings"

    def process(self, context):
        project_name = context.data["projectName"]
        self.log.debug(
            "Collecting settings for project: {}".format(project_name)
        )
        project_settings = get_project_settings(project_name)
        context.data["project_settings"] = project_settings
