# -*- coding: utf-8 -*-
import hou

import pyblish.api
from ayon_core.pipeline import PublishValidationError

from ayon_houdini.api import plugin


class ValidateCopOutputNode(plugin.HoudiniInstancePlugin):
    """Validate the instance COP Output Node.

    This will ensure:
        - The COP Path is set.
        - The COP Path refers to an existing object.
        - The COP Path node is a COP node.

    """

    order = pyblish.api.ValidatorOrder
    families = ["imagesequence"]
    label = "Validate COP Output Node"

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Output node '{}' is incorrect. "
                "See plug-in log for details.".format(invalid),
                title=self.label,
                description=(
                    "### Invalid COP output node\n\n"
                    "The output node path for the instance must be set to a "
                    "valid COP node path.\n\nSee the log for more details."
                )
            )

    @classmethod
    def get_invalid(cls, instance):
        output_node = instance.data.get("output_node")

        if not output_node:
            node = hou.node(instance.data.get("instance_node"))
            cls.log.error(
                "COP Output node in '%s' does not exist. "
                "Ensure a valid COP output path is set." % node.path()
            )

            return [node.path()]

        # Output node must be a Sop node.
        if not isinstance(output_node, hou.CopNode):
            cls.log.error(
                "Output node %s is not a COP node. "
                "COP Path must point to a COP node, "
                "instead found category type: %s",
                output_node.path(), output_node.type().category().name()
            )
            return [output_node.path()]

        # For the sake of completeness also assert the category type
        # is Cop2 to avoid potential edge case scenarios even though
        # the isinstance check above should be stricter than this category
        if output_node.type().category().name() != "Cop2":
            cls.log.error(
                "Output node %s is not of category Cop2.", output_node.path()
            )
            return [output_node.path()]
