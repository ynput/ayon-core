from pathlib import Path

from ayon_core.pipeline import (
    CreatedInstance,
)

from ayon_core.lib.attribute_definitions import (
    FileDef,
    BoolDef,
    TextDef,
)
from ayon_traypublisher.api.plugin import TrayPublishCreator


class EditorialPackageCreator(TrayPublishCreator):
    """Creates instance for OTIO file from published folder.

    Folder contains OTIO file and exported .mov files. Process should publish
    whole folder as single `editorial_pkg` product type and (possibly) convert
    .mov files into different format and copy them into `publish` `resources`
    subfolder.
    """
    identifier = "editorial_pkg"
    label = "Editorial package"
    product_type = "editorial_pkg"
    description = "Publish folder with OTIO file and resources"

    # Position batch creator after simple creators
    order = 120

    conversion_enabled = False

    def apply_settings(self, project_settings):
        self.conversion_enabled = (
            project_settings["traypublisher"]
                            ["publish"]
                            ["ExtractEditorialPckgConversion"]
                            ["conversion_enabled"]
        )

    def get_icon(self):
        return "fa.folder"

    def create(self, product_name, instance_data, pre_create_data):
        folder_path = pre_create_data.get("folder_path")
        if not folder_path:
            return

        instance_data["creator_attributes"] = {
            "folder_path": (Path(folder_path["directory"]) /
                            Path(folder_path["filenames"][0])).as_posix(),
            "conversion_enabled": pre_create_data["conversion_enabled"]
        }

        # Create new instance
        new_instance = CreatedInstance(self.product_type, product_name,
                                       instance_data, self)
        self._store_new_instance(new_instance)

    def get_pre_create_attr_defs(self):
        # Use same attributes as for instance attributes
        return [
            FileDef(
                "folder_path",
                folders=True,
                single_item=True,
                extensions=[],
                allow_sequences=False,
                label="Folder path"
            ),
            BoolDef("conversion_enabled",
                    tooltip="Convert to output defined in Settings.",
                    default=self.conversion_enabled,
                    label="Convert resources"),
        ]

    def get_instance_attr_defs(self):
        return [
            TextDef(
                "folder_path",
                label="Folder path",
                disabled=True
            ),
            BoolDef("conversion_enabled",
                    tooltip="Convert to output defined in Settings.",
                    label="Convert resources"),
        ]

    def get_detail_description(self):
        return """# Publish folder with OTIO file and video clips

        Folder contains OTIO file and exported .mov files. Process should
        publish whole folder as single `editorial_pkg` product type and
        (possibly) convert .mov files into different format and copy them into
        `publish` `resources` subfolder.
        """
