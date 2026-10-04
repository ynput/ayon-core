"""Dialog to set the product group of selected products."""

from __future__ import annotations

import typing

from qtpy import QtCore, QtWidgets

from ayon_core.tools.utils import HintedLineEdit

if typing.TYPE_CHECKING:
    from ayon_core.tools.browser.ui.browser_controller import (
        BrowserWidgetController,
    )


class ProductGroupDialog(QtWidgets.QDialog):
    """Dialog asking for a group name to set on products.

    Signals:
        group_change_failed (str): Emitted with a message when the change
            could not be saved.
    """

    group_change_failed = QtCore.Signal(str)

    def __init__(
        self,
        controller: BrowserWidgetController,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Grouping products")
        self.setMinimumWidth(250)
        self.setModal(True)

        main_label = QtWidgets.QLabel("Group Name", self)

        name_line_edit = HintedLineEdit(parent=self)
        name_line_edit.setPlaceholderText("Remain blank to ungroup..")
        name_line_edit.set_button_tool_tip(
            "Pick from an existing product group (if any)")

        group_btn = QtWidgets.QPushButton("Apply", self)
        group_btn.setAutoDefault(True)
        group_btn.setDefault(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(main_label, 0)
        layout.addWidget(name_line_edit, 0)
        layout.addWidget(group_btn, 0)

        group_btn.clicked.connect(self._on_apply_click)
        name_line_edit.returnPressed.connect(self._on_apply_click)

        self._project_name: str = ""
        self._product_ids: set[str] = set()

        self._controller = controller
        self._group_btn = group_btn
        self._name_line_edit = name_line_edit

    def set_product_ids(
        self, project_name: str, product_ids: set[str]
    ) -> None:
        """Set the products to change the group for.

        Pre-fills the current group name when all grouped products share
        one, and offers group names used in the folders of the products.

        Args:
            project_name: AYON project name.
            product_ids: Product ids to change the group for.
        """
        self._project_name = project_name
        self._product_ids = product_ids

        groups_info = self._controller.get_product_groups_info(
            project_name, product_ids
        )
        text = ""
        if len(groups_info.selected) == 1:
            text = next(iter(groups_info.selected))

        self._name_line_edit.setText(text)
        self._name_line_edit.set_options(sorted(groups_info.available))

    def _on_apply_click(self) -> None:
        group_name = self._name_line_edit.text().strip()
        try:
            self._controller.change_products_group(
                self._project_name,
                self._product_ids,
                group_name,
            )
        except Exception as exc:
            self.group_change_failed.emit(
                f"Failed to change product group: {exc}"
            )
        self.close()
