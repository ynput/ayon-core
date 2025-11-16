import typing

from qtpy import QtWidgets

from ayon_core.tools.utils import HintedLineEdit

if typing.TYPE_CHECKING:
    from ayon_core.tools.loader.control import LoaderController


class ProductGroupDialog(QtWidgets.QDialog):
    def __init__(self, controller: "LoaderController", parent):
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

        self._controller: "LoaderController" = controller
        self._group_btn = group_btn
        self._name_line_edit = name_line_edit

    def set_product_ids(self, project_name, folder_ids, product_ids):
        self._project_name = project_name
        self._product_ids = product_ids

        # Update the product groups
        product_groups = self._controller.get_folder_product_group_names(
            project_name=project_name,
            folder_ids=folder_ids
        )
        self._name_line_edit.set_options(list(sorted(product_groups)))

    def _on_apply_click(self):
        group_name = self._name_line_edit.text().strip() or None
        self._controller.change_products_group(
            self._project_name, self._product_ids, group_name
        )
        self.close()
