import typing

from qtpy import QtWidgets

from ayon_core.tools.utils import PlaceholderLineEdit

if typing.TYPE_CHECKING:
    from ayon_core.tools.loader.control import LoaderController


class ProductGroupDialog(QtWidgets.QDialog):
    def __init__(self, controller: "LoaderController", parent):
        super(ProductGroupDialog, self).__init__(parent)
        self.setWindowTitle("Grouping products")
        self.setMinimumWidth(250)
        self.setModal(True)

        main_label = QtWidgets.QLabel("Group Name", self)

        group_name_input = PlaceholderLineEdit(self)
        group_name_input.setPlaceholderText("Remain blank to ungroup..")

        group_picker_btn = QtWidgets.QPushButton()
        group_picker_btn.setFixedWidth(18)
        group_picker_menu = QtWidgets.QMenu(group_picker_btn)
        group_picker_btn.setMenu(group_picker_menu)

        group_btn = QtWidgets.QPushButton("Apply", self)
        group_btn.setAutoDefault(True)
        group_btn.setDefault(True)

        name_widget = QtWidgets.QWidget()
        name_layout = QtWidgets.QHBoxLayout(name_widget)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.addWidget(group_name_input, 1)
        name_layout.addWidget(group_picker_btn, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(main_label, 0)
        layout.addWidget(name_widget, 0)
        layout.addWidget(group_btn, 0)

        group_btn.clicked.connect(self._on_apply_click)
        group_picker_menu.triggered.connect(self._on_picker_clicked)

        self._project_name = None
        self._product_ids = set()

        self._controller: "LoaderController" = controller
        self._group_btn = group_btn
        self._group_name_input = group_name_input
        self._group_picker_btn = group_picker_btn
        self._group_picker_menu = group_picker_menu

    def set_product_ids(self, project_name, product_ids):
        self._project_name = project_name
        self._product_ids = product_ids

        # Update the product groups
        folder_ids = self._controller.get_selected_folder_ids()
        product_items = self._controller.get_product_items(
            project_name=self._controller.get_selected_project_name(),
            folder_ids=folder_ids)
        product_groups = {
            product_item.group_name for product_item in product_items
        }
        product_groups.discard(None)

        self._set_product_groups(product_groups)

    def _set_product_groups(self, product_groups):
        """Update product groups for the preset list available in the dialog"""
        # Update product group picker menu and state
        self._group_picker_menu.clear()
        for product_group in product_groups:
            self._group_picker_menu.addAction(product_group)
        self._group_picker_btn.setEnabled(bool(product_groups))

    def _on_picker_clicked(self, action):
        """Callback when action is clicked in group picker menu"""
        self._group_name_input.setText(action.text())

    def _on_apply_click(self):
        group_name = self._group_name_input.text().strip() or None
        self._controller.change_products_group(
            self._project_name, self._product_ids, group_name
        )
        self.close()
