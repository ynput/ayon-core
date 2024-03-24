import inspect
from typing import List

import mathutils
import bpy

import pyblish.api

from ayon_core.hosts.blender.api import plugin, lib
import ayon_core.hosts.blender.api.action
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction
)


class ValidateTransformZero(pyblish.api.InstancePlugin,
                            OptionalPyblishPluginMixin):
    """Transforms can't have any values"""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["model"]
    label = "Transform Zero"
    actions = [ayon_core.hosts.blender.api.action.SelectInvalidAction,
               RepairAction]

    _identity = mathutils.Matrix()

    @classmethod
    def get_invalid(cls, instance) -> List:
        invalid = []
        for obj in instance:
            if (
                isinstance(obj, bpy.types.Object)
                and obj.matrix_basis != cls._identity
            ):
                invalid.append(obj)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                "Objects found in instance which do not"
                f" have transform set to zero: {names}",
                description=self.get_description()
            )

    @classmethod
    def repair(cls, instance):

        invalid = cls.get_invalid(instance)
        if not invalid:
            return

        context = plugin.create_blender_context(
            active=invalid[0], selected=invalid
        )
        with lib.maintained_selection():
            with bpy.context.temp_override(**context):
                plugin.deselect_all()
                for obj in invalid:
                    obj.select_set(True)

                # TODO: Preferably this does allow custom pivot point locations
                #  and if so, this should likely apply to the delta instead
                #  using `bpy.ops.object.transforms_to_deltas(mode="ALL")`
                bpy.ops.object.transform_apply(location=True,
                                               rotation=True,
                                               scale=True)

    def get_description(self):
        return inspect.cleandoc(
            """## Transforms can't have any values.

            The location, rotation and scale on the transform must be at
            the default values. This also goes for the delta transforms.

            To solve this issue, try freezing the transforms:
            - `Object` > `Apply` > `All Transforms`

            Using the Repair action directly will do the same.

            So long as the transforms, rotation and scale values are zero,
            you're all good.
            """
        )
