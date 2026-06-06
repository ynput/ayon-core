"""Visual regression tests for AYComboBox."""

from __future__ import annotations

from ayon_core.ui.components.combo_box import ALL_STATUSES, AYComboBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.data_models import MenuSize
from qtpy import QtCore, QtWidgets
from qtpy.QtWidgets import QApplication, QWidget
from widget_test import WidgetTest

from utils.composite_widget import CompositeWidget


class _CompositeComboWidget(CompositeWidget):
    """A QWidget whose grab() composites the main container and open popup.

    This is a thin wrapper around `CompositeWidget` for backward compatibility.

    Args:
        combos: The ``AYComboBox`` instances whose popups will be composited.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        combos: list[AYComboBox],
        parent: QWidget | None = None,
    ) -> None:
        def popup_pos(combo: AYComboBox) -> QtCore.QPoint:
            popup = combo.view().window()
            if popup is combo or not popup.isVisible():
                return QtCore.QPoint(0, 0)
            popup_global = popup.mapToGlobal(QtCore.QPoint(0, 0))
            return self.mapFromGlobal(popup_global)

        super().__init__(
            widgets=[
                (cb.view().window(), lambda cb=cb: popup_pos(cb))
                for cb in combos
            ],
            parent=parent,
        )


class ComboBoxTest(WidgetTest):
    """Tests AYComboBox across display modes (Full/Short/Icon) and variants."""

    size = (700, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        inner = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        # Row 1: Default variant - Full mode
        row1 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        self._default_full = AYComboBox(
            items=ALL_STATUSES,
            size=MenuSize.Full,
            variant=AYComboBox.Variants.Default,
            placeholder="Select status…",
        )
        self._default_full.setCurrentIndex(2)  # In progress
        row1.add_widget(self._default_full)

        # Row 1: Low variant
        self._low_full = AYComboBox(
            items=ALL_STATUSES,
            size=MenuSize.Full,
            variant=AYComboBox.Variants.Low,
        )
        self._low_full.setCurrentIndex(3)  # Pending review
        row1.add_widget(self._low_full)
        row1.addStretch(1)
        inner.add_widget(row1)

        # Row 2: Short + Icon modes
        row2 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        self._short_combo = AYComboBox(
            items=ALL_STATUSES,
            size=MenuSize.Short,
        )
        self._short_combo.setCurrentIndex(4)  # Approved
        row2.add_widget(self._short_combo)

        self._icon_combo = AYComboBox(
            items=ALL_STATUSES,
            size=MenuSize.Icon,
        )
        self._icon_combo.setCurrentIndex(5)  # On hold
        row2.add_widget(self._icon_combo)
        row2.addStretch(1)
        inner.add_widget(row2)

        root = _CompositeComboWidget(
            [
                self._default_full,
                self._low_full,
                self._short_combo,
                self._icon_combo,
            ],
            parent=None,
        )
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(inner)

        self.widget = root
        return self.widget

    def wait_loaded(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Process pending events so the popup is fully laid out."""
        QApplication.processEvents()

    def set_inverted(self) -> None:
        self._default_full.set_inverted(True)
        self._low_full.set_inverted(True)
        self._short_combo.set_inverted(True)
        self._icon_combo.set_inverted(True)

    def set_not_inverted(self) -> None:
        self._default_full.set_inverted(False)
        self._low_full.set_inverted(False)
        self._short_combo.set_inverted(False)
        self._icon_combo.set_inverted(False)

    def open_menu_default(self) -> None:
        self._default_full.showPopup()
        QApplication.processEvents()


    def open_menu_default_hover(self) -> None:
        self._default_full.showPopup()
        QApplication.processEvents()
        view = self._default_full.view()

        # 0-based index, so 4 = 5th item
        model_index = view.model().index(4, 0)
        rect = view.visualRect(model_index)

        self._qbot.mouseMove(view.viewport(), rect.center())
        QApplication.processEvents()

    def open_menu_low(self) -> None:
        self._low_full.showPopup()
        QApplication.processEvents()

    def open_menu_short(self) -> None:
        self._short_combo.showPopup()
        QApplication.processEvents()

    def open_menu_icon(self) -> None:
        self._icon_combo.showPopup()
        QApplication.processEvents()

    def steps(self):
        return [
            self.set_inverted,
            self.set_not_inverted,
            self.open_menu_default,
            self.open_menu_default_hover,
            self.open_menu_low,
            self.open_menu_short,
            self.open_menu_icon,
        ]

    def cleanup(self, step_name: str) -> None:
        # Ensure all popups are closed before the next step
        for combo in [
            self._default_full,
            self._low_full,
            self._short_combo,
            self._icon_combo,
        ]:
            if combo.view().window().isVisible():
                combo.hidePopup()
                QApplication.processEvents()

        self._qbot.mouseMove(self.widget, QtCore.QPoint(0, 0))
        QApplication.processEvents()
