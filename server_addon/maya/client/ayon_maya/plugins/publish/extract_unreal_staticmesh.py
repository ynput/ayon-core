# -*- coding: utf-8 -*-
"""Create Unreal Static Mesh data to be extracted as FBX."""
import os

import pyblish.api
from ayon_maya.api import fbx
from ayon_maya.api.lib import maintained_selection, parent_nodes
from ayon_maya.api import plugin
from maya import cmds  # noqa


class ExtractUnrealStaticMesh(plugin.MayaExtractorPlugin):
    """Extract Unreal Static Mesh as FBX from Maya. """

    order = pyblish.api.ExtractorOrder - 0.1
    label = "Extract Unreal Static Mesh"
    families = ["staticMesh"]

    def process(self, instance):
        members = instance.data.get("geometryMembers", [])
        if instance.data.get("collisionMembers"):
            members = members + instance.data.get("collisionMembers")

        fbx_exporter = fbx.FBXExtractor(log=self.log)

        # Define output path
        staging_dir = self.staging_dir(instance)
        filename = "{0}.fbx".format(instance.name)
        path = os.path.join(staging_dir, filename)

        # The export requires forward slashes because we need
        # to format it into a string in a mel expression
        path = path.replace('\\', '/')

        self.log.debug("Extracting FBX to: {0}".format(path))
        self.log.debug("Members: {0}".format(members))
        self.log.debug("Instance: {0}".format(instance[:]))

        fbx_exporter.set_options_from_instance(instance)

        with maintained_selection():
            with parent_nodes(members):
                self.log.debug("Un-parenting: {}".format(members))
                fbx_exporter.export(members, path)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        representation = {
            'name': 'fbx',
            'ext': 'fbx',
            'files': filename,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extract FBX successful to: {0}".format(path))
