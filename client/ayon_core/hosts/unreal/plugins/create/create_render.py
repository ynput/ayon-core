# -*- coding: utf-8 -*-
from ayon_core.hosts.unreal.api.plugin import (
    UnrealAssetCreator
)
from ayon_core.hosts.unreal.api.pipeline import (
    send_request
)
from ayon_core.pipeline import CreatorError
from ayon_core.lib import (
    UILabelDef,
    UISeparatorDef,
    BoolDef,
    NumberDef
)


class CreateRender(UnrealAssetCreator):
    """Create instance for sequence for rendering"""

    identifier = "io.ayon.creators.unreal.render"
    label = "Render"
    product_type = "render"
    icon = "eye"

    def create_instance(
            self, instance_data, product_name, pre_create_data,
            selected_asset_path, master_seq, master_lvl, seq_data
    ):
        instance_data["members"] = [selected_asset_path]
        instance_data["sequence"] = selected_asset_path
        instance_data["master_sequence"] = master_seq
        instance_data["master_level"] = master_lvl
        instance_data["output"] = seq_data.get('output')
        instance_data["frameStart"] = seq_data.get('frame_range')[0]
        instance_data["frameEnd"] = seq_data.get('frame_range')[1]

        super(CreateRender, self).create(
            product_name,
            instance_data,
            pre_create_data)

    def create_with_new_sequence(
            self, product_name, instance_data, pre_create_data
    ):
        # If the option to create a new level sequence is selected,
        # create a new level sequence and a master level.
        root = "/Game/Ayon/Sequences"
        sequence_dir = f"{root}/{product_name}"

        master_lvl, sequence, seq_data = send_request(
            "create_render_with_new_sequence",
            params={
                "sequence_dir": sequence_dir,
                "subset_name": product_name,
                "start_frame": pre_create_data.get("start_frame"),
                "end_frame": pre_create_data.get("end_frame")
            })

        pre_create_data["members"] = [sequence]

        self.create_instance(
            instance_data, product_name, pre_create_data,
            sequence, sequence, master_lvl, seq_data)

    def create_from_existing_sequence(
            self, product_name, instance_data, pre_create_data
    ):
        sel_objects = send_request("get_selected_assets")

        if not sel_objects:
            raise CreatorError("Please select at least one Level Sequence.")

        for selected_asset_path in sel_objects:
            master_lvl, master_seq, seq_data = send_request(
                "create_render_from_existing_sequence",
                params={
                    "selected_asset_path": selected_asset_path,
                    "use_hierarchy": pre_create_data.get("use_hierarchy")
                })

            # If we didn't find the selected asset, we don't create the
            # instance.
            if not seq_data:
                message = (f"Skipping {selected_asset_path}. It isn't a "
                           "sub-sequence of the master sequence.")
                send_request(
                    "log", params={"message": message, "level": "warning"})

                continue

            self.create_instance(
                instance_data, product_name, pre_create_data,
                selected_asset_path, master_seq, master_lvl, seq_data)

    def create(self, product_name, instance_data, pre_create_data):
        if pre_create_data.get("create_seq"):
            self.create_with_new_sequence(
                product_name, instance_data, pre_create_data)
        else:
            self.create_from_existing_sequence(
                product_name, instance_data, pre_create_data)

    def get_pre_create_attr_defs(self):
        return [
            UILabelDef(
                "Select a Level Sequence to render or create a new one."
            ),
            BoolDef(
                "create_seq",
                label="Create a new Level Sequence",
                default=False
            ),
            UILabelDef(
                "WARNING: If you create a new Level Sequence, the current\n"
                "level will be saved and a new Master Level will be created."
            ),
            NumberDef(
                "start_frame",
                label="Start Frame",
                default=0,
                minimum=-999999,
                maximum=999999
            ),
            NumberDef(
                "end_frame",
                label="Start Frame",
                default=150,
                minimum=-999999,
                maximum=999999
            ),
            UISeparatorDef(),
            UILabelDef(
                "The following settings are valid only if you are not\n"
                "creating a new sequence."
            ),
            BoolDef(
                "use_hierarchy",
                label="Use Hierarchy",
                default=False
            ),
        ]
