import copy
import os

import pyblish.api

import substance_painter.export

from ayon_core.pipeline import PublishValidationError


class ValidateOutputMaps(pyblish.api.InstancePlugin):
    """Validate all output maps for Output Template are generated.

    Output maps will be skipped by Substance Painter if it is an output
    map in the Substance Output Template which uses channels that the current
    substance painter project has not painted or generated.

    """

    order = pyblish.api.ValidatorOrder
    label = "Validate output maps"
    hosts = ["substancepainter"]
    families = ["textureSet"]

    def process(self, instance):

        config = instance.data["exportConfig"]

        # Substance Painter API does not allow to query the actual output maps
        # it will generate without actually exporting the files. So we try to
        # generate the smallest size / fastest export as possible
        config = copy.deepcopy(config)
        invalid_channels = self.get_invalid_channels(instance, config)
        if invalid_channels:
            raise PublishValidationError(
                "Invalid Channel(s): {} found in texture set {}".format(
                    invalid_channels, instance.name
                ))
        parameters = config["exportParameters"][0]["parameters"]
        parameters["sizeLog2"] = [1, 1]     # output 2x2 images (smallest)
        parameters["paddingAlgorithm"] = "passthrough"  # no dilation (faster)
        parameters["dithering"] = False     # no dithering (faster)
        result = substance_painter.export.export_project_textures(config)
        if result.status != substance_painter.export.ExportStatus.Success:
            raise PublishValidationError(
                "Failed to export texture set: {}".format(result.message)
            )

        generated_files = set()
        for texture_maps in result.textures.values():
            for texture_map in texture_maps:
                generated_files.add(os.path.normpath(texture_map))
                # Directly clean up our temporary export
                os.remove(texture_map)

        creator_attributes = instance.data.get("creator_attributes", {})
        allow_skipped_maps = creator_attributes.get("allowSkippedMaps", True)
        error_report_missing = []
        for image_instance in instance:

            # Confirm whether the instance has its expected files generated.
            # We assume there's just one representation and that it is
            # the actual texture representation from the collector.
            representation = next(iter(image_instance.data["representations"]))
            staging_dir = representation["stagingDir"]
            filenames = representation["files"]
            if not isinstance(filenames, (list, tuple)):
                # Convert single file to list
                filenames = [filenames]

            missing = []
            for filename in filenames:
                filepath = os.path.join(staging_dir, filename)
                filepath = os.path.normpath(filepath)
                if filepath not in generated_files:
                    self.log.warning(f"Missing texture: {filepath}")
                    missing.append(filepath)

            if not missing:
                continue

            if allow_skipped_maps:
                # TODO: This is changing state on the instance's which
                #   should not be done during validation.
                self.log.warning(f"Disabling texture instance: "
                                 f"{image_instance}")
                image_instance.data["active"] = False
                image_instance.data["publish"] = False
                image_instance.data["integrate"] = False
                representation.setdefault("tags", []).append("delete")
                continue
            else:
                error_report_missing.append((image_instance, missing))

        if error_report_missing:

            message = (
                "The Texture Set skipped exporting some output maps which are "
                "defined in the Output Template. This happens if the Output "
                "Templates exports maps from channels which you do not "
                "have in your current Substance Painter project.\n\n"
                "To allow this enable the *Allow Skipped Output Maps* setting "
                "on the instance.\n\n"
                f"Instance {instance} skipped exporting output maps:\n"
                ""
            )

            for image_instance, missing in error_report_missing:
                missing_str = ", ".join(missing)
                message += f"- **{image_instance}** skipped: {missing_str}\n"

            raise PublishValidationError(
                message=message,
                title="Missing output maps"
            )

    def get_invalid_channels(self, instance, config):
        """Function to get invalid channel(s) from export channel
        filtering

        Args:
            instance (pyblish.api.Instance): Instance
            config (dict): export config

        Raises:
            PublishValidationError: raise Publish Validation
                Error if any invalid channel(s) found

        Returns:
            list: invalid channel(s)
        """
        creator_attrs = instance.data["creator_attributes"]
        export_channel = creator_attrs.get("exportChannel", [])
        tmp_export_channel = copy.deepcopy(export_channel)
        invalid_channel = []
        if export_channel:
            for export_preset in config.get("exportPresets", {}):
                if not export_preset.get("maps", {}):
                    raise PublishValidationError(
                        "No Texture Map Exported with texture set: {}.".format(
                            instance.name)
                    )
                map_names = [channel_map["fileName"] for channel_map
                             in export_preset["maps"]]
                for channel in tmp_export_channel:
                    # Check if channel is found in at least one map
                    for map_name in map_names:
                        if channel in map_name:
                            break
                    else:
                        invalid_channel.append(channel)

        return invalid_channel
