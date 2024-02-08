# -*- coding: utf-8 -*-
"""Creator plugin for creating camera."""
from ayon_core.hosts.max.api import plugin
from ayon_core.pipeline import CreatedInstance


class CreateRedshiftProxy(plugin.MaxCreator):
    identifier = "io.openpype.creators.max.redshiftproxy"
    label = "Redshift Proxy"
    family = "redshiftproxy"
    icon = "gear"
