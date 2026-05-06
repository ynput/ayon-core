"""Stable import path for macOS tray menu icon helpers.

Implementation lives in :mod:`ayon_core.tools.tray.menu_icons`. This module
exists so callers can use ``ayon_core.tools.tray.ui.tray_menu_icons`` without
pulling :mod:`ayon_core.tools.tray.ui.tray` — see lazy :mod:`ui.__init__`.
"""

from ayon_core.tools.tray.menu_icons import (
    apply_tray_menu_icon,
    create_tray_icon_action,
)

__all__ = (
    "apply_tray_menu_icon",
    "create_tray_icon_action",
)
