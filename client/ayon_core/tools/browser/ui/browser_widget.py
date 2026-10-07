"""Top-level reviews widget combining the slicer panel and version table."""

from __future__ import annotations

from typing import Any

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.actions_utils import show_actions_menu
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.control import BrowserController

from ._browser_slicer import BrowserSlicer
from ._browser_table import BrowserTable
from .browser_inspector import ReviewInspector
from .product_group_dialog import ProductGroupDialog

log = Logger.get_logger(__name__)


class BrowserWidget(AYContainer):
    """Top-level widget combining the slicer panel and version table."""

    default_view_message = QtCore.Signal(str, bool)

    # Max selected versions for which context menu data are prefetched
    prefetch_selection_limit = 50

    def __init__(
        self,
        browser_controller: BrowserController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_margin=0,
            layout_spacing=4,
            **kwargs,
        )
        self._controller = BrowserWidgetController(
            browser_controller,
            parent=self,
        )
        self._slicer = BrowserSlicer(
            self._controller,
            browser_controller,
            self,
        )
        self._table = BrowserTable(self._controller, self)
        self._table.table.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.table.customContextMenuRequested.connect(
            self._on_context_menu
        )
        self._table.card_view.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.card_view.customContextMenuRequested.connect(
            self._on_context_menu
        )
        self._prefetch_context_id = f"browser_prefetch_{id(self)}"
        for view in (self._table.table, self._table.card_view):
            view.selection_changed.connect(self._on_view_selection_changed)
        self._inspector = ReviewInspector(self._controller)
        self._table.display_type_changed.connect(self._inspector.set_view)
        self._table.default_view_message.connect(
            self.default_view_message
        )
        self._inspector.set_view(self._table.active_view)
        self._build()

        # Grouping products on pressing Ctrl + G
        self._group_dialog = ProductGroupDialog(self._controller, self)
        self._controller.products_group_changed.connect(
            self._on_product_group_changed
        )
        self._group_dialog.group_change_failed.connect(
            self._on_product_group_change_failed
        )
        group_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+G"), self
        )
        group_shortcut.setContext(
            QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut
        )
        group_shortcut.setAutoRepeat(False)
        group_shortcut.activated.connect(self._show_group_dialog)
        self._group_shortcut = group_shortcut

        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.selection_changed.connect(self._on_folder_selected)
        self._controller.category_changed.connect(
            self._table.on_category_changed
        )
        self._controller.project_info_changed.connect(
            self._table.on_project_info_changed
        )
        self._slicer.task_names_changed.connect(
            self._on_task_names_changed
        )
        self._table.filter_criteria_changed.connect(
            self._on_filter_criteria_changed
        )

    def _build(self) -> None:
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._slicer)
        main_splitter.addWidget(self._table)
        main_splitter.addWidget(self._inspector)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 6)
        main_splitter.setStretchFactor(2, 2)
        self.add_widget(main_splitter)

    def refresh_loaded_state(self) -> None:
        """Refresh rows that depend on the host's loaded containers.

        A Load action never changes which rows the server would return,
        only how already-loaded ones should display (and, if an In
        Scene filter is active, which of them stay visible) - so this
        re-enriches and repaints in place rather than resetting the
        table.
        """
        self._table.refresh_column_provider_data()

    def _on_project_changed(self, project_name: str) -> None:
        """Clear selection state and refresh table on project change.

        Args:
            project_name: Newly selected project name.
        """
        self._table.set_auto_expand(False)
        self._table.clear_expansion_state()
        self._table.reset_data()
        self._slicer.set_task_names([])
        # Discover action plugins before the first context menu, deferred
        #   to not block the project change. Plugins may use host APIs so
        #   it must run in the main thread.
        QtCore.QTimer.singleShot(0, self._warm_up_action_items)

    def _on_task_names_changed(self, names: list[str]) -> None:
        """Apply task-list selection to the table's Task criterion."""
        self._table.set_task_filter_names(names)

    def select_current_context(self) -> None:
        """Navigate the Browser slicer to the host's current context."""
        self._slicer.select_current_context()

    def select_current_context_if_empty(self) -> None:
        """Use the host context when Browser has no existing selection."""
        if self._controller.current_project or self._controller.has_selection:
            return
        self.select_current_context()

    def _on_filter_criteria_changed(self, criteria: list[Any]) -> None:
        """Reflect the filter bar's Task criterion in the task list."""
        names = []
        for criterion in criteria:
            if criterion.key == "task":
                names = criterion.values
                break
        self._slicer.set_task_names(names)

    def _on_folder_selected(self, ids: list[str]) -> None:
        """Refresh the version table when folders are selected or cleared.

        In tree mode, selecting one or more folders makes those folders
        the root rows of the table and enables auto-expansion so that
        the full sub-tree is shown immediately.

        Args:
            ids: IDs of the selected folders, or empty when deselected.
            names: Names of the selected folders (parallel to *ids*).
        """
        # Group headers stay collapsed so versions are fetched on demand,
        # matching the frontend's grouped-table behavior.
        auto_expand = (
            bool(ids)
            and self._controller.tree_mode
            and self._controller.group_by_key == "none"
        )
        self._table.set_auto_expand(auto_expand)
        self._table.reset_data()

    def _get_selected_version_ids(self) -> set[str]:
        """Return version IDs of the rows selected in the active view."""
        selection_model = self._table.active_view.selectionModel()
        version_ids: set[str] = set()
        for proxy_idx in selection_model.selectedIndexes():
            if proxy_idx.column() != 0:
                continue
            row_dict = proxy_idx.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            if row_dict.get("entityType", "") == "Folder":
                continue
            version_id = row_dict.get("_version_id") or row_dict.get("id", "")
            if version_id and not version_id.startswith("grp:"):
                version_ids.add(version_id)
        return version_ids

    def _get_selected_product_ids(self) -> set[str]:
        """Return product IDs of the rows selected in the active view.

        Covers version rows and the group headers of the Product
        group-by, other group headers and folders have no product.
        """
        selection_model = self._table.active_view.selectionModel()
        product_ids: set[str] = set()
        for proxy_idx in selection_model.selectedIndexes():
            if proxy_idx.column() != 0:
                continue
            row_dict = proxy_idx.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            product_id = (
                row_dict.get("_product_id") or row_dict.get("productId")
            )
            if product_id:
                product_ids.add(product_id)
        return product_ids

    def _show_group_dialog(self) -> None:
        """Ask for a product group to set on the selected products."""
        project_name = self._controller.current_project
        product_ids = self._get_selected_product_ids()
        if not project_name or not product_ids:
            return

        try:
            if not self._controller.can_change_products_group(project_name):
                self.default_view_message.emit(
                    "You don't have permissions to set"
                    " the product group attribute",
                    False,
                )
                return
            self._group_dialog.set_product_ids(project_name, product_ids)
        except Exception:
            log.warning("Failed to query product groups", exc_info=True)
            self.default_view_message.emit(
                "Failed to query product groups", False
            )
            return
        self._group_dialog.show()

    def _on_product_group_changed(self) -> None:
        self._table.reset_data()

    def _on_product_group_change_failed(self, message: str) -> None:
        log.warning(message)
        self.default_view_message.emit(message, False)

    def _on_view_selection_changed(self, *args: Any) -> None:
        """Prefetch context menu data for the new selection.

        A right-click selects the row on mouse press but the context menu
        is requested on release, so the data is usually ready in time.
        """
        project_name = self._controller.current_project
        version_ids = self._get_selected_version_ids()
        task_queue = get_task_queue()
        # Only the latest selection is relevant
        task_queue.clear_context_tasks(self._prefetch_context_id)
        # Don't query large selections that may never get a context menu
        if (
            not project_name
            or not version_ids
            or len(version_ids) > self.prefetch_selection_limit
        ):
            return

        controller = self._controller
        task_queue.enqueue(
            AsyncTask(
                name="browser_prefetch_action_contexts",
                function=lambda: (
                    controller.prefetch_version_action_contexts(
                        project_name, version_ids
                    )
                ),
                callback=lambda _result: None,
                priority=1,
                context_id=self._prefetch_context_id,
            )
        )

    def _warm_up_action_items(self) -> None:
        project_name = self._controller.current_project
        if project_name:
            self._controller.warm_up_action_items(project_name)

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show a contextual actions menu for the selected rows.

        Collects version IDs from the current table selection, queries
        the loader controller for applicable action items and presents
        them via :func:`show_actions_menu`.

        Args:
            pos: Cursor position in viewport coordinates.
        """
        project_name = self._controller.current_project
        version_ids = self._get_selected_version_ids()

        global_point = self._table.active_view.viewport().mapToGlobal(pos)

        if not version_ids or not project_name:
            log.debug("No version ids or project name")
            return

        action_items = self._controller.get_action_items(
            project_name, version_ids, "version"
        )

        if not action_items:
            log.warning("No action items available")
            return

        result = show_actions_menu(
            action_items,
            global_point,
            len(version_ids) == 1,
            self,
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
