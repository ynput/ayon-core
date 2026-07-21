"""Collect AYON addons."""
from __future__ import annotations

from dataclasses import dataclass
import os

import pyblish.api
import ayon_api

from ayon_core import __version__
from ayon_core.lib.ayon_info import (
    get_settings_variant,
    get_ayon_info,
    is_dev_mode_enabled,
)
from ayon_core.addon import AddonsManager, get_bundle_information


@dataclass
class AddonInfo:
    name: str
    version: str | None
    server_version: str | None
    label: str | None = None

    def get_row(
        self, name_width: int, version_width: int, server_version_width: int
    ) -> str:
        """Return formatted row for the addon info."""
        version = self.version or "-"
        server_version = self.server_version or "-"
        label = self.label or self.name

        return (
            f"{label:<{name_width}}"
            f" | {version:<{version_width}}"
            f" | {server_version:<{server_version_width}}"
        )


class CollectAddons(pyblish.api.ContextPlugin):
    """Collect AYON addons."""

    order = pyblish.api.CollectorOrder - 0.5
    label = "AYON Addons"

    def process(self, context):
        manager = AddonsManager()
        context.data["ayonAddonsManager"] = manager
        context.data["ayonAddons"] = manager.addons_by_name

        bundle_info = get_bundle_information()
        server_version_by_name = {
            addon.name: addon.version
            for addon in bundle_info.addons
        }
        server_only_addons = set(server_version_by_name)

        _addons = [
            (addon.name, addon.version or "N/A")
            for addon in manager.addons
        ]
        _addons.append(("core", __version__))

        items: list[AddonInfo] = []
        title_name = "Name"
        title_version = "Version"
        title_server_version = "Server Version"
        name_width = len(title_name)
        version_width = len(title_version)
        server_version_width = len(title_server_version)
        for addon_name, addon_version in _addons:
            server_version = server_version_by_name.get(addon_name)
            server_only_addons.discard(addon_name)
            label = addon_name
            if addon_version != server_version:
                label = f"* {addon_name}"
            name_width = max(name_width, len(label))
            version_width = max(version_width, len(addon_version))
            if server_version is not None:
                server_version_width = max(
                    server_version_width, len(server_version)
                )

            items.append(AddonInfo(
                addon_name,
                addon_version,
                server_version,
                label,
            ))

        items = []
        for addon_name in server_only_addons:
            server_version = server_version_by_name[addon_name]
            name_width = max(name_width, len(addon_name))
            server_version_width = max(
                server_version_width, len(server_version)
            )
            items.append(AddonInfo(
                addon_name,
                None,
                server_version,
            ))

        items.sort(key=lambda x: x.name)

        title = (
            f"{title_name:<{name_width}}"
            f" | {title_version:<{version_width}}"
            f" | {title_server_version:<{server_version_width}}"
        )
        bundle_name = os.getenv("AYON_BUNDLE_NAME")
        if is_dev_mode_enabled():
            settings_variant = "dev"
        else:
            settings_variant = get_settings_variant()

        server_version = ayon_api.get_server_version()

        ayon_info = get_ayon_info()
        launcher_version = ayon_info["ayon_launcher_version"]
        launcher_type = ayon_info["version_type"]
        sep_line = "+".join([
            (name_width + 1) * "-",
            (version_width + 2) * "-",
            (server_version_width + 2) * "-"
        ])
        lines = [
            "Basic AYON information:",
            f"AYON server: {server_version}",
            f"Bundle: {bundle_name} ({settings_variant})",
            f"AYON launcher: {launcher_version} ({launcher_type})",
            "Addons:",
            sep_line,
            title,
            sep_line,
        ]
        lines.extend(
            item.get_row(name_width, version_width, server_version_width)
            for item in items
        )
        lines.append(sep_line)

        self.log.debug("\n".join(lines))
