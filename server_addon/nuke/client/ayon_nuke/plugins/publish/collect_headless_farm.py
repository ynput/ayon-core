import pyblish.api

from ayon_core.pipeline.publish import (
    AYONPyblishPluginMixin
)


class CollectRenderOnFarm(pyblish.api.ContextPlugin):
    """Setup instances for render on farm submission."""

    # Needs to be after CollectFromCreateContext
    order = pyblish.api.CollectorOrder - 0.49
    label = "Collect Render On Farm"
    hosts = ["nuke"]

    settings_category = "nuke"

    def process(self, context):
        if not context.data.get("render_on_farm", False):
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

            instance.data["families"].append("render_on_farm")

            # Enable for farm publishing.
            instance.data["farm"] = True

        # Skip workfile version incremental save.
        instance.context.data["increment_script_version"] = False


class SetupRenderOnFarm(pyblish.api.InstancePlugin, AYONPyblishPluginMixin):
    """Setup instance for render on farm submission."""

    order = pyblish.api.CollectorOrder + 0.4999
    label = "Setup Render On Farm"
    hosts = ["nuke"]
    families = ["render_on_farm"]

    def process(self, instance):
        # Clear the families as we only want the main family, ei. no review
        # etc.
        instance.data["families"] = ["render_on_farm"]

        # Use the workfile instead of published.
        publish_attributes = instance.data["publish_attributes"]
        plugin_attributes = publish_attributes["NukeSubmitDeadline"]
        plugin_attributes["use_published_workfile"] = False
