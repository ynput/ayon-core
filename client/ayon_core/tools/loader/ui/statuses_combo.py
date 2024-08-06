from typing import List, Dict

from qtpy import QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.common_models import StatusItem

from ._multicombobox import (
    CustomPaintMultiselectComboBox,
    STANDARD_ITEM_TYPE,
)

STATUS_ITEM_TYPE = 0
SELECT_ALL_TYPE = 1
DESELECT_ALL_TYPE = 2
SWAP_STATE_TYPE = 3

STATUSES_FILTER_SENDER = "loader.statuses_filter"
STATUS_NAME_ROLE = QtCore.Qt.UserRole + 1
STATUS_SHORT_ROLE = QtCore.Qt.UserRole + 2
STATUS_COLOR_ROLE = QtCore.Qt.UserRole + 3
STATUS_ICON_ROLE = QtCore.Qt.UserRole + 4
ITEM_TYPE_ROLE = QtCore.Qt.UserRole + 5
ITEM_SUBTYPE_ROLE = QtCore.Qt.UserRole + 6


class StatusesQtModel(QtGui.QStandardItemModel):
    def __init__(self, controller):
        self._controller = controller
        self._items_by_name: Dict[str, QtGui.QStandardItem] = {}
        self._icons_by_name_n_color: Dict[str, QtGui.QIcon] = {}
        self._last_project = None

        self._select_project_item = None
        self._empty_statuses_item = None

        self._select_all_item = None
        self._deselect_all_item = None
        self._swap_states_item = None

        super().__init__()

        self.refresh(None)

    def get_placeholder_text(self):
        return self._placeholder

    def refresh(self, project_name):
        # New project was selected
        #   status filter is reset to show all statuses
        uncheck_all = False
        if project_name != self._last_project:
            self._last_project = project_name
            uncheck_all = True

        if project_name is None:
            self._add_select_project_item()
            return

        status_items: List[StatusItem] = (
            self._controller.get_project_status_items(
                project_name, sender=STATUSES_FILTER_SENDER
            )
        )
        if not status_items:
            self._add_empty_statuses_item()
            return

        self._remove_empty_items()

        items_to_remove = set(self._items_by_name)
        root_item = self.invisibleRootItem()
        for row_idx, status_item in enumerate(status_items):
            name = status_item.name
            if name in self._items_by_name:
                is_new = False
                item = self._items_by_name[name]
                if uncheck_all:
                    item.setCheckState(QtCore.Qt.Unchecked)
                items_to_remove.discard(name)
            else:
                is_new = True
                item = QtGui.QStandardItem()
                item.setData(ITEM_SUBTYPE_ROLE, STATUS_ITEM_TYPE)
                item.setCheckState(QtCore.Qt.Unchecked)
                item.setFlags(
                    QtCore.Qt.ItemIsEnabled
                    | QtCore.Qt.ItemIsSelectable
                    | QtCore.Qt.ItemIsUserCheckable
                )
                self._items_by_name[name] = item

            icon = self._get_icon(status_item)
            for role, value in (
                (STATUS_NAME_ROLE, status_item.name),
                (STATUS_SHORT_ROLE, status_item.short),
                (STATUS_COLOR_ROLE, status_item.color),
                (STATUS_ICON_ROLE, icon),
            ):
                if item.data(role) != value:
                    item.setData(value, role)

            if is_new:
                root_item.insertRow(row_idx, item)

        for name in items_to_remove:
            item = self._items_by_name.pop(name)
            root_item.removeRow(item.row())

        self._add_selection_items()

    def setData(self, index, value, role):
        if role == QtCore.Qt.CheckStateRole and index.isValid():
            item_type = index.data(ITEM_SUBTYPE_ROLE)
            if item_type == SELECT_ALL_TYPE:
                for item in self._items_by_name.values():
                    item.setCheckState(QtCore.Qt.Checked)
                return True
            if item_type == DESELECT_ALL_TYPE:
                for item in self._items_by_name.values():
                    item.setCheckState(QtCore.Qt.Unchecked)
                return True
            if item_type == SWAP_STATE_TYPE:
                for item in self._items_by_name.values():
                    current_state = item.checkState()
                    item.setCheckState(
                        QtCore.Qt.Checked
                        if current_state == QtCore.Qt.Unchecked
                        else QtCore.Qt.Unchecked
                    )
                return True
        return super().setData(index, value, role)

    def _get_icon(self, status_item: StatusItem) -> QtGui.QIcon:
        name = status_item.name
        color = status_item.color
        unique_id = "|".join([name or "", color or ""])
        icon = self._icons_by_name_n_color.get(unique_id)
        if icon is not None:
            return icon

        icon: QtGui.QIcon = get_qt_icon({
            "type": "material-symbols",
            "name": status_item.icon,
            "color": status_item.color
        })
        self._icons_by_name_n_color[unique_id] = icon
        return icon

    def _init_default_items(self):
        if self._empty_statuses_item is not None:
            return

        empty_statuses_item = QtGui.QStandardItem("No statuses...")
        select_project_item = QtGui.QStandardItem("Select project...")

        select_all_item = QtGui.QStandardItem("Select all")
        deselect_all_item = QtGui.QStandardItem("Deselect all")
        swap_states_item = QtGui.QStandardItem("Swap")

        for item in (
            empty_statuses_item,
            select_project_item,
            select_all_item,
            deselect_all_item,
            swap_states_item,
        ):
            item.setData(STANDARD_ITEM_TYPE, ITEM_TYPE_ROLE)

        select_all_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "done_all",
            "color": "white"
        }))
        deselect_all_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "remove_done",
            "color": "white"
        }))
        swap_states_item.setIcon(get_qt_icon({
            "type": "material-symbols",
            "name": "swap_horiz",
            "color": "white"
        }))

        for item in (
            empty_statuses_item,
            select_project_item,
        ):
            item.setFlags(QtCore.Qt.NoItemFlags)

        for item, item_type in (
            (select_all_item, SELECT_ALL_TYPE),
            (deselect_all_item, DESELECT_ALL_TYPE),
            (swap_states_item, SWAP_STATE_TYPE),
        ):
            item.setData(item_type, ITEM_SUBTYPE_ROLE)

        for item in (
            select_all_item,
            deselect_all_item,
            swap_states_item,
        ):
            item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsUserCheckable
            )

        self._empty_statuses_item = empty_statuses_item
        self._select_project_item = select_project_item

        self._select_all_item = select_all_item
        self._deselect_all_item = deselect_all_item
        self._swap_states_item = swap_states_item

    def _get_empty_statuses_item(self):
        self._init_default_items()
        return self._empty_statuses_item

    def _get_select_project_item(self):
        self._init_default_items()
        return self._select_project_item

    def _get_empty_items(self):
        self._init_default_items()
        return [
            self._empty_statuses_item,
            self._select_project_item,
        ]

    def _get_selection_items(self):
        self._init_default_items()
        return [
            self._select_all_item,
            self._deselect_all_item,
            self._swap_states_item,
        ]

    def _get_default_items(self):
        return self._get_empty_items() + self._get_selection_items()

    def _add_select_project_item(self):
        item = self._get_select_project_item()
        if item.row() < 0:
            self._remove_items()
            root_item = self.invisibleRootItem()
            root_item.appendRow(item)

    def _add_empty_statuses_item(self):
        item = self._get_empty_statuses_item()
        if item.row() < 0:
            self._remove_items()
            root_item = self.invisibleRootItem()
            root_item.appendRow(item)

    def _add_selection_items(self):
        root_item = self.invisibleRootItem()
        items = self._get_selection_items()
        for item in self._get_selection_items():
            row = item.row()
            if row >= 0:
                root_item.takeRow(row)
        root_item.appendRows(items)

    def _remove_items(self):
        root_item = self.invisibleRootItem()
        for item in self._get_default_items():
            if item.row() < 0:
                continue
            root_item.takeRow(item.row())

        root_item.removeRows(0, root_item.rowCount())
        self._items_by_name.clear()

    def _remove_empty_items(self):
        root_item = self.invisibleRootItem()
        for item in self._get_empty_items():
            if item.row() < 0:
                continue
            root_item.takeRow(item.row())


class StatusesCombobox(CustomPaintMultiselectComboBox):
    def __init__(self, controller, parent):
        self._controller = controller
        model = StatusesQtModel(controller)
        super().__init__(
            STATUS_NAME_ROLE,
            STATUS_SHORT_ROLE,
            STATUS_COLOR_ROLE,
            STATUS_ICON_ROLE,
            item_type_role=ITEM_TYPE_ROLE,
            model=model,
            parent=parent
        )
        self.set_placeholder_text("Version status filter...")
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
        self.setToolTip("Statuses filter")
        self.value_changed.connect(
            self._on_status_filter_change
        )

    def _on_status_filter_change(self):
        lines = ["Statuses filter"]
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
            self._on_status_filter_change()
