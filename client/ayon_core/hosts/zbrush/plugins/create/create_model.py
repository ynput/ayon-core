# -*- coding: utf-8 -*-
"""Creator plugin for model."""
from ayon_core.lib import NumberDef
from ayon_core.hosts.zbrush.api import plugin


class CreateModel(plugin.ZbrushCreator):
    """Creator plugin for Model."""
    identifier = "io.ayon.creators.zbrush.model"
    label = "Model"
    product_type = "model"
    icon = "gear"

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
            NumberDef("subd_level",
                      label="Subdivision Level",
                      decimals=0,
                      minimum=0,
                      default=0)
        ]

    def get_pre_create_attr_defs(self):
        return self.get_instance_attr_defs()
