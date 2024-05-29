# -*- coding: utf-8 -*-
"""Creator plugin for creating TyCache."""
from ayon_max.api import plugin


class CreateTyCache(plugin.MaxCreator):
    """Creator plugin for TyCache."""
    identifier = "io.openpype.creators.max.tycache"
    label = "TyCache"
    product_type = "tycache"
    icon = "gear"

    settings_category = "max"
