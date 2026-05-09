"""Shared Loader product grid chrome (single hex source for QSS + QWidget palette)."""
from __future__ import annotations

from qtpy import QtGui, QtWidgets

# Matches `#ProductsGridView` / `#LoaderProductsStack` in style.css.
GRID_VIEW_SURFACE_HEX = "#1c2026"


def grid_view_surface_color() -> QtGui.QColor:
    return QtGui.QColor(GRID_VIEW_SURFACE_HEX)


def apply_grid_view_surface_palette(widget: QtWidgets.QWidget) -> None:
    """Paint the grid body surface (`Window`/`Base`) so nested layouts match scroll chrome."""
    fill = grid_view_surface_color()
    pal = widget.palette()
    pal.setColor(QtGui.QPalette.ColorRole.Window, fill)
    pal.setColor(QtGui.QPalette.ColorRole.Base, fill)
    pal.setColor(QtGui.QPalette.ColorRole.Button, fill)
    widget.setPalette(pal)
    widget.setAutoFillBackground(True)
