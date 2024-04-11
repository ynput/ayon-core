import maya.cmds as cmds

from ayon_core.hosts.maya.api import plugin
from ayon_core.hosts.maya.api import lib


class YetiRigLoader(plugin.ReferenceLoader):
    """This loader will load Yeti rig."""

    product_types = {"yetiRig"}
    representations = {"ma"}

    label = "Load Yeti Rig"
    order = -9
    icon = "code-fork"
    color = "orange"

    def process_reference(
        self, context, name=None, namespace=None, options=None
    ):
        path = self.filepath_from_context(context)

        attach_to_root = options.get("attach_to_root", True)
        group_name = options["group_name"]

        # no group shall be created
        if not attach_to_root:
            group_name = namespace

        with lib.maintained_selection():
            file_url = self.prepare_root_value(
                path, context["project"]["name"]
            )
            nodes = cmds.file(
                file_url,
                namespace=namespace,
                reference=True,
                returnNewNodes=True,
                groupReference=attach_to_root,
                groupName=group_name
            )

        color = plugin.get_load_color_for_product_type("yetiRig")
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_name + ".useOutlinerColor", 1)
            cmds.setAttr(
                group_name + ".outlinerColor", red, green, blue
            )
        self[:] = nodes

        return nodes
