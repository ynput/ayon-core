# -*- coding: utf-8 -*-
"""Creator plugin for model."""
from ayon_core.lib import NumberDef
from ayon_core.hosts.zbrush.api import plugin


class CreateModel(plugin.ZbrushCreator):
    """Creator plugin for Model."""
    identifier = "io.ayon.creators.zbrush.model"
    label = "Model"
    product_type = "model"
    icon = "cube"

    def create(self, product_name, instance_data, pre_create_data):
        creator_attributes = instance_data.setdefault(
            "creator_attributes", dict())
        for key in ["subd_level"]:
            if key in pre_create_data:
                creator_attributes[key] = pre_create_data[key]

        super(CreateModel, self).create(
            product_name,
            instance_data,
            pre_create_data)

    def get_instance_attr_defs(self):
        return [
            NumberDef(
                "subd_level",
                label="Subdivision Level",
                decimals=0,
                minimum=-10,
                default=0,
                tooltip=(
                    "A level of 1 or higher sets the level to export at.\n"
                    "A level of 0 means 'Use tool's current subdiv level'.\n"
                    "A level of -1 or lower subtracts from the highest subdiv,"
                    "\n    for example -1 means highest subdiv level."
                )
            )
        ]

    def get_pre_create_attr_defs(self):
        return self.get_instance_attr_defs()
