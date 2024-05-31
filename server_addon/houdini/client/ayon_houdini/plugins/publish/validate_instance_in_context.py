# -*- coding: utf-8 -*-
"""Validate if instance asset is the same as context asset."""
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)

from ayon_houdini.api import plugin
from ayon_houdini.api.action import SelectROPAction


class ValidateInstanceInContextHoudini(plugin.HoudiniInstancePlugin,
                                       OptionalPyblishPluginMixin):
    """Validator to check if instance asset match context asset.

    When working in per-shot style you always publish data in context of
    current asset (shot). This validator checks if this is so. It is optional
    so it can be disabled when needed.
    """
    # Similar to maya-equivalent `ValidateInstanceInContext`

    order = ValidateContentsOrder
    label = "Instance in same Context"
    optional = True
    actions = [SelectROPAction, RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        folder_path = instance.data.get("folderPath")
        task = instance.data.get("task")
        context = self.get_context(instance)
        if (folder_path, task) != context:
            context_label = "{} > {}".format(*context)
            instance_label = "{} > {}".format(folder_path, task)

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
        context_folder, context_task = cls.get_context(instance)

        create_context = instance.context.data["create_context"]
        instance_id = instance.data["instance_id"]
        created_instance = create_context.get_instance_by_id(
            instance_id
        )
        created_instance["folderPath"] = context_folder
        created_instance["task"] = context_task
        create_context.save_changes()

    @staticmethod
    def get_context(instance):
        """Return folderPath, task from publishing context data"""
        context = instance.context
        return context.data["folderPath"], context.data["task"]
