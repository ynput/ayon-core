import pyblish.api


class CollectHeadlessFarm(pyblish.api.InstancePlugin):
    """Setup instances for headless farm submission."""

    order = pyblish.api.CollectorOrder + 0.4999
    label = "Collect Headless Farm"
    hosts = ["nuke"]

    def process(self, instance):
        if not instance.context.data.get("headless_farm", False):
            return

        if instance.data["family"] == "workfile":
            instance.data["active"] = False

            # Disable version validation.
            instance.data.pop("latestVersion")
            return

        # Filter out all other instances.
        node = instance.data["transientData"]["node"]
        if node.name() != instance.context.data["node_name"]:
            instance.data["active"] = False
            return

        # Enable for farm publishing.
        instance.data["farm"] = True

        # Clear the families as we only want the main family, ei. no review
        # etc.
        instance.data["families"] = []

        # Use the workfile instead of published.
        settings = instance.data["publish_attributes"]
        settings = settings["NukeSubmitDeadline"]
        settings["use_published_workfile"] = False

        # Disable version validation.
        instance.data.pop("latestVersion")
