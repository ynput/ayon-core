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
            bullet_point_invalid_statement = "\n".join(
                "- {}: {}".format(obj, message)
                for obj, message in invalid
            )
            raise PublishValidationError(
                "Keyframes found on:\n\n{0}".format(
                    bullet_point_invalid_statement)
                ,
                title="Keyframes on model"
            )

    @staticmethod
    def get_invalid(instance):
        invalid = []
        selected_objects = instance.data["members"]
        for sel in selected_objects:
            sel_pos_ctl = rt.getPropertyController(
                sel.controller, 'Position')
            ctl_count = (sel_pos_ctl.keys).count
            if ctl_count > 0:
                invalid.append(
                   ( (sel), f"Object Position(s) has {ctl_count} keyframe(s)"))
            sel_rot_ctl = rt.getPropertyController(
                sel.controller, "Rotation"
            )
            ctl_count = (sel_rot_ctl.keys).count
            if ctl_count > 0:
                invalid.append(
                    ((sel), f"Object Rotation(s) has {ctl_count} keyframe(s)"))
            sel_scale_ctl = rt.getPropertyController(
                sel.controller, "Scale"
            )
            ctl_count = (sel_scale_ctl.keys).count
            if ctl_count > 0:
                invalid.append(
                    ((sel), f"Object Scale(s) has {ctl_count} keyframe(s)"))

        return invalid
