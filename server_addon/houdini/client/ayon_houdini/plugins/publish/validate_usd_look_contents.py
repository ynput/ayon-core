# -*- coding: utf-8 -*-
import inspect
from typing import List, Union
from functools import partial

import pyblish.api

from ayon_core.pipeline.publish import PublishValidationError
from ayon_core.hosts.houdini.api.action import SelectROPAction
from ayon_core.hosts.houdini.api.usd import get_schema_type_names

import hou
from pxr import Sdf


def get_applied_items(list_proxy) -> List[Union[Sdf.Reference, Sdf.Payload]]:
    """Backwards compatible equivalent of `GetAppliedItems()`"""
    return list_proxy.ApplyEditsToList([])


class ValidateUsdLookContents(pyblish.api.InstancePlugin):
    """Validate no meshes are defined in the look.

    Usually, a published look should not contain generated meshes in the output
    but only the materials, material bindings and render geometry settings.

    To avoid accidentally including a Mesh definition we ensure none of the
    generated output layers for the instance is defining any Mesh type.

    """

    order = pyblish.api.ValidatorOrder
    families = ["look"]
    hosts = ["houdini"]
    label = "Validate Look No Meshes/Lights"
    actions = [SelectROPAction]

    disallowed_types = [
        "UsdGeomBoundable",       # Meshes/Lights/Procedurals
        "UsdRenderSettingsBase",  # Render Settings
        "UsdRenderVar",           # Render Var
        "UsdGeomCamera"           # Cameras
    ]

    def process(self, instance):

        lop_node: hou.LopNode = instance.data.get("output_node")
        if not lop_node:
            return

        # Get layers below layer break
        above_break_layers = set(layer for layer in lop_node.layersAboveLayerBreak())
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
        disallowed_type_names = set()
        for type_name in self.disallowed_types:
            disallowed_type_names.update(get_schema_type_names(type_name))

        # Find invalid prims
        invalid = []

        def collect_invalid(layer: Sdf.Layer, path: Sdf.Path):
            """Collect invalid paths into the `invalid` list"""
            if not path.IsPrimPath():
                return

            prim = layer.GetPrimAtPath(path)
            if prim.typeName in disallowed_type_names:
                self.log.warning(
                    "Disallowed prim type '%s' at %s",
                    prim.typeName, prim.path.pathString
                )
                invalid.append(path)
                return

            # TODO: We should allow referencing or payloads, but if so - we
            #   should still check whether the loaded reference or payload
            #   introduces any geometry. If so, disallow it because that
            #   opinion would 'define' geometry in the output
            references= get_applied_items(prim.referenceList)
            if references:
                self.log.warning(
                    "Disallowed references are added at %s: %s",
                    prim.path.pathString,
                    ", ".join(ref.assetPath for ref in references)
                )
                invalid.append(path)

            payloads = get_applied_items(prim.payloadList)
            if payloads:
                self.log.warning(
                    "Disallowed payloads are added at %s: %s",
                    prim.path.pathString,
                    ", ".join(payload.assetPath for payload in payloads)
                )
                invalid.append(path)

        for layer in layers:
            layer.Traverse("/", partial(collect_invalid, layer))

        if invalid:
            raise PublishValidationError(
                "Invalid look members found.",
                title="Look Invalid Members",
                description=self.get_description()
            )

    @staticmethod
    def get_description():
        return inspect.cleandoc(
            """### Look contains invalid members

            A look publish should usually only contain materials, material
            bindings and render geometry settings.

            This validation invalidates any creation of:
            - Render Settings,
            - Lights,
            - Cameras,
            - Geometry (Meshes, Curves and other geometry types)

            To avoid writing out loaded geometry into the output make sure to
            add a Layer Break after loading all the content you do **not** want
            to save into the output file. Then your materials, material
            bindings and render geometry settings are overrides applied to the
            loaded content after the **Layer Break LOP** node.

            If you happen to write out additional data for the meshes via
            e.g. a SOP Modify make sure to import to LOPs only the relevant
            attributes, mark them as static attributes, static topology and
            set the Primitive Definitions to be Overlay instead of Defines.

            Currently, to avoid issues with referencing/payloading geometry
            from external files any references or payloads are also disallowed
            for looks.

            """
        )
