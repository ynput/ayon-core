from __future__ import annotations

from qtpy import QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.common_models import StatusItem

from ._multicombobox import (
    CustomPaintMultiselectComboBox,
    BaseQtModel,
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


class StatusesQtModel(BaseQtModel):
    def __init__(self, controller):
        self._items_by_name: dict[str, QtGui.QStandardItem] = {}
        self._icons_by_name_n_color: dict[str, QtGui.QIcon] = {}
        super().__init__(
            ITEM_TYPE_ROLE,
            ITEM_SUBTYPE_ROLE,
            "No statuses...",
            controller,
        )

    def _get_standard_items(self) -> list[QtGui.QStandardItem]:
        return list(self._items_by_name.values())

    def _clear_standard_items(self):
        self._items_by_name.clear()

    def _prepare_new_value_items(
        self, project_name: str, project_changed: bool
    ):
        status_items: list[StatusItem] = (
            self._controller.get_project_status_items(
                project_name, sender=STATUSES_FILTER_SENDER
            )
        )
        items = []
        items_to_remove = []
        if not status_items:
            return items, items_to_remove

        names_to_remove = set(self._items_by_name)
        for row_idx, status_item in enumerate(status_items):
            name = status_item.name
            if name in self._items_by_name:
                item = self._items_by_name[name]
                names_to_remove.discard(name)
            else:
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

            if project_changed:
                item.setCheckState(QtCore.Qt.Unchecked)
            items.append(item)

        for name in names_to_remove:
            items_to_remove.append(self._items_by_name.pop(name))

        return items, items_to_remove

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
