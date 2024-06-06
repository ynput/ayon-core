# -*- coding: utf-8 -*-
import os

from maya import cmds  # noqa
import pyblish.api

from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_maya.api import fbx
from ayon_maya.api import plugin


class ExtractSkeletonMesh(plugin.MayaExtractorPlugin,
                          OptionalPyblishPluginMixin):
    """Extract Rig in FBX format from Maya.

    This extracts the rig in fbx with the constraints
    and referenced asset content included.
    This also optionally extract animated rig in fbx with
    geometries included.

    """
    order = pyblish.api.ExtractorOrder
    label = "Extract Skeleton Mesh"
    families = ["rig.fbx"]

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        # Define output path
        staging_dir = self.staging_dir(instance)
        filename = "{0}.fbx".format(instance.name)
        path = os.path.join(staging_dir, filename)

        fbx_exporter = fbx.FBXExtractor(log=self.log)
        out_set = instance.data.get("skeleton_mesh", [])

        instance.data["constraints"] = True
        instance.data["skeletonDefinitions"] = True

        fbx_exporter.set_options_from_instance(instance)

        # Export
        fbx_exporter.export(out_set, path)

        representations = instance.data.setdefault("representations", [])
        representations.append({
            'name': 'fbx',
            'ext': 'fbx',
            'files': filename,
            "stagingDir": staging_dir
        })

        self.log.debug("Extract FBX to: {0}".format(path))
