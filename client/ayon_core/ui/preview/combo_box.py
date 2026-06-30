"""Combo-box components for the AYON UI Qt library.

This module provides :class:`AYComboBox`, a styled :class:`QComboBox`
subclass that supports per-item coloured icons, a short-text display mode,
and an icon-only display mode via :class:`~ayon_core.ui.data_models.MenuSize`.
A dropdown arrow is drawn using the Material Symbol ``arrow_drop_down``
icon so the widget is visually recognizable as a dropdown when show_chevron
is true.

It also exposes :class:`AYComboBoxModel`, the default
:class:`QStandardItemModel` subclass that adds two extra item-data roles:

- ``ShortTextRole`` - an abbreviated label shown when the combo-box is in
  :attr:`~ayon_core.ui.data_models.MenuSize.Short` mode.
- ``IconNameRole`` - the Material Symbol icon name used to regenerate icons
  when the *inverted* colour mode is toggled.

A drop-in sample dataset :data:`ALL_STATUSES` is included for quick
prototyping and automated tests.

Typical usage::

    from ayon_core.ui.components.combo_box import AYComboBox, ALL_STATUSES

    combo = AYComboBox(parent=my_widget, items=ALL_STATUSES)
    combo.set_size("short")   # or MenuSize.Short
    combo.set_inverted(True)

Custom model usage (must expose ``ShortTextRole`` and ``IconNameRole``)::

    model = MyCustomModel(parent=combo)
    combo.setModel(model)

Note:
    When a custom model that does **not** expose ``ShortTextRole`` / \
``IconNameRole`` is set via :meth:`AYComboBox.setModel`, the widget
    falls back to displaying ``"< INCOMPATIBLE MODEL >"`` in short mode and
    raises :exc:`RuntimeError` when :meth:`AYComboBox.add_item` or
    :meth:`AYComboBox.update_items` is called.
"""

from __future__ import annotations

import os

from qtmaterialsymbols import get_icon
from qtpy import QtCore, QtWidgets
from qtpy.QtGui import (
    QBrush,
    QColor,
    QPalette,
    QStandardItem,
    QStandardItemModel,
)

from ayon_core.ui.data_models import MenuSize

from ayon_core.ui.components.combo_box import AYComboBox
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel

from ayon_core.ui.preview.constants import EXAMPLE_STATUSES
from ayon_core.ui.preview.utils import Style, preview_widget


class CustomModel(QStandardItemModel):
    ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
    IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2

    def __init__(self, parent=None):
        super().__init__(parent)

    def add_item(
        self,
        text: str,
        color: QColor,
        icon_name: str | None = None,
        short: str = "",
    ):
        bg_color = (
            self.parent()
            .palette()
            .color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
        )
        item = QStandardItem(text)
        item.setForeground(QBrush(color))
        item.setBackground(QBrush(bg_color))
        if icon_name:
            item.setIcon(
                get_icon(
                    icon_name,
                    color_normal=bg_color,
                    color_selected=color,
                    # TODO: add fill support to get_icon and
                    #       pass self._icon_fill here
                )
            )
            item.setData(icon_name, self.IconNameRole)
        if short:
            item.setData(short, self.ShortTextRole)
        self.appendRow(item)


def build_combo_box_preview_widget():
    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_spacing=6,
        layout_margin=20,
    )
    w.setMinimumWidth(250)

    w.add_widget(AYLabel("AYComboBox Tests", rel_text_size=6, bold=True))
    w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))

    w.add_widget(AYLabel("Default Model", dim=True, bold=True))
    cb = AYComboBox(items=EXAMPLE_STATUSES)
    w.add_widget(
        cb, stretch=0, alignment=QtCore.Qt.AlignmentFlag.AlignLeft
    )
    inv = AYCheckBox("inverted", parent=w)
    w.add_widget(inv)
    size = AYComboBox(w)
    size.addItems([s.name for s in MenuSize])
    w.add_widget(size)

    w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))

    # custom model test
    w.add_widget(AYLabel("Custom Model: invert ON", dim=True, bold=True))
    custom = AYComboBox(w, inverted=True)
    model = CustomModel(parent=custom)
    model.add_item(
        "Custom Model Item 1",
        QColor("#ee6666"),
        icon_name="map",
        short="CUST 1",
    )
    model.add_item(
        "Custom Model Item 2",
        QColor("#66ee66"),
        icon_name="map",
        short="CUST 2",
    )
    model.add_item(
        "Custom Model Item 3",
        QColor("#6666ee"),
        icon_name="map",
        # short="CUST 3",   # check for empty case !
    )
    custom.setModel(model)
    w.add_widget(custom)
    cust_inv = AYCheckBox("inverted", parent=w)
    cust_inv.setChecked(True)
    w.add_widget(cust_inv)
    cust_size = AYComboBox(w)
    cust_size.addItems([s.name for s in MenuSize])
    w.add_widget(cust_size)

    w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))
    w.add_widget(AYLabel("Backward compatibility"))
    back = AYComboBox(w, items=EXAMPLE_STATUSES, inverted=True)
    w.add_widget(back)

    # configure
    inv.clicked.connect(lambda x: cb.set_inverted(x))
    size.currentTextChanged.connect(lambda x: cb.set_size(x))
    cust_inv.clicked.connect(lambda x: custom.set_inverted(x))
    cust_size.currentTextChanged.connect(lambda x: custom.set_size(x))

    return w


if __name__ == "__main__":
    os.environ["QT_SCALE_FACTOR"] = "1"
    preview_widget(
        build_combo_box_preview_widget,
        style=Style.AYONStyleOverCSS
    )
