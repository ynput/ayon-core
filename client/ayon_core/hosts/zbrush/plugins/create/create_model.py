# -*- coding: utf-8 -*-
"""Creator plugin for model."""
from ayon_core.hosts.zbrush.api import plugin


class CreateModel(plugin.ZbrushCreator):
    """Creator plugin for Model."""
    identifier = "io.ayon.creators.zbrush.model"
    label = "Model"
    family = "model"
    icon = "gear"

