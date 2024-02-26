# -*- coding: utf-8 -*-
import pyblish.api
from pymxs import runtime as rt
from ayon_core.pipeline import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.hosts.max.api.action import SelectInvalidAction


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
                   if invalid.isAnimated]

        return invalid
