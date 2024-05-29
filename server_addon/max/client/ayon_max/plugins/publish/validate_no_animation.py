# -*- coding: utf-8 -*-
import pyblish.api
from pymxs import runtime as rt
from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_max.api.action import SelectInvalidAction


def get_invalid_keys(obj):
    """function to check on whether there is keyframe in

    Args:
        obj (str): object needed to check if there is a keyframe

    Returns:
        bool: whether invalid object(s) exist
    """
    for transform in ["Position", "Rotation", "Scale"]:
        num_of_key = rt.NumKeys(rt.getPropertyController(
            obj.controller, transform))
        if num_of_key > 0:
            return True
    return False


class ValidateNoAnimation(pyblish.api.InstancePlugin,
                          OptionalPyblishPluginMixin):
    """Validates No Animation

    Ensure no keyframes on nodes in the Instance
    """

    order = pyblish.api.ValidatorOrder
    families = ["model"]
    hosts = ["max"]
    optional = True
    label = "Validate No Animation"
    actions = [SelectInvalidAction]

    settings_category = "max"

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Keyframes found on:\n\n{0}".format(invalid)
                ,
                title="Keyframes on model"
            )

    @staticmethod
    def get_invalid(instance):
        """Get invalid object(s) which have keyframe(s)


        Args:
            instance (pyblish.api.instance): Instance

        Returns:
            list: list of invalid objects
        """
        invalid = [invalid for invalid in instance.data["members"]
                   if invalid.isAnimated or get_invalid_keys(invalid)]

        return invalid
