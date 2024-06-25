from maya import cmds
from ayon_maya.api import plugin
import pyblish.api


class CollectFileDependencies(plugin.MayaContextPlugin):
    """Gather all files referenced in this scene."""

    label = "Collect File Dependencies"
    order = pyblish.api.CollectorOrder - 0.49
    families = ["renderlayer"]

    @classmethod
    def apply_settings(cls, project_settings):
        # Disable plug-in if not used for deadline submission anyway
        if "deadline" not in project_settings:
            cls.enabled = False
            return
        settings = (
            project_settings
            ["deadline"]
            ["publish"]
            ["MayaSubmitDeadline"]
        )
        cls.enabled = settings.get("asset_dependencies", True)

    def process(self, context):
        dependencies = set()
        for node in cmds.ls(type="file"):
            path = cmds.getAttr("{}.{}".format(node, "fileTextureName"))
            if path not in dependencies:
                dependencies.add(path)

        for node in cmds.ls(type="AlembicNode"):
            path = cmds.getAttr("{}.{}".format(node, "abc_File"))
            if path not in dependencies:
                dependencies.add(path)

        context.data["fileDependencies"] = list(dependencies)
