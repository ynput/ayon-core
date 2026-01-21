from __future__ import annotations
import typing

from qtpy import QtWidgets

from ayon_core.tools.utils import HintedLineEdit

if typing.TYPE_CHECKING:
    from ayon_core.tools.loader.abstract import FrontendLoaderController


class ProductGroupDialog(QtWidgets.QDialog):
    def __init__(self, controller: "FrontendLoaderController", parent):
        super(ProductGroupDialog, self).__init__(parent)
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

        self._project_name = None
        self._product_ids = set()

        self._controller: "FrontendLoaderController" = controller
        self._group_btn = group_btn
        self._name_line_edit = name_line_edit

    def set_product_ids(
        self, project_name: str, folder_ids: set[str], product_ids: set[str]
    ):
        self._project_name = project_name
        self._product_ids = product_ids

        # Update the product groups
        product_items = self._controller.get_product_items(
            self._project_name, folder_ids
        )
        product_groups = {
            product_item.group_name
            for product_item in product_items
        }
        product_groups.discard(None)

        # Group names among product ids to pre-set the group name if they
        # all share the same product id
        product_ids_group_names: set[str] = set()
        for product_item in product_items:
            if not product_item.group_name:
                continue

            if product_item.product_id in product_ids:
                product_ids_group_names.add(product_item.group_name)

        text: str = ""
        if len(product_ids_group_names) == 1:
            text: str = next(iter(product_ids_group_names))

        self._name_line_edit.setText(text)
        self._name_line_edit.set_options(list(sorted(product_groups)))

    def _on_apply_click(self):
        group_name = self._name_line_edit.text().strip() or None
        self._controller.change_products_group(
            self._project_name, self._product_ids, group_name
        )
        self.close()
