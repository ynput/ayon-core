import pyblish.api


class CollectHeadlessFarm(pyblish.api.ContextPlugin):
    """Setup instances for headless farm submission."""

    order = pyblish.api.CollectorOrder + 0.4999
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

            # Enable for farm publishing.
            instance.data["farm"] = True

            # Clear the families as we only want the main family, ei. no review
            # etc.
            instance.data["families"] = ["headless_farm"]

            # Use the workfile instead of published.
            instance.data["use_published_workfile"] = False
