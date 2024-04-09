# -*- coding: utf-8 -*-
from maya import cmds  # noqa
import pyblish.api
from ayon_core.pipeline import OptionalPyblishPluginMixin


class CollectFbxAnimation(pyblish.api.InstancePlugin,
                          OptionalPyblishPluginMixin):
    """Collect Animated Rig Data for FBX Extractor."""

    order = pyblish.api.CollectorOrder + 0.2
    label = "Collect Fbx Animation"
    hosts = ["maya"]
    families = ["animation"]
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        skeleton_sets = [
            i for i in instance
            if i.endswith("skeletonAnim_SET")
        ]
        if not skeleton_sets:
            self.log.debug(
                "No animated skeleton found in instance: `{}`".format(
                    instance.name
                ))
            return

        instance.data["families"].append("animation.fbx")
        instance.data["animated_skeleton"] = []
        for skeleton_set in skeleton_sets:
            if not skeleton_set:
                self.log.debug(f"Skipping empty skeleton set: {skeleton_set}")
                continue
            skeleton_content = cmds.sets(skeleton_set, query=True)
            self.log.debug(
                "Collected animated skeleton data in {}: {}".format(
                    skeleton_set,
                    skeleton_content
                ))
            if skeleton_content:
                instance.data["animated_skeleton"] = skeleton_content
