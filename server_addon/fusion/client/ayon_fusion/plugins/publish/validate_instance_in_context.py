# -*- coding: utf-8 -*-
"""Validate if instance context is the same as publish context."""

import pyblish.api
from ayon_fusion.api.action import SelectToolAction
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)


class ValidateInstanceInContextFusion(pyblish.api.InstancePlugin,
                                      OptionalPyblishPluginMixin):
    """Validator to check if instance context matches context of publish.

    When working in per-shot style you always publish data in context of
    current asset (shot). This validator checks if this is so. It is optional
    so it can be disabled when needed.
    """
    # Similar to maya and houdini-equivalent `ValidateInstanceInContext`

    order = ValidateContentsOrder
    label = "Instance in same Context"
    optional = True
    hosts = ["fusion"]
    actions = [SelectToolAction, RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        instance_context = self.get_context(instance.data)
        context = self.get_context(instance.context.data)
        if instance_context != context:
            context_label = "{} > {}".format(*context)
            instance_label = "{} > {}".format(*instance_context)

            raise PublishValidationError(
                message=(
                    "Instance '{}' publishes to different asset than current "
                    "context: {}. Current context: {}".format(
                        instance.name, instance_label, context_label
                    )
                ),
                description=(
                    "## Publishing to a different asset\n"
                    "There are publish instances present which are publishing "
                    "into a different asset than your current context.\n\n"
                    "Usually this is not what you want but there can be cases "
                    "where you might want to publish into another asset or "
                    "shot. If that's the case you can disable the validation "
                    "on the instance to ignore it."
                )
            )

    @classmethod
    def repair(cls, instance):

        create_context = instance.context.data["create_context"]
        instance_id = instance.data.get("instance_id")
        created_instance = create_context.get_instance_by_id(
            instance_id
        )
        if created_instance is None:
            raise RuntimeError(
                f"No CreatedInstances found with id '{instance_id} "
                f"in {create_context.instances_by_id}"
            )

        context_asset, context_task = cls.get_context(instance.context.data)
        created_instance["folderPath"] = context_asset
        created_instance["task"] = context_task
        create_context.save_changes()

    @staticmethod
    def get_context(data):
        """Return asset, task from publishing context data"""
        return data["folderPath"], data["task"]
