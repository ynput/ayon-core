"""A module containing generic loader actions that will display in the Loader.

"""
import qargparse
from ayon_core.pipeline import load
from ayon_maya.api.lib import (
    maintained_selection,
    get_custom_namespace
)
import ayon_maya.api.plugin


class SetFrameRangeLoader(load.LoaderPlugin):
    """Set frame range excluding pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "proxyAbc",
        "pointcache",
    }
    representations = {"abc"}

    label = "Set frame range"
    order = 11
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        import maya.cmds as cmds

        version_attributes = context["version"]["attrib"]
        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        cmds.playbackOptions(minTime=start,
                             maxTime=end,
                             animationStartTime=start,
                             animationEndTime=end)


class SetFrameRangeWithHandlesLoader(load.LoaderPlugin):
    """Set frame range including pre- and post-handles"""

    product_types = {
        "animation",
        "camera",
        "proxyAbc",
        "pointcache",
    }
    representations = {"abc"}

    label = "Set frame range (with handles)"
    order = 12
    icon = "clock-o"
    color = "white"

    def load(self, context, name, namespace, data):

        import maya.cmds as cmds

        version_attributes = context["version"]["attrib"]

        start = version_attributes.get("frameStart")
        end = version_attributes.get("frameEnd")

        if start is None or end is None:
            print("Skipping setting frame range because start or "
                  "end frame data is missing..")
            return

        # Include handles
        start -= version_attributes.get("handleStart", 0)
        end += version_attributes.get("handleEnd", 0)

        cmds.playbackOptions(minTime=start,
                             maxTime=end,
                             animationStartTime=start,
                             animationEndTime=end)


class ImportMayaLoader(ayon_maya.api.plugin.Loader):
    """Import action for Maya (unmanaged)

    Warning:
        The loaded content will be unmanaged and is *not* visible in the
        scene inventory. It's purely intended to merge content into your scene
        so you could also use it as a new base.

    """
    representations = {"ma", "mb", "obj"}
    product_types = {
        "model",
        "pointcache",
        "proxyAbc",
        "animation",
        "mayaAscii",
        "mayaScene",
        "setdress",
        "layout",
        "camera",
        "rig",
        "camerarig",
        "staticMesh",
        "workfile",
    }

    label = "Import"
    order = 10
    icon = "arrow-circle-down"
    color = "#775555"

    options = [
        qargparse.Boolean(
            "clean_import",
            label="Clean import",
            default=False,
            help="Should all occurrences of cbId be purged?"
        )
    ]

    @classmethod
    def apply_settings(cls, project_settings):
        super(ImportMayaLoader, cls).apply_settings(project_settings)
        cls.enabled = cls.load_settings["import_loader"].get("enabled", True)

    def load(self, context, name=None, namespace=None, data=None):
        import maya.cmds as cmds

        choice = self.display_warning()
        if choice is False:
            return

        custom_group_name, custom_namespace, options = \
            self.get_custom_namespace_and_group(context, data,
                                                "import_loader")

        namespace = get_custom_namespace(custom_namespace)

        if not options.get("attach_to_root", True):
            custom_group_name = namespace

        path = self.filepath_from_context(context)
        with maintained_selection():
            nodes = cmds.file(path,
                              i=True,
                              preserveReferences=True,
                              namespace=namespace,
                              returnNewNodes=True,
                              groupReference=options.get("attach_to_root",
                                                         True),
                              groupName=custom_group_name)

            if data.get("clean_import", False):
                remove_attributes = ["cbId"]
                for node in nodes:
                    for attr in remove_attributes:
                        if cmds.attributeQuery(attr, node=node, exists=True):
                            full_attr = "{}.{}".format(node, attr)
                            print("Removing {}".format(full_attr))
                            cmds.deleteAttr(full_attr)

        # We do not containerize imported content, it remains unmanaged
        return

    def display_warning(self):
        """Show warning to ensure the user can't import models by accident

        Returns:
            bool

        """

        from qtpy import QtWidgets

        accept = QtWidgets.QMessageBox.Ok
        buttons = accept | QtWidgets.QMessageBox.Cancel

        message = "Are you sure you want import this"
        state = QtWidgets.QMessageBox.warning(None,
                                              "Are you sure?",
                                              message,
                                              buttons=buttons,
                                              defaultButton=accept)

        return state == accept
