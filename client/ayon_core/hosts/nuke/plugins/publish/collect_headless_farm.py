import pyblish.api

from ayon_core.pipeline.publish import (
    AYONPyblishPluginMixin
)


class CollectHeadlessFarm(pyblish.api.ContextPlugin):
    """Setup instances for headless farm submission."""

    # Needs to be after CollectFromCreateContext
    order = pyblish.api.CollectorOrder - 0.4
    label = "Collect Headless Farm"
    hosts = ["nuke"]

    def process(self, context):
        if not context.data.get("headless_farm", False):
            return

        for instance in context:
            if instance.data["family"] == "workfile":
                instance.data["active"] = False
                continue

            # Filter out all other instances.
            node = instance.data["transientData"]["node"]
            if node.name() != instance.context.data["node_name"]:
                instance.data["active"] = False
                continue

            instance.data["families"].append("headless_farm")


class SetupHeadlessFarm(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Setup instance for headless farm submission."""

    order = pyblish.api.CollectorOrder + 0.4999
    label = "Setup Headless Farm"
    hosts = ["nuke"]
    families = ["headless_farm"]

    def process(self, instance):
        # Enable for farm publishing.
        instance.data["farm"] = True

        # Clear the families as we only want the main family, ei. no review
        # etc.
        instance.data["families"] = ["headless_farm"]

        # Use the workfile instead of published.
        publish_attributes = instance.data["publish_attributes"]
        plugin_attributes = publish_attributes["NukeSubmitDeadline"]
        plugin_attributes["use_published_workfile"] = False
