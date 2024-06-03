# -*- coding: utf-8 -*-
import inspect

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishValidationError,
    OptionalPyblishPluginMixin
)
from ayon_core.hosts.houdini.api.action import SelectROPAction
from ayon_core.hosts.houdini.api.usd import get_schema_type_names

import hou
from pxr import Sdf, UsdShade


class ValidateLookShaderDefs(pyblish.api.InstancePlugin,
                             OptionalPyblishPluginMixin):
    """Validate Material primitives are defined types instead of overs"""

    order = pyblish.api.ValidatorOrder
    families = ["look"]
    hosts = ["houdini"]
    label = "Validate Look Shaders Are Defined"
    actions = [SelectROPAction]
    optional = True

    # Types to validate at the low-level Sdf API
    # For Usd API we validate directly against `UsdShade.Material`
    validate_types = [
        "UsdShadeMaterial"
    ]

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        lop_node: hou.LopNode = instance.data.get("output_node")
        if not lop_node:
            return

        # Get layers below layer break
        above_break_layers = set(
            layer for layer in lop_node.layersAboveLayerBreak())
        stage = lop_node.stage()
        layers = [
            layer for layer
            in stage.GetLayerStack(includeSessionLayers=False)
            if layer.identifier not in above_break_layers
        ]
        if not layers:
            return

        # The Sdf.PrimSpec type name will not have knowledge about inherited
        # types for the type, name. So we pre-collect all invalid types
        # and their child types to ensure we match inherited types as well.
        validate_type_names = set()
        for type_name in self.validate_types:
            validate_type_names.update(get_schema_type_names(type_name))

        invalid = []
        for layer in layers:
            def log_overs(path: Sdf.Path):
                if not path.IsPrimPath():
                    return
                prim_spec = layer.GetPrimAtPath(path)

                if not prim_spec.typeName:
                    # Typeless may mean Houdini generated the material or
                    # shader as override because upstream the nodes already
                    # existed. So we check the stage instead to identify
                    # the composed type of the prim
                    prim = stage.GetPrimAtPath(path)
                    if not prim:
                        return

                    if not prim.IsA(UsdShade.Material):
                        return

                    self.log.debug("Material Prim has no type defined: %s",
                                   path)

                elif prim_spec.typeName not in validate_type_names:
                    return

                if prim_spec.specifier != Sdf.SpecifierDef:
                    specifier = {
                        Sdf.SpecifierDef: "Def",
                        Sdf.SpecifierOver: "Over",
                        Sdf.SpecifierClass: "Class"
                    }[prim_spec.specifier]

                    self.log.warning(
                        "Material is not defined but specified as "
                        "'%s': %s", specifier, path
                    )
                    invalid.append(path)

            layer.Traverse("/", log_overs)

        if invalid:
            raise PublishValidationError(
                "Found Materials not specifying an authored definition.",
                title="Materials not defined",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc(
            """### Materials are not defined types

            There are materials in your current look that do not **define** the
            material primitives, but rather **override** or specify a
            **class**. This is most likely not what you want since you want
            most looks to define new materials instead of overriding existing
            materials.

            Usually this happens if your current scene loads an input asset
            that already has the materials you're creating in your current
            scene as well. For example, if you are loading the Asset that
            contains the previously publish of your look without muting the
            look layer. As such, Houdini sees the materials already exist and
            will not make new definitions, but only write "override changes".
            However, once your look publish would replace the previous one then
            suddenly the materials would be missing and only specified as
            overrides.

            So, in most cases this is solved by Layer Muting upstream the
            look layers of the loaded asset.

            If for a specific case the materials already existing in the input
            is correct then you can either specify new material names for what
            you're creating in the current scene or disable this validation
            if you are sure you want to write overrides in your look publish
            instead of definitions.
            """
        )
