from __future__ import annotations

import collections
import numbers
from typing import Optional

from qtpy import QtWidgets, QtCore

from ayon_core.lib import Logger
from ayon_core.pipeline.compatibility import is_product_base_type_supported
from ayon_core.tools.loader.drag_drop import (
    LOADER_PAYLOAD_MIME_TYPE,
    encode_loader_drag_payload,
    loader_payload_to_bytes,
)
from ayon_core.tools.utils import (
    RecursiveSortFilterProxyModel,
)
from ayon_core.tools.utils.lib import format_version

from .products_model import (
    ProductsModel,
    PRODUCTS_MODEL_SENDER_NAME,
    PRODUCT_TYPE_ROLE,
    PRODUCT_NAME_ROLE,
    VERSION_NAME_ROLE,
    GROUP_TYPE_ROLE,
    MERGED_COLOR_ROLE,
    FOLDER_ID_ROLE,
    TASK_ID_ROLE,
    PRODUCT_ID_ROLE,
    VERSION_ID_ROLE,
    VERSION_THUMBNAIL_ID_ROLE,
    STATUS_NAME_FILTER_ROLE,
    VERSION_TAGS_FILTER_ROLE,
    TASK_TAGS_FILTER_ROLE,
)
from .products_proxy_selection import collect_version_ids_from_column0_indexes
from .products_tree_view_setup import configure_loader_products_tree_view
from .actions_utils import (
    DragPayloadPrecache,
    LoaderDragTreeView,
    show_actions_menu,
)

