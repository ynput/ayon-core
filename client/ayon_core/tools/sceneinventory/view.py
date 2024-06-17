import collections
import logging
from functools import partial

from qtpy import QtWidgets, QtCore
import qtawesome

from ayon_core import style
from ayon_core.pipeline import (
    HeroVersionType,
    update_container,
    remove_container,
    discover_inventory_actions,
)
from ayon_core.tools.utils.lib import (
    iter_model_rows,
    format_version,
    preserve_expanded_rows,
    preserve_selection,
)
from ayon_core.tools.utils.delegates import StatusDelegate

from .switch_dialog import SwitchAssetDialog
from .model import (
    InventoryModel,
    FilterProxyModel,
    ITEM_UNIQUE_NAME_ROLE,
    OBJECT_NAME_ROLE,
    ITEM_ID_ROLE,
    IS_CONTAINER_ITEM_ROLE,
    STATUS_NAME_ROLE,
    STATUS_SHORT_ROLE,
    STATUS_COLOR_ROLE,
    STATUS_ICON_ROLE,
)
from .delegates import VersionDelegate
from .select_version_dialog import SelectVersionDialog, VersionOption

DEFAULT_COLOR = "#fb9c15"

log = logging.getLogger("SceneInventory")


class SceneInventoryView(QtWidgets.QTreeView):
    data_changed = QtCore.Signal()
    hierarchy_view_changed = QtCore.Signal(bool)

    def __init__(self, controller, parent):
        super(SceneInventoryView, self).__init__(parent=parent)

        # view settings
        self.setIndentation(12)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        model = InventoryModel(controller)
        proxy_model = FilterProxyModel()
        proxy_model.setSourceModel(model)
        proxy_model.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

        self.setModel(proxy_model)

        version_delegate = VersionDelegate()
        status_delegate = StatusDelegate(
            STATUS_NAME_ROLE,
            STATUS_SHORT_ROLE,
            STATUS_COLOR_ROLE,
            STATUS_ICON_ROLE,
        )
        for col, delegate in (
            (model.version_col, version_delegate),
            (model.status_col, status_delegate),
        ):
            self.setItemDelegateForColumn(col, delegate)

        # set some nice default widths for the view
        for col, width in model.width_by_column.items():
            self.setColumnWidth(col, width)

        sync_enabled = controller.is_sitesync_enabled()
        self.setColumnHidden(model.active_site_col, not sync_enabled)
        self.setColumnHidden(model.remote_site_col, not sync_enabled)

        self.customContextMenuRequested.connect(self._show_right_mouse_menu)

        self._model = model
        self._proxy_model = proxy_model
        self._version_delegate = version_delegate
        self._status_delegate = status_delegate

        self._hierarchy_view = False
        self._selected = None

        self._controller = controller

    def refresh(self):
        with preserve_expanded_rows(
            tree_view=self,
            role=ITEM_UNIQUE_NAME_ROLE
        ):
            with preserve_selection(
                tree_view=self,
                role=ITEM_UNIQUE_NAME_ROLE,
                current_index=False
            ):
                kwargs = {}
                # TODO do not touch view's inner attribute
                if self._hierarchy_view:
                    kwargs["selected"] = self._selected
                self._model.refresh(**kwargs)

    def set_hierarchy_view(self, enabled):
        self._proxy_model.set_hierarchy_view(enabled)
        self._model.set_hierarchy_view(enabled)

    def set_text_filter(self, text_filter):
        if hasattr(self._proxy_model, "setFilterRegularExpression"):
            self._proxy_model.setFilterRegularExpression(text_filter)
        else:
            self._proxy_model.setFilterRegExp(text_filter)

    def set_filter_outdated(self, enabled):
        self._proxy_model.set_filter_outdated(enabled)

    def get_selected_indexes(self):
        """Get the selected rows"""
        indexes, _ = self._get_selected_indexes()
        return indexes

    def get_selected_item_ids(self):
        return self._get_item_ids_from_indexes(
            self.get_selected_indexes()
        )

    def get_selected_container_indexes(self):
        return self._get_container_indexes(
            self.get_selected_indexes()
        )

    def _get_selected_indexes(self):
        selection_model = self.selectionModel()
        indexes = selection_model.selectedRows()
        active = self.currentIndex()
        active = active.sibling(active.row(), 0)
        if active not in indexes:
            indexes.append(active)
        return indexes, active

    def _get_item_ids_from_indexes(self, indexes):
        return {
            index.data(ITEM_ID_ROLE)
            for index in self._get_container_indexes(indexes)
        }

    def _set_hierarchy_view(self, enabled):
        if enabled == self._hierarchy_view:
            return
        self._hierarchy_view = enabled
        self.hierarchy_view_changed.emit(enabled)

    def _enter_hierarchy(self, item_ids):
        self._selected = set(item_ids)
        self._set_hierarchy_view(True)
        self.data_changed.emit()
        self.expandToDepth(1)
        self.setStyleSheet("border-color: #fb9c15;")

    def _leave_hierarchy(self):
        self._set_hierarchy_view(False)
        self.data_changed.emit()
        self.setStyleSheet("")

    def _build_item_menu_for_selection(self, menu, indexes, active_index):
        item_ids = {
            index.data(ITEM_ID_ROLE)
            for index in indexes
        }
        item_ids.discard(None)
        if not item_ids:
            return

        container_items_by_id = self._controller.get_container_items_by_id(
            item_ids
        )

        active_repre_id = None
        if active_index is not None:
            for index in self._get_container_indexes({active_index}):
                item_id = index.data(ITEM_ID_ROLE)
                container_item = container_items_by_id[item_id]
                active_repre_id = container_item.representation_id
                break

        repre_info_by_id = self._controller.get_representation_info_items({
            container_item.representation_id
            for container_item in container_items_by_id.values()
        })
        valid_repre_ids = {
            repre_id
            for repre_id, repre_info in repre_info_by_id.items()
            if repre_info.is_valid
        }

        # Exclude items that are "NOT FOUND" since setting versions, updating
        # and removal won't work for those items.
        filtered_items = []
        product_ids = set()
        version_ids = set()
        for container_item in container_items_by_id.values():
            repre_id = container_item.representation_id
            repre_info = repre_info_by_id.get(repre_id)
            if repre_info and repre_info.is_valid:
                filtered_items.append(container_item)
                version_ids.add(repre_info.version_id)
                product_ids.add(repre_info.product_id)

        # remove
        remove_icon = qtawesome.icon("fa.remove", color=DEFAULT_COLOR)
        remove_action = QtWidgets.QAction(remove_icon, "Remove items", menu)
        remove_action.triggered.connect(
            lambda: self._show_remove_warning_dialog(item_ids))

        if not filtered_items:
            # Keep remove action for invalid items
            menu.addAction(remove_action)
            return

        version_items_by_product_id = self._controller.get_version_items(
            product_ids
        )
        has_outdated = False
        has_loaded_hero_versions = False
        has_available_hero_version = False
        for version_items_by_id in version_items_by_product_id.values():
            for version_item in version_items_by_id.values():
                if version_item.is_hero:
                    has_available_hero_version = True

                if version_item.version_id not in version_ids:
                    continue
                if version_item.is_hero:
                    has_loaded_hero_versions = True

                elif not version_item.is_latest:
                    has_outdated = True

        switch_to_versioned = None
        if has_loaded_hero_versions:
            update_icon = qtawesome.icon(
                "fa.asterisk",
                color=DEFAULT_COLOR
            )
            switch_to_versioned = QtWidgets.QAction(
                update_icon,
                "Switch to versioned",
                menu
            )
            switch_to_versioned.triggered.connect(
                lambda: self._on_switch_to_versioned(item_ids)
            )

        update_to_latest_action = None
        if has_outdated or has_loaded_hero_versions:
            update_icon = qtawesome.icon(
                "fa.angle-double-up",
                color=DEFAULT_COLOR
            )
            update_to_latest_action = QtWidgets.QAction(
                update_icon,
                "Update to latest",
                menu
            )
            update_to_latest_action.triggered.connect(
                lambda: self._update_containers_to_version(
                    item_ids, version=-1
                )
            )

        change_to_hero = None
        if has_available_hero_version:
            # TODO change icon
            change_icon = qtawesome.icon(
                "fa.asterisk",
                color="#00b359"
            )
            change_to_hero = QtWidgets.QAction(
                change_icon,
                "Change to hero",
                menu
            )
            change_to_hero.triggered.connect(
                lambda: self._update_containers_to_version(
                    item_ids, version=HeroVersionType(-1)
                )
            )

        # set version
        set_version_action = None
        if active_repre_id is not None:
            set_version_icon = qtawesome.icon("fa.hashtag", color=DEFAULT_COLOR)
            set_version_action = QtWidgets.QAction(
                set_version_icon,
                "Set version",
                menu
            )
            set_version_action.triggered.connect(
                lambda: self._show_version_dialog(item_ids, active_repre_id)
            )

        # switch folder
        switch_folder_icon = qtawesome.icon("fa.sitemap", color=DEFAULT_COLOR)
        switch_folder_action = QtWidgets.QAction(
            switch_folder_icon,
            "Switch Folder",
            menu
        )
        switch_folder_action.triggered.connect(
            lambda: self._show_switch_dialog(item_ids))

        # add the actions
        if switch_to_versioned:
            menu.addAction(switch_to_versioned)

        if update_to_latest_action:
            menu.addAction(update_to_latest_action)

        if change_to_hero:
            menu.addAction(change_to_hero)

        if set_version_action is not None:
            menu.addAction(set_version_action)
        menu.addAction(switch_folder_action)

        menu.addSeparator()

        menu.addAction(remove_action)

        self._handle_sitesync(menu, valid_repre_ids)

    def _handle_sitesync(self, menu, repre_ids):
        """Adds actions for download/upload when SyncServer is enabled

        Args:
            menu (OptionMenu)
            repre_ids (list) of object_ids

        Returns:
            (OptionMenu)
        """

        if not self._controller.is_sitesync_enabled():
            return

        if not repre_ids:
            return

        menu.addSeparator()

        download_icon = qtawesome.icon("fa.download", color=DEFAULT_COLOR)
        download_active_action = QtWidgets.QAction(
            download_icon,
            "Download",
            menu
        )
        download_active_action.triggered.connect(
            lambda: self._add_sites(repre_ids, "active_site"))

        upload_icon = qtawesome.icon("fa.upload", color=DEFAULT_COLOR)
        upload_remote_action = QtWidgets.QAction(
            upload_icon,
            "Upload",
            menu
        )
        upload_remote_action.triggered.connect(
            lambda: self._add_sites(repre_ids, "remote_site"))

        menu.addAction(download_active_action)
        menu.addAction(upload_remote_action)

    def _add_sites(self, repre_ids, site_type):
        """(Re)sync all 'repre_ids' to specific site.

        It checks if opposite site has fully available content to limit
        accidents. (ReSync active when no remote >> losing active content)

        Args:
            repre_ids (list)
            site_type (Literal[active_site, remote_site]): Site type.
        """

        self._controller.resync_representations(repre_ids, site_type)

        self.data_changed.emit()

    def _build_item_menu(self, indexes=None, active_index=None):
        """Create menu for the selected items"""
        menu = QtWidgets.QMenu(self)

        # These two actions should be able to work without selection
        # expand all items
        expand_all_action = QtWidgets.QAction(menu, text="Expand all items")
        expand_all_action.triggered.connect(self.expandAll)

        # collapse all items
        collapse_action = QtWidgets.QAction(menu, text="Collapse all items")
        collapse_action.triggered.connect(self.collapseAll)

        if not indexes:
            indexes = []

        item_ids = {
            index.data(ITEM_ID_ROLE)
            for index in indexes
        }
        item_ids.discard(None)

        # add the actions
        self._build_item_menu_for_selection(menu, indexes, active_index)

        menu.addAction(expand_all_action)
        menu.addAction(collapse_action)

        custom_actions = self._get_custom_actions(item_ids)
        if custom_actions:
            submenu = QtWidgets.QMenu("Actions", self)
            for action in custom_actions:
                color = action.color or DEFAULT_COLOR
                icon = qtawesome.icon("fa.%s" % action.icon, color=color)
                action_item = QtWidgets.QAction(icon, action.label, submenu)
                action_item.triggered.connect(
                    partial(
                        self._process_custom_action, action, item_ids
                    )
                )

                submenu.addAction(action_item)

            menu.addMenu(submenu)

        # go back to flat view
        back_to_flat_action = None
        if self._hierarchy_view:
            back_to_flat_icon = qtawesome.icon("fa.list", color=DEFAULT_COLOR)
            back_to_flat_action = QtWidgets.QAction(
                back_to_flat_icon,
                "Back to Full-View",
                menu
            )
            back_to_flat_action.triggered.connect(self._leave_hierarchy)

        # send items to hierarchy view
        enter_hierarchy_icon = qtawesome.icon("fa.indent", color="#d8d8d8")
        enter_hierarchy_action = QtWidgets.QAction(
            enter_hierarchy_icon,
            "Cherry-Pick (Hierarchy)",
            menu
        )
        enter_hierarchy_action.triggered.connect(
            lambda: self._enter_hierarchy(item_ids))

        if indexes:
            menu.addAction(enter_hierarchy_action)

        if back_to_flat_action is not None:
            menu.addAction(back_to_flat_action)

        return menu

    def _get_custom_actions(self, item_ids):
        """Get the registered Inventory Actions

        Args:
            item_ids (Iterable[str]): collection of containers

        Returns:
            list: collection of filter and initialized actions
        """

        def sorter(Plugin):
            """Sort based on order attribute of the plugin"""
            return Plugin.order

        # Fedd an empty dict if no selection, this will ensure the compat
        # lookup always work, so plugin can interact with Scene Inventory
        # reversely.
        if not item_ids:
            containers = [dict()]
        else:
            containers_by_id = self._controller.get_containers_by_item_ids(
                item_ids
            )
            containers = list(containers_by_id.values())

        # Check which action will be available in the menu
        Plugins = discover_inventory_actions()
        compatible = [
            p()
            for p in Plugins
            if any(p.is_compatible(c) for c in containers)
        ]

        return sorted(compatible, key=sorter)

    def _process_custom_action(self, action, item_ids):
        """Run action and if results are returned positive update the view

        If the result is list or dict, will select view items by the result.

        Args:
            action (InventoryAction): Inventory Action instance
            item_ids (Iterable[str]): Data of currently selected items

        Returns:
            None
        """
        containers_by_id = self._controller.get_containers_by_item_ids(
            item_ids
        )
        result = action.process(list(containers_by_id.values()))
        if result:
            self.data_changed.emit()

            if isinstance(result, (list, set)):
                self._select_items_by_action(result)

            if isinstance(result, dict):
                self._select_items_by_action(
                    result["objectNames"], result["options"]
                )

    def _select_items_by_action(self, object_names, options=None):
        """Select view items by the result of action

        Args:
            object_names (list or set): A list/set of container object name
            options (dict): GUI operation options.

        Returns:
            None

        """
        options = options or dict()

        if options.get("clear", True):
            self.clearSelection()

        model = self.model()
        object_names = set(object_names)
        if self._hierarchy_view:
            item_ids = set()
            for index in iter_model_rows(model):
                if not index.data(IS_CONTAINER_ITEM_ROLE):
                    continue
                if index.data(OBJECT_NAME_ROLE) in object_names:
                    item_id = index.data(ITEM_ID_ROLE)
                    if item_id:
                        item_ids.add(item_id)

            if not self._selected.issuperset(item_ids):
                # If any container not in current cherry-picked view, update
                # view before selecting them.
                self._selected.update(item_ids)
                self.data_changed.emit()

        selection_model = self.selectionModel()

        select_mode = {
            "select": QtCore.QItemSelectionModel.Select,
            "deselect": QtCore.QItemSelectionModel.Deselect,
            "toggle": QtCore.QItemSelectionModel.Toggle,
        }[options.get("mode", "select")]

        for index in iter_model_rows(model):
            if not index.data(IS_CONTAINER_ITEM_ROLE):
                continue
            name = index.data(OBJECT_NAME_ROLE)
            if name in object_names:
                self.scrollTo(index)  # Ensure item is visible
                flags = select_mode | QtCore.QItemSelectionModel.Rows
                selection_model.select(index, flags)

                object_names.remove(name)

            if len(object_names) == 0:
                break

    def _show_right_mouse_menu(self, pos):
        """Display the menu when at the position of the item clicked"""

        globalpos = self.viewport().mapToGlobal(pos)

        if not self.selectionModel().hasSelection():
            # Build menu without selection, feed an empty list
            menu = self._build_item_menu()
            menu.exec_(globalpos)
            return

        indexes, active_index = self._get_selected_indexes()

        # Extend to the sub-items
        all_indexes = self._extend_to_children(indexes)

        menu = self._build_item_menu(all_indexes, active_index)
        menu.exec_(globalpos)

    def _get_container_indexes(self, indexes):
        container_indexes = []
        indexes_queue = collections.deque()
        indexes_queue.extend(indexes)
        # Ignore already added containers
        items_ids = set()
        while indexes_queue:
            index = indexes_queue.popleft()
            if index.data(IS_CONTAINER_ITEM_ROLE):
                item_id = index.data(ITEM_ID_ROLE)
                if item_id in items_ids:
                    continue
                items_ids.add(item_id)
                container_indexes.append(index)
                continue
            model = index.model()
            for row in range(model.rowCount(index)):
                child = model.index(row, 0, parent=index)
                indexes_queue.append(child)
        return container_indexes

    def _extend_to_children(self, indexes):
        """Extend the indices to the children indices.

        Top-level indices are extended to its children indices. Sub-items
        are kept as is.

        Args:
            indexes (list): The indices to extend.

        Returns:
            list: The children indices

        """
        def get_children(index):
            model = index.model()
            for row in range(model.rowCount(index)):
                yield model.index(row, 0, parent=index)

        subitems = set()
        for index in indexes:
            if index.parent().isValid() and index not in subitems:
                subitems.add(index)

                if self._hierarchy_view:
                    # Assume this is a group item
                    for child in get_children(index):
                        subitems.add(child)
            else:
                # is top level item
                for child in get_children(index):
                    subitems.add(child)

        return list(subitems)

    def _show_version_dialog(self, item_ids, active_repre_id):
        """Create a dialog with the available versions for the selected file

        Args:
            item_ids (Iterable[str]): List of item ids to run the
                "set_version" for.
            active_repre_id (Union[str, None]): Active representation id.

        Returns:
            None

        """
        container_items_by_id = self._controller.get_container_items_by_id(
            item_ids
        )
        repre_ids = {
            container_item.representation_id
            for container_item in container_items_by_id.values()
        }
        repre_info_by_id = self._controller.get_representation_info_items(
            repre_ids
        )

        product_ids = {
            repre_info.product_id
            for repre_info in repre_info_by_id.values()
        }
        active_repre_info = repre_info_by_id[active_repre_id]
        active_version_id = active_repre_info.version_id
        active_product_id = active_repre_info.product_id
        version_items_by_product_id = self._controller.get_version_items(
            product_ids
        )
        version_items = list(
            version_items_by_product_id[active_product_id].values()
        )
        versions = {version_item.version for version_item in version_items}
        product_ids_by_version = collections.defaultdict(set)
        for version_items_by_id in version_items_by_product_id.values():
            for version_item in version_items_by_id.values():
                version = version_item.version
                _prod_version = version
                if _prod_version < 0:
                    _prod_version = -1
                product_ids_by_version[_prod_version].add(
                    version_item.product_id
                )
                if version in versions:
                    continue
                versions.add(version)
                version_items.append(version_item)

        def version_sorter(item):
            hero_value = 0
            i_version = item.version
            if i_version < 0:
                hero_value = 1
                i_version = abs(i_version)
            return i_version, hero_value

        version_items.sort(key=version_sorter, reverse=True)
        show_statuses = len(product_ids) == 1
        status_items_by_name = {}
        if show_statuses:
            status_items_by_name = {
                status_item.name: status_item
                for status_item in self._controller.get_project_status_items()
            }

        version_options = []
        active_version_idx = 0
        for idx, version_item in enumerate(version_items):
            version = version_item.version
            label = format_version(version)
            if version_item.version_id == active_version_id:
                active_version_idx = idx

            status_name = version_item.status
            status_short = None
            status_color = None
            status_icon = None
            status_item = status_items_by_name.get(status_name)
            if status_item:
                status_short = status_item.short
                status_color = status_item.color
                status_icon = status_item.icon
            version_options.append(
                VersionOption(
                    version,
                    label,
                    status_name,
                    status_short,
                    status_color,
                    status_icon,
                )
            )

        version_option = SelectVersionDialog.ask_for_version(
            version_options,
            active_version_idx,
            show_statuses=show_statuses,
            parent=self
        )
        if version_option is None:
            return

        product_version = version = version_option.version
        if version < 0:
            product_version = -1
            version = HeroVersionType(version)

        product_ids = product_ids_by_version[product_version]

        filtered_item_ids = set()
        for container_item in container_items_by_id.values():
            repre_id = container_item.representation_id
            repre_info = repre_info_by_id[repre_id]
            if repre_info.product_id in product_ids:
                filtered_item_ids.add(container_item.item_id)

        self._update_containers_to_version(
            filtered_item_ids, version
        )

    def _show_switch_dialog(self, item_ids):
        """Display Switch dialog"""
        containers_by_id = self._controller.get_containers_by_item_ids(
            item_ids
        )
        dialog = SwitchAssetDialog(
            self._controller, self, list(containers_by_id.values())
        )
        dialog.switched.connect(self.data_changed.emit)
        dialog.show()

    def _show_remove_warning_dialog(self, item_ids):
        """Prompt a dialog to inform the user the action will remove items"""
        containers_by_id = self._controller.get_containers_by_item_ids(
            item_ids
        )
        containers = list(containers_by_id.values())
        accept = QtWidgets.QMessageBox.Ok
        buttons = accept | QtWidgets.QMessageBox.Cancel

        state = QtWidgets.QMessageBox.question(
            self,
            "Are you sure?",
            f"Are you sure you want to remove {len(containers)} item(s)",
            buttons=buttons,
            defaultButton=accept
        )

        if state != accept:
            return

        for container in containers:
            remove_container(container)
        self.data_changed.emit()

    def _show_version_error_dialog(self, version, item_ids):
        """Shows QMessageBox when version switch doesn't work

        Args:
            version: str or int or None
        """
        if version == -1:
            version_str = "latest"
        elif isinstance(version, HeroVersionType):
            version_str = "hero"
        elif isinstance(version, int):
            version_str = "v{:03d}".format(version)
        else:
            version_str = version

        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setStyleSheet(style.load_stylesheet())
        dialog.setWindowTitle("Update failed")

        switch_btn = dialog.addButton(
            "Switch Folder",
            QtWidgets.QMessageBox.ActionRole
        )
        switch_btn.clicked.connect(lambda: self._show_switch_dialog(item_ids))

        dialog.addButton(QtWidgets.QMessageBox.Cancel)

        msg = (
            "Version update to '{}' failed as representation doesn't exist."
            "\n\nPlease update to version with a valid representation"
            " OR \n use 'Switch Folder' button to change folder."
        ).format(version_str)
        dialog.setText(msg)
        dialog.exec_()

    def update_all(self):
        """Update all items that are currently 'outdated' in the view"""
        # Get the source model through the proxy model
        item_ids = self._model.get_outdated_item_ids()
        if not item_ids:
            log.info("Nothing to update.")
            return

        # Trigger update to latest
        self._update_containers_to_version(item_ids, version=-1)

    def _on_switch_to_versioned(self, item_ids):
        containers_items_by_id = self._controller.get_container_items_by_id(
            item_ids
        )
        repre_ids = {
            container_item.representation_id
            for container_item in containers_items_by_id.values()
        }
        repre_info_by_id = self._controller.get_representation_info_items(
            repre_ids
        )
        product_ids = {
            repre_info.product_id
            for repre_info in repre_info_by_id.values()
            if repre_info.is_valid
        }
        version_items_by_product_id = self._controller.get_version_items(
            product_ids
        )

        update_containers = []
        update_versions = []
        for item_id, container_item in containers_items_by_id.items():
            repre_id = container_item.representation_id
            repre_info = repre_info_by_id[repre_id]
            product_id = repre_info.product_id
            version_items_id = version_items_by_product_id[product_id]
            version_item = version_items_id.get(repre_info.version_id, {})
            if not version_item or not version_item.is_hero:
                continue
            version = abs(version_item.version)
            version_found = False
            for version_item in version_items_id.values():
                if version_item.is_hero:
                    continue
                if version_item.version == version:
                    version_found = True
                    break

            if not version_found:
                continue

            update_containers.append(container_item.item_id)
            update_versions.append(version)

        # Specify version per item to update to
        self._update_containers(update_containers, update_versions)

    def _update_containers(self, item_ids, versions):
        """Helper to update items to given version (or version per item)

        If at least one item is specified this will always try to refresh
        the inventory even if errors occurred on any of the items.

        Arguments:
            item_ids (Iterable[str]): Items to update
            versions (Iterable[Union[int, HeroVersion]]): Version to set to.
                This can be a list specifying a version for each item.
                Like `update_container` version -1 sets the latest version
                and HeroTypeVersion instances set the hero version.

        """

        # We allow a unique version to be specified per item. In that case
        # the length must match with the items
        assert len(item_ids) == len(versions), (
            "Number of items mismatches number of versions: "
            f"{len(item_ids)} items - {len(versions)} versions"
        )

        # Trigger update to latest
        containers_by_id = self._controller.get_containers_by_item_ids(
            item_ids
        )
        try:
            for item_id, item_version in zip(item_ids, versions):
                container = containers_by_id[item_id]
                try:
                    update_container(container, item_version)
                except AssertionError:
                    log.warning("Update failed", exc_info=True)
                    self._show_version_error_dialog(
                        item_version, [item_id]
                    )
        finally:
            # Always update the scene inventory view, even if errors occurred
            self.data_changed.emit()

    def _update_containers_to_version(self, item_ids, version):
        """Helper to update items to given version (or version per item)

        If at least one item is specified this will always try to refresh
        the inventory even if errors occurred on any of the items.

        Arguments:
            item_ids (Iterable[str]): Items to update
            version (Union[int, HeroVersion]): Version to set to.
                This can be a list specifying a version for each item.
                Like `update_container` version -1 sets the latest version
                and HeroTypeVersion instances set the hero version.

        """
        versions = [version for _ in range(len(item_ids))]
        self._update_containers(item_ids, versions)
