# -*- coding: utf-8 -*-
"""Creator plugin for creating camera."""
from ayon_max.api import plugin


class CreateRedshiftProxy(plugin.MaxCreator):
    identifier = "io.openpype.creators.max.redshiftproxy"
    label = "Redshift Proxy"
    product_type = "redshiftproxy"
    icon = "gear"

    settings_category = "max"
