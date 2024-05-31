# -*- coding: utf-8 -*-
"""Validator for correct naming of Static Meshes."""
import hou

from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    RepairAction,
)

from ayon_houdini.api import plugin
from ayon_houdini.api.action import SelectInvalidAction
from ayon_core.pipeline.create import get_product_name


class FixProductNameAction(RepairAction):
    label = "Fix Product Name"


class ValidateSubsetName(plugin.HoudiniInstancePlugin,
                         OptionalPyblishPluginMixin):
    """Validate Product name.

    """

    families = ["staticMesh"]
    label = "Validate Product Name"
    order = ValidateContentsOrder + 0.1
    actions = [FixProductNameAction, SelectInvalidAction]

    optional = True

    def process(self, instance):

        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            nodes = [n.path() for n in invalid]
            raise PublishValidationError(
                "See log for details. "
                "Invalid nodes: {0}".format(nodes)
            )

    @classmethod
    def get_invalid(cls, instance):

        invalid = []

        rop_node = hou.node(instance.data["instance_node"])

        # Check product name
        folder_entity = instance.data["folderEntity"]
        task_entity = instance.data["taskEntity"]
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        product_name = get_product_name(
            instance.context.data["projectName"],
            task_name,
            task_type,
            instance.context.data["hostName"],
            instance.data["productType"],
            variant=instance.data["variant"],
            dynamic_data={"asset": folder_entity["name"]}
        )

        if instance.data.get("productName") != product_name:
            invalid.append(rop_node)
            cls.log.error(
                "Invalid product name on rop node '%s' should be '%s'.",
                rop_node.path(), product_name
            )

        return invalid

    @classmethod
    def repair(cls, instance):
        rop_node = hou.node(instance.data["instance_node"])

        # Check product name
        folder_entity = instance.data["folderEntity"]
        task_entity = instance.data["taskEntity"]
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        product_name = get_product_name(
            instance.context.data["projectName"],
            task_name,
            task_type,
            instance.context.data["hostName"],
            instance.data["productType"],
            variant=instance.data["variant"],
            dynamic_data={"asset": folder_entity["name"]}
        )

        instance.data["productName"] = product_name
        rop_node.parm("AYON_productName").set(product_name)

        cls.log.debug(
            "Product name on rop node '%s' has been set to '%s'.",
            rop_node.path(), product_name
        )
