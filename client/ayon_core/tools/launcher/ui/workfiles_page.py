from __future__ import annotations

import collections

from typing import Optional

import ayon_api
from qtpy import QtCore, QtWidgets, QtGui

from ayon_core.lib.icon_definitions import (
    AYONUrlIcon,
    UrlIcon,
    TransparentIcon,
)
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.delegates import pretty_timestamp, format_file_size
from ayon_core.tools.launcher.abstract import AbstractLauncherFrontEnd

from ayon_core.ui.components import (
    AYContainer,
    AYTreeView,
    AYMenu,
)
from ayon_core.ui.components.tree_view import TreeViewItemDelegate
from ayon_core.ui.style_types import get_ayon_style


ITEM_TYPE_ROLE = QtCore.Qt.UserRole + 1
WORKFILE_ID_ROLE = QtCore.Qt.UserRole + 2
UPDATED_AT_ROLE = QtCore.Qt.UserRole + 3
HOST_NAME_ROLE = QtCore.Qt.UserRole + 4
FILE_SIZE_ROLE = QtCore.Qt.UserRole + 5


class WorkfilesModel(QtGui.QStandardItemModel):
    refreshed = QtCore.Signal()

    def __init__(self, controller: AbstractLauncherFrontEnd) -> None:
        super().__init__()

        self.setColumnCount(3)
        self.setHeaderData(0, QtCore.Qt.Horizontal, "Workfiles")
        self.setHeaderData(1, QtCore.Qt.Horizontal, "Modified")
        self.setHeaderData(2, QtCore.Qt.Horizontal, "Size")

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

        self._group_host_names = set()

        self._controller = controller
        self._selected_project_name = None
        self._selected_folder_id = None
        self._selected_task_id = None

        # Cache
        self._transparent_icon = None
        self._cached_icons = {}
        self._host_items_by_name = {}
        self._items_by_host_name = collections.defaultdict(list)

    def refresh(self) -> None:
        self._group_host_names = set(
            self._controller.get_grouped_host_names()
        )

        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        workfile_items = self._controller.get_workfile_items(
            self._selected_project_name, self._selected_task_id
        )
        items_by_host_name = collections.defaultdict(list)
        for workfile_item in workfile_items:
            icon = self._get_icon(workfile_item.icon)
            host_name = workfile_item.host_name

            item = QtGui.QStandardItem(workfile_item.filename)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(workfile_item.workfile_id, WORKFILE_ID_ROLE)
            item.setData(workfile_item.updated_at_time, UPDATED_AT_ROLE)
            item.setData(host_name, HOST_NAME_ROLE)
            item.setData(workfile_item.file_size, FILE_SIZE_ROLE)
            item.setData(0, ITEM_TYPE_ROLE)
            item.setColumnCount(3)
            flags = QtCore.Qt.NoItemFlags
            if workfile_item.exists:
                flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
            item.setFlags(flags)

            items_by_host_name[host_name].append(item)

        new_items = []
        host_items_by_name = {}
        for host_name, items in items_by_host_name.items():
            icon = next(
                (item.data(QtCore.Qt.DecorationRole) for item in items),
                None
            )

            host_item = QtGui.QStandardItem(
                host_name or "<Unknown Host>"
            )
            host_item.setData(icon, QtCore.Qt.DecorationRole)
            host_item.setData(host_name, HOST_NAME_ROLE)
            host_item.setData(1, ITEM_TYPE_ROLE)
            host_item.setFlags(QtCore.Qt.ItemIsEnabled)
            host_item.setColumnCount(3)
            host_items_by_name[host_name] = host_item
            if host_name in self._group_host_names:
                new_items.append(host_item)
            else:
                new_items.extend(items)

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
            new_items = [item]

        root_item.appendRows(new_items)

        self._host_items_by_name = host_items_by_name
        self._items_by_host_name = items_by_host_name

        self.refreshed.emit()

    def set_group_by_host_name(
        self,
        host_name: str | None,
        group: bool | None = None,
    ) -> None:
        if group is None:
            group = host_name not in self._group_host_names

        if group and host_name in self._group_host_names:
            return

        if not group and host_name not in self._group_host_names:
            return

        host_item = self._host_items_by_name.get(host_name)
        items = self._items_by_host_name.get(host_name)
        if host_item is None or not items:
            return

        root_item = self.invisibleRootItem()
        if group:
            for item in items:
                root_item.takeRow(item.row())
            root_item.appendRow(host_item)
            self._group_host_names.add(host_name)
        else:
            root_item.takeRow(host_item.row())
            root_item.appendRows(items)
            self._group_host_names.discard(host_name)

        self._controller.set_grouped_host_names(list(self._group_host_names))

    def flags(self, index):
        if index.column() != 0:
            index = self.index(index.row(), 0, index.parent())
        return super().flags(index)

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if role in {
            WORKFILE_ID_ROLE,
            HOST_NAME_ROLE,
            ITEM_TYPE_ROLE,
            FILE_SIZE_ROLE
        }:
            index = self.index(index.row(), 0, index.parent())
            return super().data(index, role)
        
        if index.column() == 1:
            if role == QtCore.Qt.DisplayRole:
                role = UPDATED_AT_ROLE
                index = self.index(index.row(), 0, index.parent())
            else:
                return None
        elif index.column() == 2:
            if role == QtCore.Qt.DisplayRole:
                return self.data(index, FILE_SIZE_ROLE)
            else:
                return None
        return super().data(index, role)

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
            self._transparent_icon = get_qt_icon(
                TransparentIcon(256)
            )
        return self._transparent_icon

    def _get_icon(self, icon_url: Optional[str]) -> QtGui.QIcon:
        if icon_url is None:
            return self._get_transparent_icon()
        icon = self._cached_icons.get(icon_url)
        if icon is not None:
            return icon

        base_url = ayon_api.get_base_url()
        if icon_url.startswith(base_url):
            url = icon_url[len(base_url) + 1:]
            icon_def = AYONUrlIcon(url)
        else:
            icon_def = UrlIcon(icon_url)

        icon = get_qt_icon(icon_def)
        if icon is None:
            icon = self._get_transparent_icon()
        self._cached_icons[icon_url] = icon
        return icon


