from __future__ import annotations

import collections
from typing import Optional

from qtpy import QtWidgets, QtCore

from ayon_core.pipeline.compatibility import is_product_base_type_supported
from ayon_core.tools.utils import (
    RecursiveSortFilterProxyModel,
    DeselectableTreeView,
)
from ayon_core.tools.utils.delegates import PrettyTimeDelegate, StatusDelegate

from .products_model import (
    ProductsModel,
    PRODUCTS_MODEL_SENDER_NAME,
    PRODUCT_TYPE_ROLE,
    GROUP_TYPE_ROLE,
    MERGED_COLOR_ROLE,
    FOLDER_ID_ROLE,
    TASK_ID_ROLE,
    PRODUCT_ID_ROLE,
    VERSION_ID_ROLE,
    VERSION_STATUS_NAME_ROLE,
    VERSION_STATUS_SHORT_ROLE,
    VERSION_STATUS_COLOR_ROLE,
    VERSION_STATUS_ICON_ROLE,
    VERSION_THUMBNAIL_ID_ROLE,
    STATUS_NAME_FILTER_ROLE,
    VERSION_TAGS_FILTER_ROLE,
    TASK_TAGS_FILTER_ROLE,
)
from .products_delegates import (
    VersionDelegate,
    LoadedInSceneDelegate,
    SiteSyncDelegate,
)
from .actions_utils import show_actions_menu


class ProductsProxyModel(RecursiveSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)

        self._product_type_filters = None
        self._statuses_filter = None
        self._version_tags_filter = None
        self._task_tags_filter = None
        self._task_ids_filter = None
        self._ascending_sort = True

    def get_statuses_filter(self):
        if self._statuses_filter is None:
            return None
        return set(self._statuses_filter)

    def set_tasks_filter(self, task_ids_filter):
        if self._task_ids_filter == task_ids_filter:
            return
        self._task_ids_filter = task_ids_filter
        self.invalidateFilter()

    def set_product_type_filters(self, product_type_filters):
        if self._product_type_filters == product_type_filters:
            return
        self._product_type_filters = product_type_filters
        self.invalidateFilter()

    def set_statuses_filter(self, statuses_filter):
        if self._statuses_filter == statuses_filter:
            return
        self._statuses_filter = statuses_filter
        self.invalidateFilter()

    def set_version_tags_filter(self, tags):
        if self._version_tags_filter == tags:
            return
        self._version_tags_filter = tags
        self.invalidateFilter()

    def set_task_tags_filter(self, tags):
        if self._task_tags_filter == tags:
            return
        self._task_tags_filter = tags
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        source_model = self.sourceModel()
        index = source_model.index(source_row, 0, source_parent)
        if not self._accept_task_ids_filter(index):
            return False

        if not self._accept_row_by_role_value(
            index, self._product_type_filters, PRODUCT_TYPE_ROLE
        ):
            return False

        if not self._accept_row_by_role_value(
            index, self._statuses_filter, STATUS_NAME_FILTER_ROLE
        ):
            return False

        if not self._accept_row_by_role_value(
            index, self._version_tags_filter, VERSION_TAGS_FILTER_ROLE
        ):
            return False

        if not self._accept_row_by_role_value(
            index, self._task_tags_filter, TASK_TAGS_FILTER_ROLE
        ):
            return False

        return super().filterAcceptsRow(source_row, source_parent)

    def _accept_task_ids_filter(self, index):
        if not self._task_ids_filter:
            return True
        task_id = index.data(TASK_ID_ROLE)
        return task_id in self._task_ids_filter

    def _accept_row_by_role_value(
        self,
        index: QtCore.QModelIndex,
        filter_value: Optional[set[str]],
        role: int
    ):
        if filter_value is None:
            return True
        if not filter_value:
            return False

        value_s = index.data(role)
        if value_s:
            for value in value_s.split("|"):
                if value in filter_value:
                    return True
        return False

    def lessThan(self, left, right):
        l_model = left.model()
        r_model = right.model()
        left_group_type = l_model.data(left, GROUP_TYPE_ROLE)
        right_group_type = r_model.data(right, GROUP_TYPE_ROLE)
        # Groups are always on top, merged product types are below
        #   and items without group at the bottom
        # QUESTION Do we need to do it this way?
        if left_group_type != right_group_type:
            if left_group_type is None:
                output = False
            elif right_group_type is None:
                output = True
            else:
                output = left_group_type < right_group_type
            if not self._ascending_sort:
                output = not output
            return output
        return super().lessThan(left, right)

    def sort(self, column, order=None):
        if order is None:
            order = QtCore.Qt.AscendingOrder
        self._ascending_sort = order == QtCore.Qt.AscendingOrder
        super().sort(column, order)


