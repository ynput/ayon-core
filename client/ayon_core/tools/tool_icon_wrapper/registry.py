"""Per-tool display names, Win32 AppUserModelIDs, and icon filenames.

Imported by :mod:`ayon_core.tools.tool_icon_wrapper.taskbar_identity` without
depending on the full tray package.
"""

from __future__ import annotations

from typing import Optional

TOOL_IDENTITIES: dict[str, dict[str, str]] = {
    "publisher": {
        "display_name": "AYON Publisher",
        "app_id": "io.ynput.ayon.publisher",
        "icon": "publish.png",
    },
    "loader": {
        "display_name": "AYON Loader",
        "app_id": "io.ynput.ayon.loader",
        "icon": "loader.png",
    },
    "workfiles": {
        "display_name": "AYON Workfiles",
        "app_id": "io.ynput.ayon.workfiles",
        "icon": "workfiles.png",
    },
    "scene_inventory": {
        "display_name": "AYON Scene Inventory",
        "app_id": "io.ynput.ayon.sceneinventory",
        "icon": "inventory.png",
    },
    "launcher": {
        "display_name": "AYON Launcher",
        "app_id": "io.ynput.ayon.launcher",
        "icon": "launch.png",
    },
}

HOST_TOOL_NAME_TO_IDENTITY: dict[str, Optional[str]] = {
    "launcher": "launcher",
    "loader": "loader",
    "libraryloader": "loader",
    "workfiles": "workfiles",
    "publisher": "publisher",
    "sceneinventory": "scene_inventory",
    "publish": None,
    "experimental_tools": None,
}

__all__ = [
    "HOST_TOOL_NAME_TO_IDENTITY",
    "TOOL_IDENTITIES",
]
