# -*- coding: utf-8 -*-
"""Extract Ornatrix rig."""

import os
import json

from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds, mel


class ExtractOxRig(plugin.MayaExtractorPlugin):
    """Extract the Ornatrix rig to a Maya Scene and write the Ornatrix rig data."""

    label = "Extract Ornatrix Rig"
    families = ["oxrig"]
    scene_type = "ma"

    def process(self, instance):
        """Plugin entry point."""
        cmds.loadPlugin("Ornatrix", quiet=True)
        maya_settings = instance.context.data["project_settings"]["maya"]
        ext_mapping = {
            item["name"]: item["value"]
            for item in maya_settings["ext_mapping"]
        }
        if ext_mapping:
            self.log.debug("Looking in settings for scene type ...")
            # use extension mapping for first family found
            for family in self.families:
                try:
                    self.scene_type = ext_mapping[family]
                    self.log.debug(
                        "Using {} as scene type".format(self.scene_type))
                    break
                except KeyError:
                    # no preset found
                    pass

        # Define extract output file path
        dirname = self.staging_dir(instance)
        settings_path = os.path.join(dirname, "ornatrix.rigsettings")
        image_search_path = instance.data["resourcesDir"]

        # add textures to transfers
        if 'transfers' not in instance.data:
            instance.data['transfers'] = []

        resources = instance.data.get("resources", [])
        for resource in resources:
            for file in resource['files']:
                src = file
                dst = os.path.join(image_search_path, os.path.basename(file))
                resource["destination_file"] = dst
                instance.data['transfers'].append([src, dst])

                self.log.debug("adding transfer {} -> {}". format(src, dst))

        self.log.debug("Writing metadata file: {}".format(settings_path))
        with open(settings_path, "w") as fp:
            json.dump(resources, fp, ensure_ascii=False)

        texture_attributes = {
            resource["texture_attribute"]: resource["destination_file"]
            for resource in resources
        }
        source_nodes = [resource["node"] for resource in resources]
        # Ornatrix related staging dirs
        maya_path = os.path.join(dirname,
                                 "ornatrix_rig.{}".format(self.scene_type))
        ox_groom_path = os.path.join(dirname, "ornatrix_rig.oxg.zip")
        ox_groom_path = ox_groom_path.replace("\\", "/")
        nodes = instance.data["setMembers"]
        with lib.maintained_selection():
            with lib.attribute_values(texture_attributes):
                cmds.select(nodes, noExpand=True)
                cmds.file(maya_path,
                          force=True,
                          exportSelected=True,
                          type="mayaAscii" if self.scene_type == "ma" else "mayaBinary",  # noqa: E501
                          preserveReferences=False,
                          constructionHistory=True,
                          shader=False)

        with lib.maintained_selection():
                cmds.select(source_nodes, noExpand=True)
                mel.eval(f'OxSaveGroom -path "{ox_groom_path}"')
                self.log.debug(f"{ox_groom_path}")

        # Ensure files can be stored
        # build representations
        if "representations" not in instance.data:
            instance.data["representations"] = []

        self.log.debug("rig file: {}".format(maya_path))
        instance.data["representations"].append(
            {
                'name': self.scene_type,
                'ext': self.scene_type,
                'files': os.path.basename(maya_path),
                'stagingDir': dirname
            }
        )

        self.log.debug("OxGroom file: {}".format(ox_groom_path))
        instance.data["representations"].append(
            {
                'name': "oxg.zip",
                'ext': "oxg.zip",
                'files': os.path.basename(ox_groom_path),
                'stagingDir': dirname
            }
        )

        self.log.debug("settings file: {}".format(settings_path))
        instance.data["representations"].append(
            {
                'name': "rigsettings",
                'ext': "rigsettings",
                'files': os.path.basename(settings_path),
                'stagingDir': dirname
            }
        )

        self.log.debug("Extracted {} to {}".format(instance, dirname))
