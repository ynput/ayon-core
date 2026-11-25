"""Fixes of how placeholder option widgets look in the tool."""

from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.tools.attribute_defs import AttributeDefinitionsWidget
from ayon_core.tools.attribute_defs.widgets import LabelAttrWidget

from .preview_widget import _HintingFilter
from .utils import INPUT_COLOR, PANEL_COLOR, get_palette_color


def _polish_options(attrs_widget: AttributeDefinitionsWidget) -> None:
    """Fix how option widgets look in the tool.

    - The AYON font disables hinting. Qt on Windows then renders bold rich
        text, like the bold section labels of the options, with the regular
        weight. Labels of the options use the default hinting instead.
    - Multiline text inputs paint their text on a viewport which the
        stylesheet of the window does not reach, so they would show no
        background at all. The viewport gets the color of the other inputs.

    Args:
        attrs_widget (AttributeDefinitionsWidget): Widget with the options.

    """
    for label_widget in attrs_widget.findChildren(LabelAttrWidget):
        for label in label_widget.findChildren(QtWidgets.QLabel):
            _HintingFilter.install(label)

    viewport_stylesheet = (
        "QWidget {{ background: {}; }}"
        " QWidget:disabled {{ background: {}; }}"
    ).format(
        get_palette_color(INPUT_COLOR), get_palette_color(PANEL_COLOR)
    )
    multiline_inputs = (
        attrs_widget.findChildren(QtWidgets.QPlainTextEdit)
        + attrs_widget.findChildren(QtWidgets.QTextEdit)
    )
    for input_widget in multiline_inputs:
        input_widget.viewport().setStyleSheet(viewport_stylesheet)