class ProductsWidget(QtWidgets.QWidget):
    refreshed = QtCore.Signal()
    merged_products_selection_changed = QtCore.Signal()
    selection_changed = QtCore.Signal()
    default_widths = (
        200,  # Product name
        90,   # Product type
        90,   # Product base type
        130,  # Folder label
        60,   # Version
        100,  # Status
        125,  # Time
        75,   # Author
        75,   # Frames
        60,   # Duration
        55,   # Handles
        10,   # Step
        25,   # Loaded in scene
        65,   # Site sync info
    )

    def __init__(self, controller, parent):
        super(ProductsWidget, self).__init__(parent)

        self._controller = controller

        products_view = DeselectableTreeView(self)
        # TODO - define custom object name in style
        products_view.setObjectName("ProductView")
        products_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        products_view.setAllColumnsShowFocus(True)
        # TODO - add context menu
        products_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        products_view.setSortingEnabled(True)
        # Sort by product type
        products_view.sortByColumn(1, QtCore.Qt.AscendingOrder)
        products_view.setAlternatingRowColors(True)

        products_model = ProductsModel(controller)
        products_proxy_model = ProductsProxyModel()
        products_proxy_model.setSourceModel(products_model)

        products_view.setModel(products_proxy_model)

        for idx, width in enumerate(self.default_widths):
            products_view.setColumnWidth(idx, width)

        version_delegate = VersionDelegate()
        time_delegate = PrettyTimeDelegate()
        status_delegate = StatusDelegate(
            VERSION_STATUS_NAME_ROLE,
            VERSION_STATUS_SHORT_ROLE,
            VERSION_STATUS_COLOR_ROLE,
            VERSION_STATUS_ICON_ROLE,
        )
        in_scene_delegate = LoadedInSceneDelegate()
        sitesync_delegate = SiteSyncDelegate()

        for col, delegate in (
            (products_model.version_col, version_delegate),
            (products_model.published_time_col, time_delegate),
            (products_model.status_col, status_delegate),
            (products_model.in_scene_col, in_scene_delegate),
            (products_model.sitesync_avail_col, sitesync_delegate),
        ):
            products_view.setItemDelegateForColumn(col, delegate)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(products_view, 1)

        products_proxy_model.rowsInserted.connect(self._on_rows_inserted)
        products_proxy_model.rowsMoved.connect(self._on_rows_moved)
        products_model.refreshed.connect(self._on_refresh)
        products_model.version_changed.connect(self._on_version_change)
        products_view.customContextMenuRequested.connect(
            self._on_context_menu)
        products_view_sel_model = products_view.selectionModel()
        products_view_sel_model.selectionChanged.connect(
            self._on_selection_change)
        version_delegate.version_changed.connect(
            self._on_version_delegate_change
        )

        controller.register_event_callback(
            "selection.folders.changed",
            self._on_folders_selection_change,
        )
        controller.register_event_callback(
            "products.refresh.finished",
            self._on_products_refresh_finished
        )
        controller.register_event_callback(
            "products.group.changed",
            self._on_group_changed
        )

        self._products_view = products_view
        self._products_model = products_model
        self._products_proxy_model = products_proxy_model

        self._version_delegate = version_delegate
        self._time_delegate = time_delegate
        self._status_delegate = status_delegate
        self._in_scene_delegate = in_scene_delegate
        self._sitesync_delegate = sitesync_delegate

        self._selected_project_name = None
        self._selected_folder_ids = set()

        self._selected_merged_products = []
        self._selected_versions_info = []

        # Set initial state of widget
        # - Hide folders column
        self._update_folders_label_visible()
        # - Hide in scene column if is not supported (this won't change)
        products_view.setColumnHidden(
            products_model.in_scene_col,
            not controller.is_loaded_products_supported()
        )
        self._set_sitesync_visibility(
            self._controller.is_sitesync_enabled()
        )

        if not is_product_base_type_supported():
            # Hide product base type column
            products_view.setColumnHidden(
                products_model.product_base_type_col, True
            )

    def set_name_filter(self, name):
        """Set filter of product name.

        Args:
            name (str): The string filter.

        """
        self._products_proxy_model.setFilterFixedString(name)

    def set_tasks_filter(self, task_ids):
        """Set filter of version tasks.

        Args:
            task_ids (set[str]): Task ids.

        """
        self._version_delegate.set_tasks_filter(task_ids)
        self._products_proxy_model.set_tasks_filter(task_ids)

    def set_statuses_filter(self, status_names):
        """Set filter of version statuses.

        Args:
            status_names (list[str]): The list of status names.

        """
        self._version_delegate.set_statuses_filter(status_names)
        self._products_proxy_model.set_statuses_filter(status_names)

    def set_version_tags_filter(self, version_tags):
        self._version_delegate.set_version_tags_filter(version_tags)
        self._products_proxy_model.set_version_tags_filter(version_tags)

    def set_task_tags_filter(self, task_tags):
        self._version_delegate.set_task_tags_filter(task_tags)
        self._products_proxy_model.set_task_tags_filter(task_tags)

    def set_product_type_filter(self, product_type_filters):
        """

        Args:
            product_type_filters (dict[str, bool]): The filter of product
                types.
        """

        self._products_proxy_model.set_product_type_filters(
            product_type_filters
        )

    def set_enable_grouping(self, enable_grouping):
        self._products_model.set_enable_grouping(enable_grouping)

    def get_selected_merged_products(self):
        return self._selected_merged_products

    def get_selected_version_info(self):
        return self._selected_versions_info

    def refresh(self):
        self._refresh_model()

    def _set_sitesync_visibility(self, sitesync_enabled):
        self._products_view.setColumnHidden(
            self._products_model.sitesync_avail_col,
            not sitesync_enabled
        )

    def _fill_version_editor(self):
        model = self._products_proxy_model
        index_queue = collections.deque()
        for row in range(model.rowCount()):
            index_queue.append((row, None))

        version_col = self._products_model.version_col
        while index_queue:
            (row, parent_index) = index_queue.popleft()
            args = [row, 0]
            if parent_index is not None:
                args.append(parent_index)
            index = model.index(*args)
            rows = model.rowCount(index)
            for row in range(rows):
                index_queue.append((row, index))

            product_id = model.data(index, PRODUCT_ID_ROLE)
            if product_id is not None:
                args[1] = version_col
                v_index = model.index(*args)
                self._products_view.openPersistentEditor(v_index)

    def _on_refresh(self):
        self._fill_version_editor()
        self.refreshed.emit()

    def _on_rows_inserted(self):
        self._fill_version_editor()

    def _on_rows_moved(self):
        self._fill_version_editor()

    def _refresh_model(self):
        self._products_model.refresh(
            self._selected_project_name,
            self._selected_folder_ids
        )

    def _on_context_menu(self, point):
        selection_model = self._products_view.selectionModel()
        model = self._products_view.model()
        project_name = self._products_model.get_last_project_name()

        version_ids = set()
        indexes_queue = collections.deque()
        indexes_queue.extend(selection_model.selectedIndexes())
        while indexes_queue:
            index = indexes_queue.popleft()
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                indexes_queue.append(child_index)
            version_id = model.data(index, VERSION_ID_ROLE)
            if version_id is not None:
                version_ids.add(version_id)

        action_items = self._controller.get_versions_action_items(
            project_name, version_ids)

        # Prepare global point where to show the menu
        global_point = self._products_view.mapToGlobal(point)

        result = show_actions_menu(
            action_items,
            global_point,
            len(version_ids) == 1,
            self
        )
        action_item, options = result
        if action_item is None or options is None:
            return

        self._controller.trigger_action_item(
            action_item.identifier,
            options,
            action_item.project_name,
            version_ids=action_item.version_ids,
            representation_ids=action_item.representation_ids,
        )

    def _on_selection_change(self):
        selected_merged_products = []
        selection_model = self._products_view.selectionModel()
        model = self._products_view.model()
        indexes_queue = collections.deque()
        indexes_queue.extend(selection_model.selectedIndexes())

        # Helper for 'version_items' to avoid duplicated items
        all_product_ids = set()
        selected_version_ids = set()
        # Version items contains information about selected version items
        selected_versions_info = []
        while indexes_queue:
            index = indexes_queue.popleft()
            if index.column() != 0:
                continue

            group_type = model.data(index, GROUP_TYPE_ROLE)
            if group_type is None:
                product_id = model.data(index, PRODUCT_ID_ROLE)
                # Skip duplicates - when group and item are selected the item
                #   would be in the loop multiple times
                if product_id in all_product_ids:
                    continue

                all_product_ids.add(product_id)

                version_id = model.data(index, VERSION_ID_ROLE)
                selected_version_ids.add(version_id)

                thumbnail_id = model.data(index, VERSION_THUMBNAIL_ID_ROLE)
                selected_versions_info.append({
                    "folder_id": model.data(index, FOLDER_ID_ROLE),
                    "product_id": product_id,
                    "version_id": version_id,
                    "thumbnail_id": thumbnail_id,
                })
                continue

            if group_type == 0:
                for row in range(model.rowCount(index)):
                    child_index = model.index(row, 0, index)
                    indexes_queue.append(child_index)
                continue

            if group_type != 1:
                continue

            item_folder_ids = set()
            for row in range(model.rowCount(index)):
                child_index = model.index(row, 0, index)
                indexes_queue.append(child_index)

                folder_id = model.data(child_index, FOLDER_ID_ROLE)
                item_folder_ids.add(folder_id)

            if not item_folder_ids:
                continue

            hex_color = model.data(index, MERGED_COLOR_ROLE)
            item_data = {
                "color": hex_color,
                "folder_ids": item_folder_ids
            }
            selected_merged_products.append(item_data)

        prev_selected_merged_products = self._selected_merged_products
        self._selected_merged_products = selected_merged_products
        self._selected_versions_info = selected_versions_info

        if selected_merged_products != prev_selected_merged_products:
            self.merged_products_selection_changed.emit()
        self.selection_changed.emit()
        self._controller.set_selected_versions(selected_version_ids)

    def _on_version_change(self):
        self._on_selection_change()

    def _on_version_delegate_change(self, product_id, version_id):
        self._products_model.set_product_version(product_id, version_id)

    def _on_folders_selection_change(self, event):
        project_name = event["project_name"]
        sitesync_enabled = self._controller.is_sitesync_enabled(
            project_name
        )
        self._set_sitesync_visibility(sitesync_enabled)
        self._selected_project_name = project_name
        self._selected_folder_ids = event["folder_ids"]
        self._refresh_model()
        self._update_folders_label_visible()

    def _update_folders_label_visible(self):
        folders_label_hidden = len(self._selected_folder_ids) <= 1
        self._products_view.setColumnHidden(
            self._products_model.folders_label_col,
            folders_label_hidden
        )

    def _on_products_refresh_finished(self, event):
        if event["sender"] != PRODUCTS_MODEL_SENDER_NAME:
            self._refresh_model()

    def _on_group_changed(self, event):
        if event["project_name"] != self._selected_project_name:
            return
        folder_ids = event["folder_ids"]
        if not set(folder_ids).intersection(set(self._selected_folder_ids)):
            return
        self.refresh()