class WorkfileSortFilterProxy(QtCore.QSortFilterProxyModel):
    def lessThan(self, source_left, source_right):
        l_host = source_left.data(HOST_NAME_ROLE)
        r_host = source_right.data(HOST_NAME_ROLE)
        if l_host != r_host:
            if l_host is None:
                return True
            if r_host is None:
                return False
            if self.sortOrder() == QtCore.Qt.DescendingOrder:
                return l_host > r_host
            return l_host < r_host
        return super().lessThan(source_left, source_right)


class WorkfilesDelegate(TreeViewItemDelegate):
    """Unified delegate for the workfiles tree view.

    Column 0: workfile name with middle-elide.
    Column 1: pretty-printed timestamp (falls back to ``"N/A"``).
    Column 2: file size in human-readable format (falls back to ``"N/A"``).
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.column() == 0:
            option.textElideMode = QtCore.Qt.ElideMiddle
        elif index.column() == 1:
            # Column 1 exposes timestamp through DisplayRole in WorkfilesModel.
            raw = index.data(QtCore.Qt.DisplayRole)
            if raw is not None:
                pretty = pretty_timestamp(raw)
                if pretty is not None:
                    option.text = pretty
                    return
            option.text = "N/A"
        elif index.column() == 2:
            raw = index.data(QtCore.Qt.DisplayRole)
            if raw is not None:
                option.text = format_file_size(raw)
            else:
                option.text = "N/A"


class WorkfilesPage(AYContainer):
    def __init__(
        self,
        controller: AbstractLauncherFrontEnd,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
            layout_spacing=0,
        )

        workfiles_view = AYTreeView(self, item_height=23, item_padding=[1, 6])
        workfiles_view.setHeaderHidden(False)
        workfiles_view.setIndentation(0)
        workfiles_view.setSortingEnabled(True)
        workfiles_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        workfiles_model = WorkfilesModel(controller)
        workfiles_proxy = WorkfileSortFilterProxy()
        workfiles_proxy.setSourceModel(workfiles_model)

        workfiles_view.setModel(workfiles_proxy)

        workfiles_delegate = WorkfilesDelegate(
            parent=workfiles_view,
            style_model=get_ayon_style().model,
            item_height=23,
            item_padding=[1, 6]
        )
        workfiles_view.setItemDelegate(workfiles_delegate)

        self.add_widget(workfiles_view, stretch=1)

        resize_timer = QtCore.QTimer()

        workfiles_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        workfiles_view.doubleClicked.connect(self._on_view_clicked)
        workfiles_view.customContextMenuRequested.connect(
            self._on_custom_menu_request
        )
        resize_timer.timeout.connect(self._on_resize_timer)

        self._controller = controller
        self._workfiles_view = workfiles_view
        self._workfiles_delegate = workfiles_delegate
        self._workfiles_model = workfiles_model
        self._workfiles_proxy = workfiles_proxy
        self._resize_timer = resize_timer
        self._resize_counter = 0

    def showEvent(self, event) -> None:
        super().showEvent(event)

        self._resize_timer.start()

    def refresh(self) -> None:
        self._workfiles_model.refresh()

    def deselect(self):
        sel_model = self._workfiles_view.selectionModel()
        sel_model.clearSelection()

    def _on_resize_timer(self):
        # --- NOTE ---
        # Because the date column does not store string value to display
        #   but float value then displayed using delegate we're not
        #   able to get the width of the column using standard methods.
        # For that a default width of date column is set to 160 but resizing
        #   second column is not allowed, instead we can resize the first
        #   column. For that we need size of the view which is known only
        #   after 2 Qt app loops.

        # Make sure the logic happens only once
        if self._resize_counter == 2:
            self._resize_timer.stop()
            return

        self._resize_counter += 1
        if self._resize_counter < 2:
            return

        # NOTE changing resize mode during initialization crashes application
        view_header = self._workfiles_view.header()
        view_header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Interactive
        )
        view_header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Interactive
        )
        view_header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeMode.Interactive
        )

        # Resize workfiles column
        view_size = self._workfiles_view.size()
        col_0_width = view_size.width() - 220
        if col_0_width < 120:
            col_0_width = 120
        view_header.resizeSection(0, col_0_width)
        view_header.resizeSection(1, 140)
        view_header.resizeSection(2, 80)

    def _on_selection_changed(self, selected, _deselected) -> None:
        workfile_id = None
        for index in selected.indexes():
            workfile_id = index.data(WORKFILE_ID_ROLE)
        self._controller.set_selected_workfile(workfile_id)

    def _on_view_clicked(self, index) -> None:
        if not index.isValid() or index.data(ITEM_TYPE_ROLE) != 1:
            return
        host_name = index.data(HOST_NAME_ROLE)
        self._workfiles_model.set_group_by_host_name(host_name)

    def _on_custom_menu_request(self, point):
        index = self._workfiles_view.indexAt(point)
        if not index.isValid():
            return

        item_type = index.data(ITEM_TYPE_ROLE)
        if item_type is None:
            return

        action_title = None
        if item_type == 0:
            action_title = "Group by host"
        elif item_type == 1:
            action_title = "Ungroup (double-click)"

        if action_title is None:
            return

        # TODO: using AYMenu breaking the tool need to figure out the issue
        # menu = AYMenu(self._workfiles_view)
        # Found that in AYMenu Forcing the menu to use AYONStyle for drawing
        # it causing the application collapse
        menu = QtWidgets.QMenu(self._workfiles_view)
        menu.addAction(action_title)

        global_pos = self._workfiles_view.viewport().mapToGlobal(point)
        action = menu.exec_(global_pos)
        if action is not None:
            host_name = index.data(HOST_NAME_ROLE)
            self._workfiles_model.set_group_by_host_name(host_name)
