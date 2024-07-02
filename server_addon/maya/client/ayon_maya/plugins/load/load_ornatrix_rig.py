from typing import List

import maya.cmds as cmds
from ayon_core.pipeline import registered_host,CreatorError
from ayon_core.pipeline.create import CreateContext
from ayon_maya.api import lib, plugin


class OxRigLoader(plugin.ReferenceLoader):
    """This loader will load Ornatix rig."""

    product_types = {"oxrig"}
    representations = {"ma"}

    label = "Load Ornatrix Rig"
    order = -9
    icon = "code-fork"
    color = "orange"

    # From settings
    create_cache_instance_on_load = True

    def process_reference(
        self, context, name=None, namespace=None, options=None
    ):
        path = self.filepath_from_context(context)

        # Check if the plugin for Ornatrix is available on the pc
        try:
            cmds.loadPlugin("Ornatrix", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

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

        color = plugin.get_load_color_for_product_type("oxrig")
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_name + ".useOutlinerColor", 1)
            cmds.setAttr(
                group_name + ".outlinerColor", red, green, blue
            )

        self[:] = nodes

        if self.create_cache_instance_on_load:
            self._create_ox_cache_instance(nodes, variant=namespace)

        return nodes

    def _create_ox_cache_instance(self, nodes: List[str], variant: str):
        """Create a onratrixcache product type instance to publish the output.

        This is similar to how loading animation rig will automatically create
        an animation instance for publishing any loaded character rigs, but
        then for Onratrix rigs.

        Args:
            nodes (List[str]): Nodes generated on load.
            variant (str): Variant for the onratrix cache instance to create.

        """

        # Check of the nodes connect to the ornatrix-related nodes
        ox_node_types = (
            "HairFromGuidesNode", "GuidesFromMeshNode",
            "MeshFromStrandsNode", "SurfaceCombNode"
        )
        # Check of the nodes connect to the ornatrix-related nodes
        ox_nodes = cmds.ls(nodes, type=ox_node_types)
        assert ox_nodes, "No Ornatrix nodes in rig, this is a bug."

        ox_geo_nodes = cmds.ls(nodes, assemblies=True, long=True)

        self.log.info("Creating variant: {}".format(variant))

        creator_identifier = "io.openpype.creators.maya.oxcache"

        host = registered_host()
        create_context = CreateContext(host)

        with lib.maintained_selection():
            cmds.select(ox_geo_nodes, noExpand=True)
            try:
                create_context.create(
                    creator_identifier=creator_identifier,
                    variant=variant,
                    pre_create_data={"use_selection": True}
                )
            except CreatorError:
                self.log.debug(
                    "Ornatrix Cache has been turned off. Skip creating instance.")
