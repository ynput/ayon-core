# -*- coding: utf-8 -*-
import hou

import pyblish.api
from ayon_core.pipeline import PublishValidationError
from ayon_core.pipeline.publish import RepairAction

from ayon_houdini.api.action import SelectInvalidAction
from ayon_houdini.api import plugin



class DisableUseFolderHandlesAction(RepairAction):
    label = "Disable use folder handles"
    icon = "mdi.toggle-switch-off"


class ValidateFrameRange(plugin.HoudiniInstancePlugin):
    """Validate Frame Range.

    Due to the usage of start and end handles,
    then Frame Range must be >= (start handle + end handle)
    which results that frameEnd be smaller than frameStart
    """

    order = pyblish.api.ValidatorOrder - 0.1
    label = "Validate Frame Range"
    actions = [DisableUseFolderHandlesAction, SelectInvalidAction]

    def process(self, instance):

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                title="Invalid Frame Range",
                message=(
                    "Invalid frame range because the instance "
                    "start frame ({0[frameStart]}) is higher than "
                    "the end frame ({0[frameEnd]})"
                    .format(instance.data)
                ),
                description=(
                    "## Invalid Frame Range\n"
                    "The frame range for the instance is invalid because "
                    "the start frame is higher than the end frame.\n\nThis "
                    "is likely due to folder handles being applied to your "
                    "instance or the ROP node's start frame "
                    "is set higher than the end frame.\n\nIf your ROP frame "
                    "range is correct and you do not want to apply folder "
                    "handles make sure to disable Use folder handles on the "
                    "publish instance."
                )
            )

    @classmethod
    def get_invalid(cls, instance):

        if not instance.data.get("instance_node"):
            return

        rop_node = hou.node(instance.data["instance_node"])
        frame_start = instance.data.get("frameStart")
        frame_end = instance.data.get("frameEnd")

        if frame_start is None or frame_end is None:
            cls.log.debug(
                "Skipping frame range validation for "
                "instance without frame data: {}".format(rop_node.path())
            )
            return

        if frame_start > frame_end:
            cls.log.info(
                "The ROP node render range is set to "
                "{0[frameStartHandle]} - {0[frameEndHandle]} "
                "The folder handles applied to the instance are start handle "
                "{0[handleStart]} and end handle {0[handleEnd]}"
                .format(instance.data)
            )
            return [rop_node]

    @classmethod
    def repair(cls, instance):

        if not cls.get_invalid(instance):
            # Already fixed
            return

        # Disable use folder handles
        context = instance.context
        create_context = context.data["create_context"]
        instance_id = instance.data.get("instance_id")
        if not instance_id:
            cls.log.debug("'{}' must have instance id"
                          .format(instance))
            return

        created_instance = create_context.get_instance_by_id(instance_id)
        if not instance_id:
            cls.log.debug("Unable to find instance '{}' by id"
                          .format(instance))
            return

        created_instance.publish_attributes["CollectAssetHandles"]["use_handles"] = False  # noqa

        create_context.save_changes()
        cls.log.debug("use folder handles is turned off for '{}'"
                      .format(instance))
