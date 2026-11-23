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


def test_widget_color_change_keeps_base_palette(qapp):
    """Changing colors of a widget does not change palette of other widgets.

    Widgets start with the base palette of the style until they are
    polished, changing their palette must not change the shared one.
    """
    from ayon_core.ui.components import AYLabel
    from ayon_core.ui.style_types import get_ayon_style

    base_palette = get_ayon_style().model.base_palette
    role = QPalette.ColorRole.WindowText
    expected = QColor(base_palette.color(role))

    label = AYLabel("Label")
    try:
        label.set_text_color("#00ff00")
        assert base_palette.color(role) == expected
        # New widgets do not inherit the color either
        other_label = AYLabel("Other label")
        assert other_label._style_palette.color(role) == expected
    finally:
        # Do not affect other tests if the shared palette was changed
        base_palette.setColor(role, expected)
