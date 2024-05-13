# -*- coding: utf-8 -*-
import os
from contextlib import nullcontext

import pyblish.api
from ayon_core.hosts.maya.api import lib
from ayon_core.pipeline import publish
from maya import cmds


class ExtractObj(publish.Extractor):
    """Extract OBJ from Maya.

    This extracts reproducible OBJ exports ignoring any of the settings
    set on the local machine in the OBJ export options window.

    """
    order = pyblish.api.ExtractorOrder
    hosts = ["maya"]
    label = "Extract OBJ"
    families = ["model"]

    # OBJ export options
    obj_options = {
        "groups": 1,
        "ptgroups": 1,
        "materials": 1,
        "smoothing": 1,
        "normals": 1,
    }

    def process(self, instance):

        # Define output path

        staging_dir = self.staging_dir(instance)
        filename = "{0}.obj".format(instance.name)
        path = os.path.join(staging_dir, filename)

        # The export requires forward slashes because we need to
        # format it into a string in a mel expression

        self.log.debug("Extracting OBJ to: {0}".format(path))

        members = instance.data("setMembers")
        members = cmds.ls(members,
                          dag=True,
                          shapes=True,
                          type=("mesh", "nurbsCurve"),
                          noIntermediate=True,
                          long=True)
        self.log.debug("Members: {0}".format(members))
        self.log.debug("Instance: {0}".format(instance[:]))

        if not cmds.pluginInfo('objExport', query=True, loaded=True):
            cmds.loadPlugin('objExport')

        strip_shader = instance.data.get("strip_shaders", True)
        if strip_shader:
            self.obj_options["materials"] = 0

        # Export
        with lib.no_display_layers(instance):
            with lib.displaySmoothness(members,
                                       divisionsU=0,
                                       divisionsV=0,
                                       pointsWire=4,
                                       pointsShaded=1,
                                       polygonObject=1):
                with lib.shader(members,
                                shadingEngine="initialShadingGroup") if strip_shader else nullcontext():  # noqa: E501
                    with lib.maintained_selection():
                        cmds.select(members, noExpand=True)
                        cmds.file(path,
                                  exportSelected=True,
                                  type='OBJexport',
                                  op=';'.join(f"{key}={val}" for key, val in self.obj_options.items()),  # noqa: E501
                                  preserveReferences=True,
                                  force=True)

        if "representation" not in instance.data:
            instance.data["representation"] = []

        representation = {
            'name': 'obj',
            'ext': 'obj',
            'files': filename,
            "stagingDir": staging_dir,
        }
        instance.data["representations"].append(representation)

        self.log.debug("Extract OBJ successful to: {0}".format(path))
