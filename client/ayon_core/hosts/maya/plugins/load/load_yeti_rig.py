from typing import List

import maya.cmds as cmds

from ayon_core.hosts.maya.api import plugin
from ayon_core.hosts.maya.api import lib

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import CreateContext


class YetiRigLoader(plugin.ReferenceLoader):
    """This loader will load Yeti rig."""

    product_types = {"yetiRig"}
    representations = {"ma"}

    label = "Load Yeti Rig"
    order = -9
    icon = "code-fork"
    color = "orange"

    # From settings
    create_cache_instance_on_load = True

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

        if self.create_cache_instance_on_load:
            # Automatically create in instance to allow publishing the loaded
            # yeti rig into a yeti cache
            self._create_yeti_cache_instance(nodes, variant=namespace)

        return nodes

    def _create_yeti_cache_instance(self, nodes: List[str], variant: str):
        """Create a yeticache product type instance to publish the output.

        This is similar to how loading animation rig will automatically create
        an animation instance for publishing any loaded character rigs, but
        then for yeti rigs.

        Args:
            nodes (List[str]): Nodes generated on load.
            variant (str): Variant for the yeti cache instance to create.

        """

        # Find the roots amongst the loaded nodes
        yeti_nodes = cmds.ls(nodes, type="pgYetiMaya", long=True)
        assert yeti_nodes, "No pgYetiMaya nodes in rig, this is a bug."

        self.log.info("Creating variant: {}".format(variant))

        creator_identifier = "io.openpype.creators.maya.yeticache"

        host = registered_host()
        create_context = CreateContext(host)

        with lib.maintained_selection():
            cmds.select(yeti_nodes, noExpand=True)
            create_context.create(
                creator_identifier=creator_identifier,
                variant=variant,
                pre_create_data={"use_selection": True}
            )
