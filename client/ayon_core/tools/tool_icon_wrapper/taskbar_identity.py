"""Per-tool taskbar / window identity for tray and host UIs.

Stable public API; implementations are split across optional modules so
``patch/tool-identity-icons-windows`` and ``patch/tool-identity-icons-macos``
can merge in either order without duplicating platform logic.

- :mod:`._taskbar_identity_windows` — Qt icons + Win32 ``AppUserModelID``
  (Windows patch).
- :mod:`ayon_core.tools.tray.tool_shim` — macOS Dock shim + NSApplication
  icon for dedicated processes.
"""

from __future__ import annotations

import sys


def set_taskbar_identity(widget: object, tool_name: str) -> None:
    if sys.platform == "darwin":
        try:
            from ayon_core.tools.tray import tool_shim as _ts
        except ImportError:
            return
        _ts.darwin_apply_tool_identity(widget, tool_name)
        return

    try:
        from ayon_core.tools.tool_icon_wrapper import (
            _taskbar_identity_windows as _win,
        )
    except ImportError:
        return
    _win.set_taskbar_identity_impl(widget, tool_name)


def host_tools_before_show_delegate(tool_name: str) -> bool:
    """True if the caller should skip normal ``show_tool_by_name`` (Darwin)."""
    if sys.platform != "darwin":
        return False
    try:
        from ayon_core.tools.tray import tool_shim as _ts
    except ImportError:
        return False
    return _ts.darwin_tray_shim_delegation_from_host(tool_name)


def host_tools_after_show(
    helper: object, tool_name: str, parent: object
) -> None:
    if sys.platform == "darwin":
        try:
            from ayon_core.tools.tray import tool_shim as _ts
        except ImportError:
            return
        _ts.host_tools_after_show(helper, tool_name, parent)
        return

    try:
        from ayon_core.tools.tool_icon_wrapper import (
            _taskbar_identity_windows as _win,
        )
    except ImportError:
        return
    _win.host_tools_after_show_impl(helper, tool_name, parent)


__all__ = [
    "host_tools_after_show",
    "host_tools_before_show_delegate",
    "set_taskbar_identity",
]
