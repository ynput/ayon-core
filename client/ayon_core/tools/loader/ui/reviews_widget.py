"""Top-level reviews widget combining the slicer panel and version table."""

from __future__ import annotations

from typing import Any

from ayon_ui_qt.components.container import AYContainer
from ayon_ui_qt.components.tree_model import LazyTreeModel
from qtpy import QtCore, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.loader.ui.actions_utils import show_actions_menu
from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.loader.ui.review_types import ReviewCategory
from ayon_core.tools.utils.user_prefs import UserPreferences

from ._review_slicer import ReviewSlicer
from ._review_table import ReviewTable

log = Logger.get_logger(__name__)


class ReviewsWidget(AYContainer):
    """Top-level widget combining the slicer panel and version table."""

    def __init__(
        self,
        *args: Any,
        loader_controller: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            **kwargs,
        )
        prefs = UserPreferences()
        saved_project = prefs.get("loader.review.last_project", "")
        saved_category = prefs.get(
            "loader.review.last_category",
            ReviewCategory.HIERARCHY.value,
        )

        self._controller = ReviewController(
            parent=self, loader_controller=loader_controller
        )
        self._slicer = ReviewSlicer(
            self._controller,
            self,
            initial_project=saved_project,
            initial_category=saved_category,
        )
        self._model = LazyTreeModel(
            fetch_children=self._controller.fetch_children
        )
        self._slicer.set_model(self._model)
        self._table = ReviewTable(self._controller, self)
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
        self._build()

        self._slicer._selector.currentTextChanged.connect(
            self._controller.set_project
        )
        self._controller.tree_reset_requested.connect(self._on_tree_reset)
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.selection_changed.connect(self._on_folder_selected)
        self._controller.category_changed.connect(
            self._table.on_category_changed
        )
        self._controller.project_info_changed.connect(
            self._table.on_project_info_changed
        )

        initial_project = self._slicer.current_project()
        if initial_project:
            self._controller.set_project(initial_project)
        initial_category = self._slicer.current_category()
        if initial_category:
            self._controller.set_category(initial_category)

    def _build(self) -> None:
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._slicer)
        main_splitter.addWidget(self._table)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 6)
        self.add_widget(main_splitter)

    def _on_tree_reset(self) -> None:
        """Reset the tree model and re-attach it to the slicer."""
        self._model.reset()
        self._slicer.set_model(self._model)

    def _on_project_changed(self, project_name: str) -> None:
        """Clear selection state and refresh table on project change.

        Args:
            project_name: Newly selected project name.
        """
        self._table.set_auto_expand(False)
        self._table.reset_data()

    def _on_folder_selected(self, ids: list[str], names: list[str]) -> None:
        """Refresh the version table when folders are selected or cleared.

        In tree mode, selecting one or more folders makes those folders
        the root rows of the table and enables auto-expansion so that
        the full sub-tree is shown immediately.

        Args:
            ids: IDs of the selected folders, or empty when deselected.
            names: Names of the selected folders (parallel to *ids*).
        """
        auto_expand = bool(ids) and self._controller.tree_mode
        self._table.set_auto_expand(auto_expand)
        self._table.reset_data()
        self._table.refresh_filter()

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show a contextual actions menu for the selected rows.

        Collects version IDs from the current table selection, queries
        the loader controller for applicable action items and presents
        them via :func:`show_actions_menu`.

        Args:
            pos: Cursor position in viewport coordinates.
        """
        project_name = self._controller.current_project
        selection_model = self._table.active_view.selectionModel()

        version_ids: set[str] = set()
        for proxy_idx in selection_model.selectedIndexes():
            if proxy_idx.column() != 0:
                continue
            row_dict = proxy_idx.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            if row_dict.get("entityType", "") == "Folder":
                continue
            version_id = row_dict.get("_version_id", row_dict.get("id", ""))
            if version_id:
                version_ids.add(version_id)

        global_point = self._table.active_view.viewport().mapToGlobal(pos)

        if not version_ids or not project_name:
            log.warning("No version ids or project name")
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
