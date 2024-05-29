# -*- coding: utf-8 -*-
"""Creator plugin for creating pointcache alembics."""
from ayon_core.hosts.max.api import plugin


class CreatePointCache(plugin.MaxCreator):
    """Creator plugin for Point caches."""
    identifier = "io.openpype.creators.max.pointcache"
    label = "Point Cache"
    product_type = "pointcache"
    icon = "gear"
