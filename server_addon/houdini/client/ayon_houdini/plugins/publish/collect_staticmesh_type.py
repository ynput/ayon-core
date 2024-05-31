# -*- coding: utf-8 -*-
"""Collector for staticMesh types. """

import pyblish.api
from ayon_houdini.api import plugin


class CollectStaticMeshType(plugin.HoudiniInstancePlugin):
    """Collect data type for fbx instance."""

    families = ["staticMesh"]
    label = "Collect type of staticMesh"

    order = pyblish.api.CollectorOrder

    def process(self, instance):

        if instance.data["creator_identifier"] == "io.openpype.creators.houdini.staticmesh.fbx":  # noqa: E501
            # Marking this instance as FBX triggers the FBX extractor.
            instance.data["families"] += ["fbx"]
