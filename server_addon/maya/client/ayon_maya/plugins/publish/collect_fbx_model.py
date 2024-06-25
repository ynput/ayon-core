import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin
from ayon_maya.api import plugin



class CollectFbxModel(plugin.MayaInstancePlugin,
                      OptionalPyblishPluginMixin):
    """Collect Camera for FBX export."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Model for FBX export"
    families = ["model"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        if not instance.data.get("families"):
            instance.data["families"] = []

        if "fbx" not in instance.data["families"]:
            instance.data["families"].append("fbx")

        for key in {
            "bakeComplexAnimation", "bakeResampleAnimation",
            "skins", "constraints", "lights"}:
                instance.data[key] = False
