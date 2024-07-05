from typing import List, Dict

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.common_models import StatusItem

from ._multicombobox import CustomPaintMultiselectComboBox


STATUSES_FILTER_SENDER = "loader.statuses_filter"
STATUS_NAME_ROLE = QtCore.Qt.UserRole + 1
STATUS_SHORT_ROLE = QtCore.Qt.UserRole + 2
STATUS_COLOR_ROLE = QtCore.Qt.UserRole + 3
STATUS_ICON_ROLE = QtCore.Qt.UserRole + 4


class StatusesQtModel(QtGui.QStandardItemModel):
    def __init__(self, controller):
        self._controller = controller
        self._items_by_name: Dict[str, QtGui.QStandardItem] = {}
        self._icons_by_name_n_color: Dict[str, QtGui.QIcon] = {}
        self._last_project = None
        super().__init__()

    def refresh(self, project_name):
        # New project was selected
        #   status filter is reset to show all statuses
        check_all = False
        if project_name != self._last_project:
            self._last_project = project_name
            check_all = True

        status_items: List[StatusItem] = (
            self._controller.get_project_status_items(
                project_name, sender=STATUSES_FILTER_SENDER
            )
        )
        items_to_remove = set(self._items_by_name)
        root_item = self.invisibleRootItem()
        for row_idx, status_item in enumerate(status_items):
            name = status_item.name
            if name in self._items_by_name:
                is_new = False
                item = self._items_by_name[name]
                if check_all:
                    item.setCheckState(QtCore.Qt.Checked)
                items_to_remove.discard(name)
            else:
                is_new = True
                item = QtGui.QStandardItem()
                item.setCheckState(QtCore.Qt.Checked)
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


class StatusesCombobox(CustomPaintMultiselectComboBox):
    def __init__(self, controller, parent):
        self._controller = controller
        model = StatusesQtModel(controller)
        super().__init__(
            STATUS_NAME_ROLE,
            STATUS_SHORT_ROLE,
            STATUS_COLOR_ROLE,
            STATUS_ICON_ROLE,
            model=model,
            parent=parent
        )
        self.set_placeholder_text("Statuses filter..")
        self._model = model
        self._last_project_name = None

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
        tooltip = "Statuses filter"
        all_enabled = True
        all_disabled = True
        lines = []
        for item in self.get_all_value_info():
            status_name, enabled = item
            if enabled:
                all_disabled = False
            else:
                all_enabled = False

            lines.append(f"{'✔' if enabled else '☐'} {status_name}")

        if all_disabled:
            tooltip += "\n- All disabled"
        elif all_enabled:
            tooltip += "\n- All enabled"
        else:
            mod_names = "\n".join(lines)
            tooltip += f"\n{mod_names}"
        self.setToolTip(tooltip)

    def _on_project_change(self, event):
        project_name = event["project_name"]
        self._last_project_name = project_name
        self._model.refresh(project_name)
        self._on_status_filter_change()

    def _on_projects_refresh(self):
        if self._last_project_name:
            self._model.refresh(self._last_project_name)
            self._on_status_filter_change()
