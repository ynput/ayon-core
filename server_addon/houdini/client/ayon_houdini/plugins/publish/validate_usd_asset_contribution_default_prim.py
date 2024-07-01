import inspect

import hou
import pyblish.api

from ayon_core.pipeline import PublishValidationError
from ayon_core.pipeline.publish import RepairAction, OptionalPyblishPluginMixin

from ayon_houdini.api.action import SelectROPAction
from ayon_houdini.api import plugin


class ValidateUSDAssetContributionDefaultPrim(plugin.HoudiniInstancePlugin,
                                              OptionalPyblishPluginMixin):
    """Validate the default prim is set when USD contribution is set to asset.

    If the USD asset contributions is enabled and the user has it set to
    initialize asset as "asset" then most likely they are looking to publish
    into an asset structure - which should have a default prim that matches
    the folder's name. To ensure that's the case we force require the
    value to be set on the ROP node.

    Note that another validator "Validate USD Rop Default Prim" enforces the
    primitive actually exists (or has modifications) if the ROP specifies
    a default prim - so that does not have to be validated with this validator.

    """

    order = pyblish.api.ValidatorOrder
    families = ["usdrop"]
    hosts = ["houdini"]
    label = "Validate USD Asset Contribution Default Prim"
    actions = [SelectROPAction, RepairAction]

    # TODO: Unfortunately currently this does not show as optional toggle
    #   because the product type is `usd` and not `usdrop` - however we do
    #   not want to run this for ALL `usd` product types?
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        # Check if instance is set to be an asset contribution
        settings = self.get_attr_values_from_data_for_plugin_name(
            "CollectUSDLayerContributions", instance.data
        )
        if (
                not settings.get("contribution_enabled", False)
                or settings.get("contribution_target_product_init") != "asset"
        ):
            return

        rop_node = hou.node(instance.data["instance_node"])
        default_prim = rop_node.evalParm("defaultprim")
        if not default_prim:
            raise PublishValidationError(
                f"No default prim specified on ROP node: {rop_node.path()}",
                description=self.get_description()
            )

        folder_name = instance.data["folderPath"].rsplit("/", 1)[-1]
        if not default_prim.lstrip("/") == folder_name:
            raise PublishValidationError(
                f"Default prim specified on ROP node does not match the "
                f"asset's folder name: '{default_prim}' "
                f"(should be: '/{folder_name}')",
                description=self.get_description()
            )

    @classmethod
    def repair(cls, instance):
        rop_node = hou.node(instance.data["instance_node"])
        rop_node.parm("defaultprim").set(
            "/`strsplit(chs(\"folderPath\"), \"/\", -1)`"
        )

    @staticmethod
    def get_attr_values_from_data_for_plugin_name(
            plugin_name: str, data: dict) -> dict:
        return (
            data
            .get("publish_attributes", {})
            .get(plugin_name, {})
        )

    def get_description(self):
        return inspect.cleandoc(
            """### Default primitive not set to current asset

            The USD instance has **USD Contribution** enabled and is set to 
            initialize as **asset**. The asset requires a default root 
            primitive with the name of the folder it's related to.
            
            For example, you're working in `/asset/char_hero` then the
            folder's name is `char_hero`. For the asset hence all prims should
            live under `/char_hero` root primitive.
            
            This validation solely ensures the **default primitive** on the ROP
            node is set to match the folder name.
            """
        )
