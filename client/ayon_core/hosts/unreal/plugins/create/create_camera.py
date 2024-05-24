# -*- coding: utf-8 -*-
from ayon_core.pipeline import CreatorError
from ayon_core.hosts.unreal.api.pipeline import (
    send_request,
)
from ayon_core.hosts.unreal.api.plugin import (
    UnrealAssetCreator,
)


class CreateCamera(UnrealAssetCreator):
    """Create Camera."""

    identifier = "io.ayon.creators.unreal.camera"
    label = "Camera"
    product_type = "camera"
    icon = "fa.camera"

    def create(self, product_name, instance_data, pre_create_data):
        if pre_create_data.get("use_selection"):
            selection = send_request("get_selected_assets")

            if len(selection) != 1:
                raise CreatorError("Please select only one object.")

        # Add the current level path to the metadata
        instance_data["level"] = send_request("get_editor_world")

        super(CreateCamera, self).create(
            product_name,
            instance_data,
            pre_create_data)
