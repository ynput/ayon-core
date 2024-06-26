# -*- coding: utf-8 -*-
import pyblish.api
from ayon_maya.api import plugin


class CollectGLTF(plugin.MayaInstancePlugin):
    """Collect Assets for GLTF/GLB export."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Asset for GLTF/GLB export"
    families = ["model", "animation", "pointcache"]

    def process(self, instance):
        if not instance.data.get("families"):
            instance.data["families"] = []

        if "gltf" not in instance.data["families"]:
            instance.data["families"].append("gltf")
