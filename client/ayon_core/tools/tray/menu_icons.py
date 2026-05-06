"""Tray menu icons on macOS.

Qt 6.7.3+ defaults to hiding QAction icons in menus on Darwin, and icons on
`QSystemTrayIcon` context menus are often routed through native menus that do
not paint `QAction` icons reliably. Use a `QWidgetAction` row (pixmap + label)
when running on macOS so status dots and similar glyphs remain visible.

Also exposed as :mod:`ayon_core.tools.tray.ui.tray_menu_icons`; the ``ui``
package lazily loads ``tray.py`` so importing that shim does not pull aiohttp.
"""

from __future__ import annotations

import platform
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

_MACOS = platform.system() == "Darwin"
_ICON_PX = 16


def _pixmap_for_menu_icon(icon: QtGui.QIcon) -> QtGui.QPixmap:
    """Logical *_ICON_PX tray pixmap with correct device pixel ratio (Retina)."""

    screen = QtGui.QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio()) if screen else 1.0
    physical = QtCore.QSize(
        int(round(_ICON_PX * dpr)),
        int(round(_ICON_PX * dpr)),
    )
    pm = icon.pixmap(physical)
    if not pm.isNull():
        pm.setDevicePixelRatio(dpr)
    return pm


class _TrayIconRow(QtWidgets.QWidget):
    """Clickable menu row that forwards activation to the hosting QAction."""

    def __init__(
        self,
        widget_action: QtWidgets.QWidgetAction,
        text: str,
    ) -> None:
        super().__init__()
        self._widget_action = widget_action
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(10, 3, 14, 3)
        layout.setSpacing(8)
        self._icon_label = QtWidgets.QLabel()
        self._icon_label.setFixedSize(_ICON_PX + 2, _ICON_PX + 2)
        self._icon_label.setAlignment(QtCore.Qt.AlignCenter)
        self._text_label = QtWidgets.QLabel(text)
        layout.addWidget(self._icon_label)
        layout.addWidget(self._text_label, 1)
        # Without this, clicks hit the child QLabel and never reach this
        # widget — QAction never triggers (macOS tray regression).
        _transparent = QtCore.Qt.WA_TransparentForMouseEvents
        self._icon_label.setAttribute(_transparent, True)
        self._text_label.setAttribute(_transparent, True)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._widget_action.trigger()
        super().mouseReleaseEvent(event)


def create_tray_icon_action(
    parent_menu: QtWidgets.QMenu,
    text: str,
) -> QtWidgets.QAction:
    """Create a menu action that supports visible tray icons on all platforms.

    On macOS this returns a QWidgetAction with an icon label; elsewhere a
    normal QAction. Does not add the action to the menu — caller uses
    ``addAction`` / ``add_service_action`` as before.

    Args:
        parent_menu: Menu that will own the action.
        text: Visible label.

    Returns:
        QAction (possibly a QWidgetAction subclass).
    """

    if not _MACOS:
        return QtWidgets.QAction(text, parent_menu)

    wa = QtWidgets.QWidgetAction(parent_menu)
    wa.setText(text)
    menu_role_enum = getattr(QtWidgets.QAction, "MenuRole", None)
    no_role = getattr(menu_role_enum, "NoRole", None) if menu_role_enum else None
    if no_role is not None:
        wa.setMenuRole(no_role)

    row = _TrayIconRow(wa, text)
    wa.setDefaultWidget(row)
    wa._ayon_mac_menu_icon_label = row._icon_label  # noqa: SLF001
    return wa


def apply_tray_menu_icon(
    action: QtWidgets.QAction,
    icon: Optional[QtGui.QIcon],
) -> None:
    """Set or clear the icon shown for a tray menu row."""

    label = getattr(action, "_ayon_mac_menu_icon_label", None)
    if label is not None:
        if icon is None or icon.isNull():
            label.clear()
            label.hide()
        else:
            label.setPixmap(_pixmap_for_menu_icon(icon))
            label.show()
        return

    action.setIcon(icon)
    if hasattr(action, "setIconVisibleInMenu"):
        action.setIconVisibleInMenu(
            icon is not None and not icon.isNull()
        )
