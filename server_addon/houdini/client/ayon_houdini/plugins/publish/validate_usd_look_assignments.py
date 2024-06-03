# -*- coding: utf-8 -*-
import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.hosts.houdini.api.action import SelectROPAction

import hou
from pxr import Usd, UsdShade, UsdGeom


def has_material(prim: Usd.Prim,
                 include_subsets: bool=True,
                 purpose=UsdShade.Tokens.allPurpose) -> bool:
    """Return whether primitive has any material binding."""
    search_from = [prim]
    if include_subsets:
        subsets = UsdShade.MaterialBindingAPI(prim).GetMaterialBindSubsets()
        for subset in subsets:
            search_from.append(subset.GetPrim())

    bounds = UsdShade.MaterialBindingAPI.ComputeBoundMaterials(search_from,
                                                               purpose)
    for (material, relationship) in zip(*bounds):
        material_prim = material.GetPrim()
        if material_prim.IsValid():
            # Has a material binding
            return True

    return False


class ValidateUsdLookAssignments(pyblish.api.InstancePlugin,
                                 OptionalPyblishPluginMixin):
    """Validate all geometry prims have a material binding.

    Note: This does not necessarily validate the material binding is authored
        by the current layers if the input already had material bindings.

    """

    order = pyblish.api.ValidatorOrder
    families = ["look"]
    hosts = ["houdini"]
    label = "Validate All Geometry Has Material Assignment"
    actions = [SelectROPAction]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        lop_node: hou.LopNode = instance.data.get("output_node")
        if not lop_node:
            return

        # We iterate the composed stage for code simplicity; however this
        # means that it does not validate across e.g. multiple model variants
        # but only checks against the current composed stage. Likely this is
        # also what you actually want to validate, because your look might not
        # apply to *all* model variants.
        stage = lop_node.stage()
        invalid = []
        for prim in stage.Traverse():
            if not prim.IsA(UsdGeom.Gprim):
                continue

            if not has_material(prim):
                invalid.append(prim.GetPath())

        for path in sorted(invalid):
            self.log.warning("No material binding on: %s", path.pathString)

        if invalid:
            raise PublishValidationError(
                "Found geometry without material bindings.",
                title="No assigned materials",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc(
            """### Geometry has no material assignments.

            A look publish should usually define a material assignment for all
            geometry of a model. As such, this validates whether all geometry
            currently has at least one material binding applied.

            """
        )
