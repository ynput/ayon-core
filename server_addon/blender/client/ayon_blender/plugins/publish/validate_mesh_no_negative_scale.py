from typing import List

import bpy

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)
import ayon_blender.api.action
from ayon_blender.api import plugin


class ValidateMeshNoNegativeScale(
    plugin.BlenderInstancePlugin,
    OptionalPyblishPluginMixin
):
    """Ensure that meshes don't have a negative scale."""

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["model"]
    label = "Mesh No Negative Scale"
    actions = [ayon_blender.api.action.SelectInvalidAction]

    @staticmethod
    def get_invalid(instance) -> List:
        invalid = []
        for obj in instance:
            if isinstance(obj, bpy.types.Object) and obj.type == 'MESH':
                if any(v < 0 for v in obj.scale):
                    invalid.append(obj)
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            names = ", ".join(obj.name for obj in invalid)
            raise PublishValidationError(
                f"Meshes found in instance with negative scale: {names}"
            )
