# -*- coding: utf-8 -*-
from maya import cmds  # noqa
import pyblish.api
from ayon_maya.api import plugin
from pprint import pformat


class CollectUnrealStaticMesh(plugin.MayaInstancePlugin):
    """Collect Unreal Static Mesh."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Unreal Static Meshes"
    families = ["staticMesh"]

    def process(self, instance):
        geometry_set = [
            i for i in instance
            if i.startswith("geometry_SET")
        ]
        instance.data["geometryMembers"] = cmds.sets(
            geometry_set, query=True)

        self.log.debug("geometry: {}".format(
            pformat(instance.data.get("geometryMembers"))))

        collision_set = [
            i for i in instance
            if i.startswith("collisions_SET")
        ]
        instance.data["collisionMembers"] = cmds.sets(
            collision_set, query=True)

        self.log.debug("collisions: {}".format(
            pformat(instance.data.get("collisionMembers"))))

        frame = cmds.currentTime(query=True)
        instance.data["frameStart"] = frame
        instance.data["frameEnd"] = frame
