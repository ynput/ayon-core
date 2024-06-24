import os
import json
from ayon_maya.api import lib
from ayon_maya.api import plugin
from maya import cmds


class ExtractOxCache(plugin.MayaExtractorPlugin):
    """Producing Ornatrix cache files using scene time range.

    This will extract Ornatrix cache file sequence and fur settings.
    """

    label = "Extract Ornatrix Cache"
    families = ["oxrig", "oxcache"]

    def process(self, instance):
        cmds.loadPlugin("Ornatrix", quiet=True)
        # Define extract output file path
        ox_nodes = cmds.ls(instance[:], long=True)
        dirname = self.staging_dir(instance)
        attr_values = instance.data["creator_attributes"]
        # Start writing the files for snap shot
        ox_abc_path = os.path.join(dirname, "{}ornatrix.abc".format(
            instance.name))
        ox_export_option = self.ox_option(attr_values)
        with lib.maintained_selection():
            cmds.select(ox_nodes, noExpand=True)
            cmds.file(ox_abc_path,
                      force=True,
                      exportSelected=True,
                      typ="Ornatrix Alembic",
                      options=ox_export_option)

        settings = instance.data["cachesettings"]
        self.log.debug("Writing metadata file")
        cachesettings_path = os.path.join(dirname, "ornatrix.cachesettings")
        with open(cachesettings_path, "w") as fp:
            json.dump(settings, fp, ensure_ascii=False)

        # build representations
        if "representations" not in instance.data:
            instance.data["representations"] = []

        instance.data["representations"].append(
            {
                'name': 'abc',
                'ext': 'abc',
                'files': os.path.basename(ox_abc_path),
                'stagingDir': dirname
            }
        )

        instance.data["representations"].append(
            {
                'name': 'cachesettings',
                'ext': 'cachesettings',
                'files': os.path.basename(cachesettings_path),
                'stagingDir': dirname
            }
        )

        self.log.debug("Extracted {} to {}".format(instance, dirname))

    def ox_option(self, attr_values):
        """Get Ornatrix export options

        Args:
            instance (pyblish.api.Instance): Instance

        Returns:
            str: export options command
        """
        ox_export_options = []
        for key, value in attr_values.items():
            export_option = None
            if key == "frameStart":
                export_option = "fromTime={}".format(int(value))
            elif key == "frameEnd":
                export_option = "toTime={}".format(int(value))
            elif isinstance(key, bool):
                export_option = "{}={}".format(key, int(value))
            else:
                export_option = "{}={}".format(key, value)
            ox_export_options.append(export_option)
        ox_export_option = ";".join(ox_export_options)
        return ox_export_option
