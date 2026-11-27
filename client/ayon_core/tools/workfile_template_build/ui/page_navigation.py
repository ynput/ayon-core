"""Publisher-like navigation between the template builder pages."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYButton, AYContainer

from .constants import BUILD_PAGE, CREATE_PAGE, OVERVIEW_PAGE


class PageNavigationWidget(AYContainer):
    """Small tab strip for Create, Overview and Build."""

    page_requested = QtCore.Signal(int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=4,
        )

        buttons = {}
        for page, label in (
            (CREATE_PAGE, "Create"),
            (OVERVIEW_PAGE, "Overview"),
            (BUILD_PAGE, "Build"),
        ):
            button = AYButton(
                label,
                parent=self,
                variant=AYButton.Variants.Surface,
            )
            button.clicked.connect(
                lambda _checked=False, page=page: (
                    self.page_requested.emit(page)
                )
            )
            self.add_widget(button)
            buttons[page] = button

        self.addStretch(1)
        self._buttons = buttons
        self._current_page = BUILD_PAGE
        self.set_current_page(BUILD_PAGE)

    def set_current_page(self, page: int) -> None:
        """Highlight the active page."""
        self._current_page = page
        for button_page, button in self._buttons.items():
            button.set_variant(
                AYButton.Variants.Filled
                if button_page == page
                else AYButton.Variants.Surface
            )

    def set_create_enabled(self, enabled: bool) -> None:
        """Disable Create when the host has no placeholder plugins."""
        self._buttons[CREATE_PAGE].setEnabled(enabled)
