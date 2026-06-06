"""Utility for compositing multiple widgets into a single snapshot.

This module provides a reusable `CompositeWidget` class that can composite
multiple widgets (e.g., a base widget and its popup/dropdown) into a single
pixmap. This is useful for visual regression testing where the snapshot
must include both the main widget and any transient overlays.
"""

from __future__ import annotations

from typing import Callable

from ayon_core.ui.components.frame import AYFrame
from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPainter


class CompositeWidget(AYFrame):
    """A QWidget whose grab() composites multiple child widgets.

    This class generalizes the compositing logic used in
    `_CompositeComboWidget` and `_CompositeMenuWidget`. It supports:
    - Compositing any number of child widgets.
    - Dynamic positioning of child widgets relative to the parent.
    - Optional background color for the base layer.
    - Skipping hidden widgets.

    Args:
        widgets: A list of tuples, where each tuple contains:
            - The child widget to composite.
            - A callable that computes the child's top-left position
              relative to this widget. The callable should return a
              `QtCore.QPoint`.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        widgets: list[tuple[QtWidgets.QWidget, Callable[[], QtCore.QPoint]]],
        variant: AYFrame.Variants = AYFrame.Variants.Default,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(variant=variant, parent=parent)
        self._widgets = widgets
        style = self.style().model.get_style("QFrame", variant.value)
        self.bg_color = style.get("background-color", QColor(Qt.GlobalColor.transparent))

    def grab(  # type: ignore[override]
        self,
        rectangle: QtCore.QRect = QtCore.QRect(
            QtCore.QPoint(0, 0), QtCore.QSize(-1, -1)
        ),
    ) -> QtGui.QPixmap:
        """Return a pixmap of this widget composited with all child widgets.

        Args:
            rectangle: Sub-rectangle to grab (forwarded to the base
                implementation for the main widget layer).

        Returns:
            A `QPixmap` containing the composite image.
        """
        base_pixmap = super().grab(rectangle)
        if not self._widgets:
            return base_pixmap

        # Collect visible widgets and their pixmaps/positions
        layers = []
        for widget, pos_func in self._widgets:
            if widget is None or not widget.isVisible():
                continue
            widget_pixmap = widget.grab()
            pos = pos_func()
            layers.append((widget_pixmap, pos))

        if not layers:
            return base_pixmap

        # Compute canvas size
        max_x = base_pixmap.width()
        max_y = base_pixmap.height()
        for pixmap, pos in layers:
            max_x = max(max_x, pos.x() + pixmap.width())
            max_y = max(max_y, pos.y() + pixmap.height())

        canvas = QtGui.QPixmap(max_x, max_y + 10)
        canvas.fill(self.bg_color)

        # Composite all layers
        painter = QPainter(canvas)
        painter.drawPixmap(0, 0, base_pixmap)
        for pixmap, pos in layers:
            painter.drawPixmap(pos.x(), pos.y(), pixmap)
        painter.end()

        return canvas
