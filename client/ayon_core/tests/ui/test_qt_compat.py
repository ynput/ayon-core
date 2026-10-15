from unittest.mock import Mock

from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (
    QStyleOption,
    QStyleOptionButton,
    QStyleOptionComplex,
    QStyleOptionSlider,
)

from ayon_core.ui.components.label import _iter_enum_values
from ayon_core.ui.drawers.button import _get_button_option
from ayon_core.ui.drawers.scrollbar import _get_slider_option


def test_iter_enum_values_supports_pyside2_mapping():
    first = object()
    second = object()

    class LegacyEnum:
        values = {"First": first, "Second": second}

    assert list(_iter_enum_values(LegacyEnum)) == [first, second]


def test_get_slider_option_restores_sliced_option():
    widget = Mock()

    def _init_style_option(option):
        option.minimum = 2
        option.maximum = 12
        option.sliderPosition = 5
        option.upsideDown = False

    widget.initStyleOption.side_effect = _init_style_option

    option = _get_slider_option(QStyleOptionComplex(), widget)

    assert isinstance(option, QStyleOptionSlider)
    assert option.minimum == 2
    assert option.maximum == 12
    assert option.sliderPosition == 5
    widget.initStyleOption.assert_called_once_with(option)


def test_get_button_option_restores_sliced_option():
    widget = Mock()

    def _init_style_option(option):
        option.text = "Refresh"
        option.icon = QIcon()

    widget.initStyleOption.side_effect = _init_style_option
    base_option = QStyleOption()
    base_option.rect.setWidth(120)

    option = _get_button_option(base_option, widget)

    assert isinstance(option, QStyleOptionButton)
    assert option.text == "Refresh"
    assert option.rect.width() == 120
    widget.initStyleOption.assert_called_once_with(option)
