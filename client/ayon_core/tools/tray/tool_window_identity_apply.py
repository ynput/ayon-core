"""Apply per-tool window icons / taskbar identity to Launcher and Loader."""

from __future__ import annotations


def apply_launcher_window_identity(launcher_window) -> None:
    try:
        from ayon_core.tools.tool_icon_wrapper import taskbar_identity

        taskbar_identity.set_taskbar_identity(launcher_window, "launcher")
    except ImportError:
        pass


def apply_loader_window_identity(browser_window) -> None:
    try:
        from ayon_core.tools.tool_icon_wrapper import taskbar_identity

        taskbar_identity.set_taskbar_identity(browser_window, "loader")
    except ImportError:
        pass
