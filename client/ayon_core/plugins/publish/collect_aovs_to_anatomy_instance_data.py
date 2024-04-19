import pyblish.api


class CollectAOVNameToAnatomyInstanceData(pyblish.api.InstancePlugin):
    """
    Collect AOV name to template data.

    Note:
        This functionality depends on AOV name added by
        ``submit_publish_job`` plugin and so it only works
        with Deadline submission.

    """
    order = pyblish.api.CollectorOrder + 0.499
    targets = ["farm"]
    label = "Collect AOV name to template data"

    def process(self, instance):
        if "aovName" not in instance.data:
            return

        instance.data["anatomyData"]["aov_name"] = instance.data["aovName"]
