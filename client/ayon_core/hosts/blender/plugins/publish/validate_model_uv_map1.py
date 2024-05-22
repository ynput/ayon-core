import inspect
from typing import List

import bpy

import pyblish.api

from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError,
    RepairAction
)
import ayon_core.hosts.blender.api.action


class ValidateModelMeshUvMap1(
        pyblish.api.InstancePlugin,
        OptionalPyblishPluginMixin,
):
    """Validate model mesh uvs are named `map1`.

    This is solely to get them to work nicely for the Maya pipeline.
    """

    order = ValidateContentsOrder
    hosts = ["blender"]
    families = ["model"]
    label = "Mesh UVs named map1"
    actions = [ayon_core.hosts.blender.api.action.SelectInvalidAction,
               RepairAction]
    optional = True
    enabled = False

    @classmethod
    def get_invalid(cls, instance) -> List:

        invalid = []
        for obj in instance:
            if obj.mode != "OBJECT":
                cls.log.warning(
                    f"Mesh object {obj.name} should be in 'OBJECT' mode"
                    " to be properly checked."
                )

            obj_data = obj.data
            if isinstance(obj_data, bpy.types.Mesh):
                mesh = obj_data

                # Ignore mesh without UVs
                if not mesh.uv_layers:
                    continue

                # If mesh has map1 all is ok
                if mesh.uv_layers.get("map1"):
                    continue

                cls.log.warning(
                    f"Mesh object {obj.name} should be in 'OBJECT' mode"
                    " to be properly checked."
                )
                invalid.append(obj)

        return invalid

    @classmethod
    def repair(cls, instance):
        for obj in cls.get_invalid(instance):
            mesh = obj.data

            # Rename the first UV set to map1
            mesh.uv_layers[0].name = "map1"

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                f"Meshes found in instance without valid UV's: {invalid}",
                description=self.get_description()
            )

    def get_description(self):
        return inspect.cleandoc(
            """## Meshes must have map1 uv set

            To accompany a better Maya-focused pipeline with Alembics it is
            expected that a Mesh has a `map1` UV set. Blender defaults to
            a UV set named `UVMap` and thus needs to be renamed.

            """
        )
