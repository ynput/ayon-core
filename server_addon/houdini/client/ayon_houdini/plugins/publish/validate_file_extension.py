# -*- coding: utf-8 -*-
import os
import hou

import pyblish.api
from ayon_core.pipeline import PublishValidationError

from ayon_houdini.api import lib, plugin


class ValidateFileExtension(plugin.HoudiniInstancePlugin):
    """Validate the output file extension fits the output family.

    File extensions:
        - Pointcache must be .abc
        - Camera must be .abc
        - VDB must be .vdb

    """

    order = pyblish.api.ValidatorOrder
    families = ["camera", "vdbcache"]
    label = "Output File Extension"

    family_extensions = {
        "camera": ".abc",
        "vdbcache": ".vdb",
    }

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "ROP node has incorrect file extension: {}".format(invalid),
                title=self.label
            )

    @classmethod
    def get_invalid(cls, instance):

        # Get ROP node from instance
        node = hou.node(instance.data["instance_node"])

        # Create lookup for current family in instance
        families = []
        product_type = instance.data.get("productType")
        if product_type:
            families.append(product_type)
        families = set(families)

        # Perform extension check
        output = lib.get_output_parameter(node).eval()
        _, output_extension = os.path.splitext(output)

        for family in families:
            extension = cls.family_extensions.get(family, None)
            if extension is None:
                raise PublishValidationError(
                    "Unsupported family: {}".format(family),
                    title=cls.label)

            if output_extension != extension:
                return [node.path()]
