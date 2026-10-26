"""Tests for the base palette built by StyleData."""
from __future__ import annotations

from qtpy.QtGui import QColor, QPalette

from ayon_core.ui.style_types import StyleData


def test_base_palette_sets_tooltip_colors(qapp):
    """Tooltip roles come from the style, not the platform defaults."""
    data = StyleData()
    palette = data.base_palette
    text = palette.color(QPalette.ColorRole.ToolTipText)
    base = palette.color(QPalette.ColorRole.ToolTipBase)

    assert text == QColor(data._palette["qt-active-tooltip-text"])
    assert base == QColor(data._palette["qt-active-tooltip-base"])
