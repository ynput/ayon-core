# -*- coding: utf-8 -*-
import unreal

from ayon_core.pipeline import CreatorError
from ayon_unreal.api.pipeline import UNREAL_VERSION
from ayon_unreal.api.plugin import (
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
            sel_objects = unreal.EditorUtilityLibrary.get_selected_assets()
            selection = [a.get_path_name() for a in sel_objects]

            if len(selection) != 1:
                raise CreatorError("Please select only one object.")

        # Add the current level path to the metadata
        if UNREAL_VERSION.major == 5:
            world = unreal.UnrealEditorSubsystem().get_editor_world()
        else:
            world = unreal.EditorLevelLibrary.get_editor_world()

        instance_data["level"] = world.get_path_name()

        super(CreateCamera, self).create(
            product_name,
            instance_data,
            pre_create_data)
