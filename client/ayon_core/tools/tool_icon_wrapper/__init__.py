"""Tool window identity (taskbar / Dock) integration entrypoints.

``register_tray_routes`` wires Darwin Dock HTTP handlers when
``tool_shim`` is available.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

__all__ = [
    "register_tray_routes",
]


def register_tray_routes(
    web_server_manager: Optional[Any] = None,
    tray_manager: Optional[Any] = None,
) -> None:
    """Register optional tray HTTP routes (Darwin Dock shim)."""
    if web_server_manager is None or tray_manager is None:
        return
    if sys.platform != "darwin":
        return
    try:
        from ayon_core.tools.tray import tool_shim
    except ImportError:
        return
    tool_shim.register_routes(web_server_manager, tray_manager)
