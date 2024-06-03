# -*- coding: utf-8 -*-
"""Validator for checking that export is a single frame."""
import pyblish.api
from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import ValidateContentsOrder
from ayon_houdini.api.action import SelectInvalidAction


class ValidateSingleFrame(pyblish.api.InstancePlugin,
                           OptionalPyblishPluginMixin):
    """Validate Export is a Single Frame.

    It checks if rop node is exporting one frame.
    This is mainly for Model product type.
    """

    families = ["model"]
    label = "Validate Single Frame"
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

        frame_start = instance.data.get("frameStartHandle")
        frame_end = instance.data.get("frameEndHandle")

        # This happens if instance node has no 'trange' parameter.
        if frame_start is None or frame_end is None:
            cls.log.debug(
                "No frame data, skipping check.."
            )
            return

        if frame_start != frame_end:
            invalid.append(instance.data["instance_node"])
            cls.log.error(
                "Invalid frame range on '%s'."
                "You should use the same frame number for 'f1' "
                "and 'f2' parameters.",
                instance.data["instance_node"].path()
            )

        return invalid
