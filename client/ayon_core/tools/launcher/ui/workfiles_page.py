import time
from typing import Optional

import ayon_api
from qtpy import QtCore, QtWidgets, QtGui

from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.launcher.abstract import AbstractLauncherFrontEnd

VERSION_ROLE = QtCore.Qt.UserRole + 1
WORKFILE_ID_ROLE = QtCore.Qt.UserRole + 2
HOST_NAME_ROLE = QtCore.Qt.UserRole + 3


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
            item.setData(workfile_item.workfile_id, WORKFILE_ID_ROLE)
            item.setData(getattr(workfile_item, "host_name", None), HOST_NAME_ROLE)
            flags = QtCore.Qt.NoItemFlags
            if workfile_item.exists:
                flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
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

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.ToolTipRole:
            item = self.itemFromIndex(index)
            if item is None:
                return None
            workfile_id = item.data(WORKFILE_ID_ROLE)
            if workfile_id is None:
                return None
            if hasattr(self._controller, "get_workfile_tooltip_data"):
                tooltip = self._controller.get_workfile_tooltip_data(workfile_id)
                if tooltip:
                    return tooltip
            filename = item.data(QtCore.Qt.DisplayRole) or ""
            version = item.data(VERSION_ROLE)
            version_str = str(version) if version is not None else "—"
            host_name = item.data(HOST_NAME_ROLE)
            host_str = f"Host: {host_name}\n" if host_name else ""
            exists = (item.flags() & QtCore.Qt.ItemIsEnabled) != 0
            status = "On disk" if exists else "Missing"
            return f"{filename}\n{host_str}Version: {version_str}\n{status}"
        return super().data(index, role)


class WorkfilesView(QtWidgets.QTreeView):
    def drawBranches(self, painter, rect, index):
        return

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tooltip_style_applied = False

    def _apply_tooltip_stylesheet(self):
        if self._tooltip_style_applied:
            return
        self._tooltip_style_applied = True
        app = QtWidgets.QApplication.instance()
        if not app:
            return
        rule = (
            "QToolTip { background-color: #21252b; color: #d3d8de; "
            "border: none; }"
        )
        old = app.styleSheet() or ""
        if "QToolTip" not in old:
            app.setStyleSheet(old + ("\n" if old else "") + rule)

    def viewportEvent(self, event):
        if event.type() == QtCore.QEvent.ToolTip:
            help_ev = event
            index = self.indexAt(help_ev.pos())
            if index.isValid():
                tip = index.data(QtCore.Qt.ToolTipRole)
                if tip:
                    self._apply_tooltip_stylesheet()
                    font = QtGui.QFont()
                    font.setStyleHint(QtGui.QFont.TypeWriter)
                    QtWidgets.QToolTip.setFont(font)
                    QtWidgets.QToolTip.showText(
                        help_ev.globalPos(), tip, self.viewport()
                    )
                    return True
            QtWidgets.QToolTip.hideText()
            return True
        return super().viewportEvent(event)


class WorkfilesPage(QtWidgets.QWidget):
    def __init__(
        self,
        controller: AbstractLauncherFrontEnd,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        workfiles_view = WorkfilesView(self)
        workfiles_view.setIndentation(0)
        workfiles_view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        workfiles_model = WorkfilesModel(controller)
        workfiles_proxy = QtCore.QSortFilterProxyModel()
        workfiles_proxy.setSourceModel(workfiles_model)

        workfiles_view.setModel(workfiles_proxy)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(workfiles_view, 1)

        workfiles_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        workfiles_view.doubleClicked.connect(self._on_double_clicked_open)
        workfiles_model.refreshed.connect(self._on_refresh)

        self._controller = controller
        self._workfiles_view = workfiles_view
        self._workfiles_model = workfiles_model
        self._workfiles_proxy = workfiles_proxy
        self._last_open_workfile_id = None
        self._last_open_time = 0.0
        self._open_cooldown_seconds = 2.0

    def refresh(self) -> None:
        self._workfiles_model.refresh()

    def _on_refresh(self) -> None:
        self._workfiles_proxy.sort(0, QtCore.Qt.DescendingOrder)

    def _on_selection_changed(self, selected, _deselected) -> None:
        workfile_id = None
        for index in selected.indexes():
            workfile_id = index.data(WORKFILE_ID_ROLE)
        self._controller.set_selected_workfile(workfile_id)

    def _on_double_clicked_open(self, index: QtCore.QModelIndex) -> None:
        view = self._workfiles_view
        proxy = self._workfiles_proxy
        if not index.isValid():
            index = view.currentIndex()
        if not index.isValid():
            return
        index = index.sibling(index.row(), 0)
        source_index = proxy.mapToSource(index)
        if not source_index.isValid():
            return
        workfile_id = source_index.data(WORKFILE_ID_ROLE)
        host_name = source_index.data(HOST_NAME_ROLE)
        if workfile_id is None or not (source_index.flags() & QtCore.Qt.ItemIsEnabled):
            return
        now = time.monotonic()
        if (
            self._last_open_workfile_id == workfile_id
            and (now - self._last_open_time) < self._open_cooldown_seconds
        ):
            return
        self._last_open_workfile_id = workfile_id
        self._last_open_time = now
        self._controller.open_workfile_with_app(workfile_id, host_name)