_log = Logger.get_logger(__name__)


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

    def supportedDragActions(self):
        """Return CopyAction so the view initiates drag (loader DnD)."""
        return QtCore.Qt.CopyAction

    def mimeTypes(self):
        """MIME type for loader drag payload (required for view to start drag)."""
        return [LOADER_PAYLOAD_MIME_TYPE]

    def mimeData(self, indexes):
        """Build loader payload from selected indexes so the view starts drag."""
        if _log:
            _log.debug("mimeData: indexes count=%s", len(indexes) if indexes else 0)
        if not indexes:
            if _log:
                _log.debug("mimeData: returning None (no indexes)")
            return None
        source = self.sourceModel()
        project_name = getattr(source, "get_last_project_name", lambda: None)()
        if _log:
            _log.debug("mimeData: project_name=%s", project_name)
        if not project_name:
            if _log:
                _log.debug("mimeData: returning None (no project_name)")
            return None
        version_ids = []
        seen = set()
        for idx in indexes:
            if idx.column() != 0:
                idx = idx.sibling(idx.row(), 0)
            src_idx = self.mapToSource(idx)
            if not src_idx.isValid() or src_idx in seen:
                continue
            seen.add(src_idx)
            vid = source.data(src_idx, VERSION_ID_ROLE)
            if vid:
                version_ids.append(vid)
        if _log:
            _log.debug("mimeData: version_ids=%s", version_ids)
        if not version_ids:
            if _log:
                _log.debug("mimeData: returning None (no version_ids)")
            return None
        payload = encode_loader_drag_payload(
            project_name, "version", version_ids, []
        )
        mime = QtCore.QMimeData()
        mime.setData(
            LOADER_PAYLOAD_MIME_TYPE,
            QtCore.QByteArray(loader_payload_to_bytes(payload)),
        )
        if _log:
            _log.debug("mimeData: returning QMimeData")
        return mime

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
        role: int,
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

    def __init__(self, controller, parent):
        super(ProductsWidget, self).__init__(parent)

        self._controller = controller

        products_view = LoaderDragTreeView(self)
        # TODO - define custom object name in style
        products_view.setObjectName("ProductView")
        products_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection
        )
        products_view.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows
        )
        products_view.setAllColumnsShowFocus(False)
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

        delegates = configure_loader_products_tree_view(
            products_view, products_model, controller, hide_folders_column=False
        )
        self._version_delegate = delegates["version_delegate"]
        self._time_delegate = delegates["time_delegate"]
        self._status_delegate = delegates["status_delegate"]
        self._in_scene_delegate = delegates["in_scene_delegate"]
        self._sitesync_delegate = delegates["sitesync_delegate"]

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(products_view, 1)

        products_proxy_model.rowsInserted.connect(self._on_rows_inserted)
        products_proxy_model.rowsMoved.connect(self._on_rows_moved)
        products_model.refreshed.connect(self._on_refresh)
        products_model.version_changed.connect(self._on_version_change)
        products_view.customContextMenuRequested.connect(self._on_context_menu)
        products_view_sel_model = products_view.selectionModel()
        products_view_sel_model.selectionChanged.connect(
            self._on_selection_change
        )
        self._version_delegate.version_changed.connect(
            self._on_version_delegate_change
        )

        controller.register_event_callback(
            "selection.folders.changed",
            self._on_folders_selection_change,
        )
        controller.register_event_callback(
            "products.refresh.finished", self._on_products_refresh_finished
        )
        controller.register_event_callback(
            "products.group.changed", self._on_group_changed
        )

        products_view.set_drag_data_callback(self._get_products_drag_data)
        products_view.set_drag_pixmap_context_callback(
            self._products_drag_pixmap_context
        )
        self._drag_precache = DragPayloadPrecache()
        products_view.set_drag_precache(self._drag_precache)

        self._products_view = products_view
        self._products_model = products_model
        self._products_proxy_model = products_proxy_model

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
            not controller.is_loaded_products_supported(),
        )
        self._set_sitesync_visibility(self._controller.is_sitesync_enabled())

        if not is_product_base_type_supported():
            # Hide product base type column
            products_view.setColumnHidden(
                products_model.product_base_type_col, True
            )

    def get_proxy_model(self):
        """Filtered/sorted products proxy model.

        Used by alternate views (e.g. grid) to share the same filter chain.
        """
        return self._products_proxy_model

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
            self._products_model.sitesync_avail_col, not sitesync_enabled
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
            self._selected_project_name, self._selected_folder_ids
        )

    def open_loader_context_from_version_editor(
        self,
        global_pos,
        version_column_index,
    ):
        """Show loader actions menu when right-clicking a version combo.

        Triggered by `VersionDelegate.eventFilter`; mirrors the canonical
        `_on_context_menu` flow but seeded by a single proxy index that
        identifies the row under the persistent version editor instead of
        relying on the current selection.
        """
        if not version_column_index.isValid():
            return
        model = self._products_view.model()
        idx0 = model.index(
            version_column_index.row(),
            0,
            version_column_index.parent(),
        )
        if not idx0.isValid():
            return

        selection_model = self._products_view.selectionModel()
        selection_model.clearSelection()
        selection_model.select(
            idx0, QtCore.QItemSelectionModel.SelectionFlag.Select
        )
        self._products_view.setCurrentIndex(idx0)

        project_name = self._products_model.get_last_project_name()
        version_ids = set()
        group_type = model.data(idx0, GROUP_TYPE_ROLE)
        if group_type == 1:
            for row in range(model.rowCount(idx0)):
                child_index = model.index(row, 0, idx0)
                child_version_id = model.data(child_index, VERSION_ID_ROLE)
                if child_version_id is not None:
                    version_ids.add(child_version_id)
        elif group_type == 0:
            for row in range(model.rowCount(idx0)):
                child_index = model.index(row, 0, idx0)
                child_version_id = model.data(child_index, VERSION_ID_ROLE)
                if child_version_id is not None:
                    version_ids.add(child_version_id)
        else:
            version_id = model.data(idx0, VERSION_ID_ROLE)
            if version_id is not None:
                version_ids.add(version_id)

        if not version_ids:
            return

        action_items = self._controller.get_action_items(
            project_name, version_ids, "version"
        )
        result = show_actions_menu(
            action_items, global_pos, len(version_ids) == 1, self
        )
        action_item, options = result
        if action_item is None or options is None:
            return

        self._controller.trigger_action_item(
            identifier=action_item.identifier,
            project_name=project_name,
            selected_ids=version_ids,
            selected_entity_type="version",
            data=action_item.data,
            options=options,
            form_values={},
        )

    def _products_drag_pixmap_context(self):
        """Context for composite drag pixmap (thumb path + labels)."""
        result = self._get_products_drag_data()
        if not result:
            return None
        project_name, version_ids, _ = result
        selection_model = self._products_view.selectionModel()
        model = self._products_proxy_model
        col0 = [
            i
            for i in selection_model.selectedIndexes()
            if i.column() == 0
        ]
        ix = col0[0] if col0 else None
        product_label = ""
        version_label = ""
        first_vid = None
        if ix is not None and ix.isValid():
            product_label = str(
                model.data(ix, PRODUCT_NAME_ROLE)
                or model.data(ix, QtCore.Qt.DisplayRole)
                or ""
            )
            raw_ver = model.data(ix, VERSION_NAME_ROLE)
            if isinstance(raw_ver, numbers.Integral):
                version_label = format_version(
                    raw_ver,
                    version_padding=self._controller.get_version_padding(
                        project_name
                    ),
                )
            else:
                version_label = str(raw_ver or "")
            first_vid = model.data(ix, VERSION_ID_ROLE)
        thumb_path = None
        if version_ids:
            paths = self._controller.get_thumbnail_paths(
                project_name, "version", set(version_ids)
            )
            if paths:
                vid_for_thumb = (
                    first_vid if first_vid and first_vid in paths else None
                )
                if vid_for_thumb is None:
                    vid_for_thumb = sorted(version_ids)[0]
                thumb_path = paths.get(vid_for_thumb)
        return {
            "thumbnail_path": thumb_path,
            "product_label": product_label,
            "version_label": version_label,
            "count": len(version_ids),
        }

    def _get_products_drag_data(self):
        """Return (project_name, version_ids, 'version') for current selection, or None."""
        selection_model = self._products_view.selectionModel()
        model = self._products_view.model()
        project_name = self._products_model.get_last_project_name()
        if not project_name:
            return None
        selected_indexes = [
            idx
            for idx in selection_model.selectedIndexes()
            if idx.column() == 0
        ]
        if not selected_indexes:
            return None
        version_ids = collect_version_ids_from_column0_indexes(
            model, selected_indexes
        )
        if not version_ids:
            return None
        return (project_name, version_ids, "version")

    def _on_context_menu(self, point):
        result = self._get_products_drag_data()
        if not result:
            return
        project_name, version_ids, _ = result

        action_items = self._controller.get_action_items(
            project_name, version_ids, "version"
        )

        # Prepare global point where to show the menu
        global_point = self._products_view.viewport().mapToGlobal(point)

        result = show_actions_menu(
            action_items, global_point, len(version_ids) == 1, self
        )
        action_item, options = result
        if action_item is None or options is None:
            return

        self._controller.trigger_action_item(
            identifier=action_item.identifier,
            project_name=project_name,
            selected_ids=version_ids,
            selected_entity_type="version",
            data=action_item.data,
            options=options,
            form_values={},
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
                selected_versions_info.append(
                    {
                        "folder_id": model.data(index, FOLDER_ID_ROLE),
                        "product_id": product_id,
                        "version_id": version_id,
                        "thumbnail_id": thumbnail_id,
                    }
                )
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
            item_data = {"color": hex_color, "folder_ids": item_folder_ids}
            selected_merged_products.append(item_data)

        prev_selected_merged_products = self._selected_merged_products
        self._selected_merged_products = selected_merged_products
        self._selected_versions_info = selected_versions_info

        project_name = self._products_model.get_last_project_name()
        if project_name and selected_version_ids:
            self._drag_precache.pre_build(
                self._controller,
                project_name,
                selected_version_ids,
                "version",
            )

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
        sitesync_enabled = self._controller.is_sitesync_enabled(project_name)
        self._set_sitesync_visibility(sitesync_enabled)
        self._selected_project_name = project_name
        self._selected_folder_ids = event["folder_ids"]
        self._refresh_model()
        self._update_folders_label_visible()

    def _update_folders_label_visible(self):
        folders_label_hidden = len(self._selected_folder_ids) <= 1
        self._products_view.setColumnHidden(
            self._products_model.folders_label_col, folders_label_hidden
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
