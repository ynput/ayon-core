from typing import Optional

import ayon_api
from qtpy import QtCore, QtWidgets, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.launcher.abstract import AbstractLauncherFrontEnd

VERSION_ROLE = QtCore.Qt.UserRole + 1


class WorkfilesModel(QtGui.QStandardItemModel):
    refreshed = QtCore.Signal()

    def __init__(self, controller: AbstractLauncherFrontEnd) -> None:
        super().__init__()

        self.setColumnCount(1)
        self.setHeaderData(0, QtCore.Qt.Horizontal, "Workfiles")

        controller.register_event_callback(
            "selection.project.changed",
            self._on_selection_project_changed,
        )
        controller.register_event_callback(
            "selection.folder.changed",
            self._on_selection_folder_changed,
        )
        controller.register_event_callback(
            "selection.task.changed",
            self._on_selection_task_changed,
        )

        self._controller = controller
        self._selected_project_name = None
        self._selected_folder_id = None
        self._selected_task_id = None

        self._transparent_icon = None

        self._cached_icons = {}

    def refresh(self) -> None:
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        workfile_items = self._controller.get_workfile_items(
            self._selected_project_name, self._selected_task_id
        )
        new_items = []
        for workfile_item in workfile_items:
            icon = self._get_icon(workfile_item.icon)
            item = QtGui.QStandardItem(workfile_item.filename)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(workfile_item.version, VERSION_ROLE)
            flags = QtCore.Qt.NoItemFlags
            if workfile_item.exists:
                flags = QtCore.Qt.ItemIsEnabled
            item.setFlags(flags)
            new_items.append(item)

        if not new_items:
            title = "< No workfiles >"
            if not self._selected_project_name:
                title = "< Select a project >"
            elif not self._selected_folder_id:
                title = "< Select a folder >"
            elif not self._selected_task_id:
                title = "< Select a task >"
            item = QtGui.QStandardItem(title)
            item.setFlags(QtCore.Qt.NoItemFlags)
            new_items.append(item)
        root_item.appendRows(new_items)

        self.refreshed.emit()

    def _on_selection_project_changed(self, event) -> None:
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = None
        self._selected_task_id = None
        self.refresh()

    def _on_selection_folder_changed(self, event) -> None:
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = None
        self.refresh()

    def _on_selection_task_changed(self, event) -> None:
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = event["task_id"]
        self.refresh()

    def _get_transparent_icon(self) -> QtGui.QIcon:
        if self._transparent_icon is None:
            self._transparent_icon = get_qt_icon({
                "type": "transparent", "size": 256
            })
        return self._transparent_icon

    def _get_icon(self, icon_url: Optional[str]) -> QtGui.QIcon:
        if icon_url is None:
            return self._get_transparent_icon()
        icon = self._cached_icons.get(icon_url)
        if icon is not None:
            return icon

        base_url = ayon_api.get_base_url()
        if icon_url.startswith(base_url):
            icon_def = {
                "type": "ayon_url",
                "url": icon_url[len(base_url) + 1:],
            }
        else:
            icon_def = {
                "type": "url",
                "url": icon_url,
            }

        icon = get_qt_icon(icon_def)
        if icon is None:
            icon = self._get_transparent_icon()
        self._cached_icons[icon_url] = icon
        return icon


class WorkfilesView(QtWidgets.QTreeView):
    def drawBranches(self, painter, rect, index):
        return


class WorkfilesPage(QtWidgets.QWidget):
    def __init__(
        self,
        controller: AbstractLauncherFrontEnd,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        workfiles_view = WorkfilesView(self)
        workfiles_view.setIndentation(0)
        workfiles_model = WorkfilesModel(controller)
        workfiles_proxy = QtCore.QSortFilterProxyModel()
        workfiles_proxy.setSourceModel(workfiles_model)

        workfiles_view.setModel(workfiles_proxy)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(workfiles_view, 1)

        workfiles_model.refreshed.connect(self._on_refresh)

        self._controller = controller
        self._workfiles_view = workfiles_view
        self._workfiles_model = workfiles_model
        self._workfiles_proxy = workfiles_proxy

    def refresh(self) -> None:
        self._workfiles_model.refresh()

    def _on_refresh(self) -> None:
        self._workfiles_proxy.sort(0, QtCore.Qt.DescendingOrder )
