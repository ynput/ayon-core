# -*- coding: utf-8 -*-
"""Validate if instance context is the same as current context."""
import pyblish.api
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.hosts.max.api.action import SelectInvalidAction
from pymxs import runtime as rt


class ValidateInstanceInContext(pyblish.api.InstancePlugin,
                                OptionalPyblishPluginMixin):
    """Validator to check if instance context match current context.

    When working in per-shot style you always publish data in context of
    current context (shot). This validator checks if this is so. It is optional
    so it can be disabled when needed.

    Action on this validator will select invalid instances.
    """
    order = ValidateContentsOrder
    label = "Instance in same Context"
    optional = True
    hosts = ["max"]
    actions = [SelectInvalidAction, RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        folderPath = instance.data.get("folderPath")
        task = instance.data.get("task")
        context = self.get_context(instance)
        if (folderPath, task) != context:
            context_label = "{} > {}".format(*context)
            instance_label = "{} > {}".format(folderPath, task)
            message = (
                "Instance '{}' publishes to different context(folder or task) "
                "than current context: {}. Current context: {}".format(
                    instance.name, instance_label, context_label
                )
            )
            raise PublishValidationError(
                message=message,
                description=(
                    "## Publishing to a different context data(folder or task)\n"
                    "There are publish instances present which are publishing "
                    "into a different folder path or task than your current context.\n\n"
                    "Usually this is not what you want but there can be cases "
                    "where you might want to publish into another context or "
                    "shot. If that's the case you can disable the validation "
                    "on the instance to ignore it."
                )
            )

    @classmethod
    def get_invalid(cls, instance):
        invalid = []
        folderPath = instance.data.get("folderPath")
        task = instance.data.get("task")
        context = cls.get_context(instance)
        if (folderPath, task) != context:
            invalid.append(rt.getNodeByName(instance.name))
        return invalid

    @classmethod
    def repair(cls, instance):
        context_asset = instance.context.data["folderPath"]
        context_task = instance.context.data["task"]
        instance_node = rt.getNodeByName(instance.data.get(
            "instance_node", ""))
        if not instance_node:
            return
        rt.SetUserProp(instance_node, "folderPath", context_asset)
        rt.SetUserProp(instance_node, "task", context_task)

    @staticmethod
    def get_context(instance):
        """Return asset, task from publishing context data"""
        context = instance.context
        return context.data["folderPath"], context.data["task"]
