"""Persist/restore tool window geometry and splitter state (QSettings)."""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

_SETTINGS_ORG = "AYON"
_SETTINGS_APP = "ayon_core"


def save_tool_window_state(
    tool_key: str,
    window: QtWidgets.QWidget,
    splitters: list[tuple[str, QtWidgets.QSplitter]] | None = None,
) -> None:
    """Save window geometry and optional splitter states to QSettings."""
    settings = QtCore.QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.beginGroup(tool_key)
    try:
        settings.setValue("geometry", window.saveGeometry())
        if splitters:
            for key, splitter in splitters:
                settings.setValue(key, splitter.saveState())
    finally:
        settings.endGroup()
    settings.sync()


def restore_tool_window_state(
    tool_key: str,
    window: QtWidgets.QWidget,
    splitters: list[tuple[str, QtWidgets.QSplitter]] | None = None,
) -> bool:
    """Restore window geometry and optional splitter states from QSettings.

    Returns True if geometry was restored, False otherwise (e.g. first run).
    """
    settings = QtCore.QSettings(_SETTINGS_ORG, _SETTINGS_APP)
    settings.beginGroup(tool_key)
    geometry_restored = False
    try:
        geo = settings.value("geometry")
        if (
            geo is not None
            and isinstance(geo, QtCore.QByteArray)
            and not geo.isEmpty()
        ):
            geometry_restored = window.restoreGeometry(geo)
        if splitters:
            for key, splitter in splitters:
                state = settings.value(key)
                if (
                    state is not None
                    and isinstance(state, QtCore.QByteArray)
                    and not state.isEmpty()
                ):
                    splitter.restoreState(state)
    finally:
        settings.endGroup()
    return geometry_restored
