# -*- coding: utf-8 -*-
"""Creator plugin for model."""
from ayon_max.api import plugin


class CreateModel(plugin.MaxCreator):
    """Creator plugin for Model."""
    identifier = "io.openpype.creators.max.model"
    label = "Model"
    product_type = "model"
    icon = "gear"

    settings_category = "max"
