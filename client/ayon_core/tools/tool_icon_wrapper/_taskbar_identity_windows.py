"""Qt window icons and Win32 AppUserModelID for tray-hosted tools."""

from __future__ import annotations

import sys
from pathlib import Path

from ayon_core.lib import Logger
from ayon_core.tools.tool_icon_wrapper.registry import (
    HOST_TOOL_NAME_TO_IDENTITY,
    TOOL_IDENTITIES,
)

_LOG = Logger.get_logger("TaskbarIdentityWindows")

_NATIVE_TASKBAR_EXC = (
    RuntimeError,
    AttributeError,
    OSError,
    SystemError,
    TypeError,
    ValueError,
)


def _apply_win32_app_user_model_id(
    widget: object, app_id: str, tool_name: str
) -> None:
    if sys.platform != "win32":
        return
    try:
        from ayon_core.tools.tool_icon_wrapper.taskbar_windows import (
            win_set_app_user_model_id,
        )

        window_id = int(widget.winId())  # type: ignore[union-attr]
        if window_id:
            win_set_app_user_model_id(window_id, app_id)
    except _NATIVE_TASKBAR_EXC as exc:
        _LOG.debug("native taskbar (win) %s: %s", tool_name, exc)


def set_taskbar_identity_impl(widget: object, tool_name: str) -> None:
    """Set taskbar icon (Qt) and, on Windows, per-tool AppUserModelID."""
    if sys.platform == "darwin":
        return

    meta = TOOL_IDENTITIES.get(tool_name)
    if meta is None:
        return

    from ayon_core import AYON_CORE_ROOT
    from qtpy import QtGui, QtWidgets

    if not isinstance(widget, QtWidgets.QWidget):
        return

    icon_path = Path(AYON_CORE_ROOT) / "resources" / "icons" / meta["icon"]
    if icon_path.is_file():
        widget.setWindowIcon(QtGui.QIcon(str(icon_path)))

    if sys.platform != "win32":
        return

    app_id = meta.get("app_id")
    if not app_id:
        return

    from qtpy import QtCore

    already_visible = widget.isVisible()

    def _run_native() -> None:
        try:
            _apply_win32_app_user_model_id(widget, app_id, tool_name)
        except _NATIVE_TASKBAR_EXC as exc:
            _LOG.debug("set_taskbar_identity native %s: %s", tool_name, exc)

    if already_visible:
        QtCore.QTimer.singleShot(0, _run_native)
        QtCore.QTimer.singleShot(50, _run_native)
        QtCore.QTimer.singleShot(150, _run_native)
    else:
        _run_native()
        QtCore.QTimer.singleShot(0, _run_native)
        QtCore.QTimer.singleShot(150, _run_native)


def _resolve_publish_front_window():
    """Best-effort QWidget for Pyblish / Tray Publisher after ``show()``."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    active = app.activeWindow()
    if isinstance(active, QtWidgets.QWidget) and active.isVisible():
        return active

    title_hints = ("tray", "publish", "pyblish")
    for tl in app.topLevelWidgets():
        if not isinstance(tl, QtWidgets.QWidget):
            continue
        if not tl.isVisible() or not tl.isWindow():
            continue
        title = (tl.windowTitle() or "").lower()
        if any(h in title for h in title_hints):
            return tl
    return None


def _defer_publish_taskbar_identity(identity_key: str) -> None:
    """Tray Publisher via Pyblish may have no ``get_tool_by_name`` widget yet."""
    if sys.platform != "win32":
        return

    from qtpy import QtCore

    def _apply() -> None:
        widget = _resolve_publish_front_window()
        if widget is None:
            _LOG.debug(
                "Tray Publisher taskbar identity: no window matched yet.",
            )
            return
        set_taskbar_identity_impl(widget, identity_key)

    QtCore.QTimer.singleShot(0, _apply)
    QtCore.QTimer.singleShot(50, _apply)
    QtCore.QTimer.singleShot(150, _apply)


def host_tools_after_show_impl(
    helper: object, tool_name: str, parent: object
) -> None:
    identity_key = HOST_TOOL_NAME_TO_IDENTITY.get(tool_name)
    if not identity_key:
        return
    widget = helper.get_tool_by_name(tool_name, parent)  # type: ignore[union-attr]
    if widget is not None:
        set_taskbar_identity_impl(widget, identity_key)
        return

    if tool_name == "publish":
        _defer_publish_taskbar_identity(identity_key)
