# -*- coding: utf-8 -*-
"""Collect AYON addons."""
import os

import pyblish.api
import ayon_api

from ayon_core.lib.ayon_info import (
    get_settings_variant,
    get_ayon_info,
    is_dev_mode_enabled,
)
from ayon_core.addon import AddonsManager


class CollectAddons(pyblish.api.ContextPlugin):
    """Collect AYON addons."""

    order = pyblish.api.CollectorOrder - 0.5
    label = "AYON Addons"

    def process(self, context):
        manager = AddonsManager()
        context.data["ayonAddonsManager"] = manager
        context.data["ayonAddons"] = manager.addons_by_name

        items = []
        title_name = "Name"
        title_version = "Version"
        longest_name = len(title_name)
        longest_version = len(title_version)
        for addon in sorted(manager.addons, key=lambda x: x.name):
            addon_name = addon.name
            addon_version = addon.version or "N/A"
            longest_name = max(longest_name, len(addon_name))
            longest_version = max(longest_version, len(addon_version))
            items.append((addon_name, addon_version))

        template = f"{{:<{longest_name}}} | {{:<{longest_version}}}"
        title = template.format(title_name, title_version)
        bundle_name = os.getenv("AYON_BUNDLE_NAME")
        if is_dev_mode_enabled():
            settings_variant = "dev"
        else:
            settings_variant = get_settings_variant()

        server_version = ayon_api.get_server_version()

        ayon_info = get_ayon_info()
        launcher_version = ayon_info["ayon_launcher_version"]
        launcher_type = ayon_info["version_type"]
        lines = [
            "Basic AYON information:",
            f"AYON server: {server_version}",
            f"Bundle: {bundle_name} ({settings_variant})",
            f"AYON launcher: {launcher_version} ({launcher_type})",
            "Addons:",
            len(title) * "-",
            title,
            len(title) * "-",
        ]
        lines.extend(
            template.format(addon_name, addon_version)
            for addon_name, addon_version in items
        )
        self.log.debug("\n".join(lines))
