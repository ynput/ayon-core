"""
Requires:
    context     -> anatomy
    context     -> anatomyData

Provides:
    instance    -> publishDir
    instance    -> resourcesDir
"""

import os
import copy

import pyblish.api

from ayon_core.pipeline.publish import get_publish_template_name
from ayon_core.pipeline.context_tools import get_current_host_name


class CollectResourcesPath(pyblish.api.InstancePlugin):
    """Generate directory path where the files and resources will be stored.

    Collects folder name and file name from files, if exists, for in-situ
    publishing.
    """

    label = "Collect Resources Path"
    order = pyblish.api.CollectorOrder + 0.495
    families = ["workfile",
                "pointcache",
                "proxyAbc",
                "camera",
                "animation",
                "model",
                "mayaAscii",
                "mayaScene",
                "setdress",
                "layout",
                "ass",
                "vdbcache",
                "scene",
                "vrayproxy",
                "render",
                "prerender",
                "imagesequence",
                "rendersetup",
                "rig",
                "plate",
                "look",
                "mvLook",
                "yetiRig",
                "yeticache",
                "nukenodes",
                "gizmo",
                "source",
                "matchmove",
                "image",
                "source",
                "assembly",
                "fbx",
                "gltf",
                "textures",
                "action",
                "background",
                "effect",
                "staticMesh",
                "skeletalMesh",
                "xgen",
                "yeticacheUE",
                "tycache",
                "usd",
                "oxrig",
                "sbsar",
                ]

    def process(self, instance):
        anatomy = instance.context.data["anatomy"]

        template_data = copy.deepcopy(instance.data["anatomyData"])

        # This is for cases of Deprecated anatomy without `folder`
        # TODO remove when all clients have solved this issue
        template_data.update({"frame": "FRAME_TEMP", "representation": "TEMP"})

        template_name = get_publish_template_name(
            project_name=template_data["project"]["name"],
            host_name=get_current_host_name(),
            product_type=template_data["product"]["type"],
            task_name=template_data["product"]["name"],
            task_type=template_data["product"]["type"],
            project_settings=instance.context.data["project_settings"],
            logger=self.log,
        )

        publish_template = anatomy.get_template_item(
            "publish", template_name, "directory")

        publish_folder = os.path.normpath(
            publish_template.format_strict(template_data)
        )
        resources_folder = os.path.join(publish_folder, "resources")

        instance.data["publishDir"] = publish_folder
        instance.data["resourcesDir"] = resources_folder

        self.log.debug("publishDir: \"{}\"".format(publish_folder))
        self.log.debug("resourcesDir: \"{}\"".format(resources_folder))
