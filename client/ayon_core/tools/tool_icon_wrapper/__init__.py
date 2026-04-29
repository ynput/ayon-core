"""Tool window identity (taskbar / Dock) integration entrypoints.

``register_tray_routes`` forwards to an optional Darwin hook when present; on
Windows-focused trees it is typically a no-op.
"""

from __future__ import annotations

from typing import Any, Optional

__all__ = [
    "register_tray_routes",
]


def register_tray_routes(
    web_server_manager: Optional[Any] = None,
    tray_manager: Optional[Any] = None,
) -> None:
    """Register optional tray HTTP routes (Darwin Dock companion when shipped)."""
    if web_server_manager is None or tray_manager is None:
        return
    from ayon_core.tools.tool_icon_wrapper import darwin

    register = getattr(darwin, "register_dock_http_routes", None)
    if callable(register):
        register(web_server_manager, tray_manager)
