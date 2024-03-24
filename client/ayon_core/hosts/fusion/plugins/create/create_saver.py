from ayon_core.lib import (
    UILabelDef,
    NumberDef,
    EnumDef
)

from ayon_core.hosts.fusion.api.plugin import GenericCreateSaver
from ayon_core.hosts.fusion.api.lib import get_current_comp


class CreateSaver(GenericCreateSaver):
    """Fusion Saver to generate image sequence of 'render' product type.

     Original Saver creator targeted for 'render' product type. It uses
     original not to descriptive name because of values in Settings.
    """
    identifier = "io.openpype.creators.fusion.saver"
    label = "Render (saver)"
    name = "render"
    product_type = "render"
    description = "Fusion Saver to generate image sequence"

    default_frame_range_option = "current_folder"

    def get_detail_description(self):
        return """Fusion Saver to generate image sequence.

        This creator is expected for publishing of image sequences for 'render'
        product type. (But can publish even single frame 'render'.)

        Select what should be source of render range:
        - "Current Folder context" - values set on folder on AYON server
        - "From render in/out" - from node itself
        - "From composition timeline" - from timeline

        Supports local and farm rendering.

        Supports selection from predefined set of output file extensions:
        - exr
        - tga
        - png
        - tif
        - jpg
        """

    def get_pre_create_attr_defs(self):
        """Settings for create page"""
        attr_defs = [
            self._get_render_target_enum(),
            self._get_reviewable_bool(),
            self._get_frame_range_enum(),
            self._get_image_format_enum(),
            *self._get_custom_frame_range_attribute_defs()
        ]
        return attr_defs

    def _get_frame_range_enum(self):
        frame_range_options = {
            "current_folder": "Current Folder context",
            "render_range": "From render in/out",
            "comp_range": "From composition timeline",
            "custom_range": "Custom frame range",
        }

        return EnumDef(
            "frame_range_source",
            items=frame_range_options,
            label="Frame range source",
            default=self.default_frame_range_option
        )

    @staticmethod
    def _get_custom_frame_range_attribute_defs() -> list:

        # Define custom frame range defaults based on current comp
        # timeline settings (if a comp is currently open)
        comp = get_current_comp()
        if comp is not None:
            attrs = comp.GetAttrs()
            frame_defaults = {
                "frameStart": int(attrs["COMPN_GlobalStart"]),
                "frameEnd": int(attrs["COMPN_GlobalEnd"]),
                "handleStart": int(
                    attrs["COMPN_RenderStart"] - attrs["COMPN_GlobalStart"]
                ),
                "handleEnd": int(
                    attrs["COMPN_GlobalEnd"] - attrs["COMPN_RenderEnd"]
                ),
            }
        else:
            frame_defaults = {
                "frameStart": 1001,
                "frameEnd": 1100,
                "handleStart": 0,
                "handleEnd": 0
            }

        return [
            UILabelDef(
                label="<br><b>Custom Frame Range</b><br>"
                      "<i>only used with 'Custom frame range' source</i>"
            ),
            NumberDef(
                "custom_frameStart",
                label="Frame Start",
                default=frame_defaults["frameStart"],
                minimum=0,
                decimals=0,
                tooltip=(
                    "Set the start frame for the export.\n"
                    "Only used if frame range source is 'Custom frame range'."
                )
            ),
            NumberDef(
                "custom_frameEnd",
                label="Frame End",
                default=frame_defaults["frameEnd"],
                minimum=0,
                decimals=0,
                tooltip=(
                    "Set the end frame for the export.\n"
                    "Only used if frame range source is 'Custom frame range'."
                )
            ),
            NumberDef(
                "custom_handleStart",
                label="Handle Start",
                default=frame_defaults["handleStart"],
                minimum=0,
                decimals=0,
                tooltip=(
                    "Set the start handles for the export, this will be "
                    "added before the start frame.\n"
                    "Only used if frame range source is 'Custom frame range'."
                )
            ),
            NumberDef(
                "custom_handleEnd",
                label="Handle End",
                default=frame_defaults["handleEnd"],
                minimum=0,
                decimals=0,
                tooltip=(
                    "Set the end handles for the export, this will be added "
                    "after the end frame.\n"
                    "Only used if frame range source is 'Custom frame range'."
                )
            )
        ]
