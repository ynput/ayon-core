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
                "zfab",
                ]

    def process(self, instance):
        anatomy = instance.context.data["anatomy"]

        template_data = copy.deepcopy(instance.data["anatomyData"])

        # This is for cases of Deprecated anatomy without `folder`
        # TODO remove when all clients have solved this issue
        template_data.update({"frame": "FRAME_TEMP", "representation": "TEMP"})

        task_name = task_type = None
        task_entity = instance.data.get("taskEntity")
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        template_name = get_publish_template_name(
            project_name=instance.context.data["projectName"],
            host_name=instance.context.data["hostName"],
            product_type=instance.data["productType"],
            task_name=task_name,
            task_type=task_type,
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
