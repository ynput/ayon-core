# -*- coding: utf-8 -*-
"""Collect AYON addons."""
import pyblish.api

from ayon_core.addon import AddonsManager


class CollectAddons(pyblish.api.ContextPlugin):
    """Collect AYON addons."""

    order = pyblish.api.CollectorOrder - 0.5
    label = "AYON Addons"

    def process(self, context):
        manager = AddonsManager()
        context.data["ayonAddonsManager"] = manager
        context.data["ayonAddons"] = manager.addons_by_name
