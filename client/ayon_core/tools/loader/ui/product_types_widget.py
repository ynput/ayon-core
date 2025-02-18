from qtpy import QtWidgets, QtGui, QtCore

from ._multicombobox import (
    CustomPaintMultiselectComboBox,
    BaseQtModel,
)

STATUS_ITEM_TYPE = 0
SELECT_ALL_TYPE = 1
DESELECT_ALL_TYPE = 2
SWAP_STATE_TYPE = 3

PRODUCT_TYPE_ROLE = QtCore.Qt.UserRole + 1
ITEM_TYPE_ROLE = QtCore.Qt.UserRole + 2
ITEM_SUBTYPE_ROLE = QtCore.Qt.UserRole + 3


class ProductTypesQtModel(BaseQtModel):
    def __init__(self, controller):
        self._reset_filters_on_refresh = True
        self._refreshing = False
        self._bulk_change = False
        self._items_by_name = {}

        super().__init__(
            item_type_role=ITEM_TYPE_ROLE,
            item_subtype_role=ITEM_SUBTYPE_ROLE,
            empty_values_label="No product types...",
            controller=controller,
        )

    def is_refreshing(self):
        return self._refreshing

    def refresh(self, project_name):
        self._refreshing = True
        super().refresh(project_name)

        self._reset_filters_on_refresh = False
        self._refreshing = False

    def reset_product_types_filter_on_refresh(self):
        self._reset_filters_on_refresh = True

    def _get_standard_items(self) -> list[QtGui.QStandardItem]:
        return list(self._items_by_name.values())

    def _clear_standard_items(self):
        self._items_by_name.clear()

    def _prepare_new_value_items(self, project_name: str, _: bool) -> tuple[
        list[QtGui.QStandardItem], list[QtGui.QStandardItem]
    ]:
        product_type_items = self._controller.get_product_type_items(
            project_name)
        self._last_project = project_name

        names_to_remove = set(self._items_by_name.keys())
        items = []
        items_filter_required = {}
        for product_type_item in product_type_items:
            name = product_type_item.name
            names_to_remove.discard(name)
            item = self._items_by_name.get(name)
            # Apply filter to new items or if filters reset is requested
            filter_required = self._reset_filters_on_refresh
            if item is None:
                filter_required = True
                item = QtGui.QStandardItem(name)
                item.setData(name, PRODUCT_TYPE_ROLE)
                item.setEditable(False)
                item.setCheckable(True)
                self._items_by_name[name] = item

            items.append(item)

            if filter_required:
                items_filter_required[name] = item

        if items_filter_required:
            product_types_filter = self._controller.get_product_types_filter()
            for product_type, item in items_filter_required.items():
                matching = (
                    int(product_type in product_types_filter.product_types)
                    + int(product_types_filter.is_allow_list)
                )
                item.setCheckState(
                    QtCore.Qt.Checked
                    if matching % 2 == 0
                    else QtCore.Qt.Unchecked
                )

        items_to_remove = []
        for name in names_to_remove:
            items_to_remove.append(
                self._items_by_name.pop(name)
            )

        # Uncheck all if all are checked (same result)
        if all(
            item.checkState() == QtCore.Qt.Checked
            for item in items
        ):
            for item in items:
                item.setCheckState(QtCore.Qt.Unchecked)

        return items, items_to_remove


class ProductTypesCombobox(CustomPaintMultiselectComboBox):
    def __init__(self, controller, parent):
        self._controller = controller
        model = ProductTypesQtModel(controller)
        super().__init__(
            PRODUCT_TYPE_ROLE,
            PRODUCT_TYPE_ROLE,
            QtCore.Qt.ForegroundRole,
            QtCore.Qt.DecorationRole,
            item_type_role=ITEM_TYPE_ROLE,
            model=model,
            parent=parent
        )
        self.set_placeholder_text("Product types filter...")
        self._model = model
        self._last_project_name = None
        self._fully_disabled_filter = False

        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_change
        )
        controller.register_event_callback(
            "projects.refresh.finished",
            self._on_projects_refresh
        )
        self.setToolTip("Product types filter")
        self.value_changed.connect(
            self._on_product_type_filter_change
        )

    def reset_product_types_filter_on_refresh(self):
        self._model.reset_product_types_filter_on_refresh()

    def _on_product_type_filter_change(self):
        lines = ["Product types filter"]
        for item in self.get_value_info():
            status_name, enabled = item
            lines.append(f"{'✔' if enabled else '☐'} {status_name}")

        self.setToolTip("\n".join(lines))

    def _on_project_change(self, event):
        project_name = event["project_name"]
        self._last_project_name = project_name
        self._model.refresh(project_name)

    def _on_projects_refresh(self):
        if self._last_project_name:
            self._model.refresh(self._last_project_name)
            self._on_product_type_filter_change()
