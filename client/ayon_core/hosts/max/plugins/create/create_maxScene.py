# -*- coding: utf-8 -*-
"""Creator plugin for creating raw max scene."""
from ayon_core.hosts.max.api import plugin


class CreateMaxScene(plugin.MaxCreator):
    """Creator plugin for 3ds max scenes."""
    identifier = "io.openpype.creators.max.maxScene"
    label = "Max Scene"
    product_type = "maxScene"
    icon = "gear"
