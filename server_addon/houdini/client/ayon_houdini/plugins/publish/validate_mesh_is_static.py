# -*- coding: utf-8 -*-
"""Validator for correct naming of Static Meshes."""
from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import ValidateContentsOrder

from ayon_houdini.api import plugin
from ayon_houdini.api.action import SelectInvalidAction
from ayon_houdini.api.lib import get_output_children


class ValidateMeshIsStatic(plugin.HoudiniInstancePlugin,
                           OptionalPyblishPluginMixin):
    """Validate mesh is static.

    It checks if output node is time dependent.
    this avoids getting different output from ROP node when extracted
    from a different frame than the first frame.
    (Might be overly restrictive though)
    """

    families = ["staticMesh",
                "model"]
    label = "Validate Mesh is Static"
    order = ValidateContentsOrder + 0.1
    actions = [SelectInvalidAction]

    def process(self, instance):

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

        output_node = instance.data.get("output_node")
        if output_node is None:
            cls.log.debug(
                "No Output Node, skipping check.."
            )
            return

        all_outputs = get_output_children(output_node)

        for output in all_outputs:
            if output.isTimeDependent():
                invalid.append(output)
                cls.log.error(
                    "Output node '%s' is time dependent.",
                    output.path()
                )

        return invalid
