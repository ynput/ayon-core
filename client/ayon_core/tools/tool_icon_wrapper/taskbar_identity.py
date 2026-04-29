"""Per-tool taskbar / window identity for tray and host UIs.

Stable public API; implementations are split across optional modules so
``patch/tool-identity-icons-windows`` and ``patch/tool-identity-icons-macos``
can merge in either order without duplicating platform logic.

- :mod:`._taskbar_identity_windows` — Qt icons + Win32 ``AppUserModelID`` (Windows patch).
- :mod:`ayon_core.tools.tray.dock_companion` — macOS Dock shim (macOS patch).
"""

from __future__ import annotations


def set_taskbar_identity(widget: object, tool_name: str) -> None:
    try:
        from ayon_core.tools.tool_icon_wrapper import (
            _taskbar_identity_windows as _win,
        )
    except ImportError:
        return
    _win.set_taskbar_identity_impl(widget, tool_name)


def host_tools_after_show(helper: object, tool_name: str, parent: object) -> None:
    try:
        from ayon_core.tools.tool_icon_wrapper import (
            _taskbar_identity_windows as _win,
        )
    except ImportError:
        return
    _win.host_tools_after_show_impl(helper, tool_name, parent)


def open_dock_companion_for_tool(tool_name: str) -> None:
    try:
        from ayon_core.tools.tray import dock_companion as _dock
    except ImportError:
        return
    _dock.open_companion_for_tool(tool_name)


__all__ = [
    "host_tools_after_show",
    "open_dock_companion_for_tool",
    "set_taskbar_identity",
]
