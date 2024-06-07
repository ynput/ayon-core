# -*- coding: utf-8 -*-
"""Creator of online files.

Online file retain their original name and use it as product name. To
avoid conflicts, this creator checks if product with this name already
exists under selected folder.
"""
from pathlib import Path

# import ayon_api

from ayon_core.lib.attribute_definitions import FileDef, BoolDef
from ayon_core.pipeline import (
    CreatedInstance,
    CreatorError
)
from ayon_traypublisher.api.plugin import TrayPublishCreator


class OnlineCreator(TrayPublishCreator):
    """Creates instance from file and retains its original name."""

    identifier = "io.ayon.creators.traypublisher.online"
    label = "Online"
    product_type = "online"
    description = "Publish file retaining its original file name"
    extensions = [".mov", ".mp4", ".mxf", ".m4v", ".mpg", ".exr",
                  ".dpx", ".tif", ".png", ".jpg"]

    def get_detail_description(self):
        return """# Create file retaining its original file name.

        This will publish files using template helping to retain original
        file name and that file name is used as product name.

        Bz default it tries to guard against multiple publishes of the same
        file."""

    def get_icon(self):
        return "fa.file"

    def create(self, product_name, instance_data, pre_create_data):
        repr_file = pre_create_data.get("representation_file")
        if not repr_file:
            raise CreatorError("No files specified")

        files = repr_file.get("filenames")
        if not files:
            # this should never happen
            raise CreatorError("Missing files from representation")

        origin_basename = Path(files[0]).stem

        # disable check for existing product with the same name
        """
        folder_entity = ayon_api.get_folder_by_path(
            self.project_name, instance_data["folderPath"], fields={"id"})

        if ayon_api.get_product_by_name(
                self.project_name, origin_basename, folder_entity["id"],
                fields={"id"}):
            raise CreatorError(f"product with {origin_basename} already "
                               "exists in selected folder")
        """

        instance_data["originalBasename"] = origin_basename
        product_name = origin_basename

        instance_data["creator_attributes"] = {
            "path": (Path(repr_file["directory"]) / files[0]).as_posix()
        }

        # Create new instance
        new_instance = CreatedInstance(self.product_type, product_name,
                                       instance_data, self)
        self._store_new_instance(new_instance)

    def get_instance_attr_defs(self):
        return [
            BoolDef(
                "add_review_family",
                default=True,
                label="Review"
            )
        ]

    def get_pre_create_attr_defs(self):
        return [
            FileDef(
                "representation_file",
                folders=False,
                extensions=self.extensions,
                allow_sequences=True,
                single_item=True,
                label="Representation",
            ),
            BoolDef(
                "add_review_family",
                default=True,
                label="Review"
            )
        ]

    def get_product_name(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name=None,
        instance=None
    ):
        if instance is None:
            return "{originalBasename}"

        return instance.data["productName"]
