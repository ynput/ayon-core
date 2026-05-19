"""Left-hand slicer panel with project selector, category slicer, and tree."""

from __future__ import annotations

from typing import Any

from ayon_ui_qt.components.container import AYContainer
from ayon_ui_qt.components.slicer import AYSlicer
from ayon_ui_qt.components.task_queue import get_task_queue
from ayon_ui_qt.components.task_queue_monitor import AsyncTaskQueueMonitor
from ayon_ui_qt.components.tree_model import LazyTreeModel
from ayon_ui_qt.components.tree_view import AYTreeView, QItemSelection
from qtpy import QtCore, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.loader.ui.review_types import ReviewCategory

from ._project_selector import ProjectSelector

log = Logger.get_logger(__name__)


class ReviewTreeView(AYTreeView):
    """Tree view used inside the review slicer."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, variant=AYTreeView.Variants.Low)


class ReviewSlicer(AYContainer):
    """Left-hand panel with project selector, category slicer and tree."""

    CATEGORIES = [
        {
            "text": ReviewCategory.HIERARCHY.value,
            "short_text": "HIE",
            "icon": "table_rows",
            "color": "#f4f5f5",
        },
        {
            "text": ReviewCategory.REVIEWS.value,
            "short_text": "REV",
            "icon": "subscriptions",
            "color": "#f4f5f5",
        },
    ]

    def __init__(
        self,
        controller: ReviewController,
        *args: Any,
        initial_project: str = "",
        initial_category: str = ReviewCategory.HIERARCHY.value,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_margin=8,
            layout_spacing=4,
            **kwargs,
        )
        self.setMinimumWidth(250)
        self._controller = controller

        self._selector = ProjectSelector(
            controller,
            initial_project=initial_project,
        )
        self.add_widget(self._selector, stretch=0)

        self._slicer = AYSlicer(
            item_list=self.CATEGORIES,
            initial_text=initial_category,
        )
        self.add_widget(self._slicer, stretch=0)

        self._tree_view = ReviewTreeView(self)
        self.add_widget(self._tree_view, stretch=0)

        self._progress = AsyncTaskQueueMonitor(get_task_queue(), parent=self)
        self.add_widget(self._progress, stretch=0)

        self._slicer.category_changed.connect(self._on_category_changed)
        self._tree_view.selection_changed.connect(self._on_selection_changed)

    def set_model(self, model: LazyTreeModel) -> None:
        """Attach a tree model to the view and slicer proxy.

        Args:
            model: The lazy tree model to display.
        """
        self._tree_view.setModel(model)
        self._slicer.set_model(self._tree_view.model(), view=self._tree_view)

    def _on_category_changed(self, category: str) -> None:
        self._controller.set_category(category)

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        log.debug("Selected: %s, Deselected: %s", selected, deselected)
        # Read the canonical full selection rather than the delta
        # arguments, which are unreliable under ExtendedSelection.
        all_indexes = [
            idx
            for idx in self._tree_view.selectionModel().selectedIndexes()
            if idx.column() == 0
        ]
        ids: list[str] = []
        names: list[str] = []
        for idx in all_indexes:
            data = idx.data(QtCore.Qt.ItemDataRole.UserRole)
            if data:
                entity_id = data.get("id", "")
                if entity_id:
                    ids.append(entity_id)
                    names.append(data.get("name", ""))
        log.debug("Current selection ids: %s", ids)
        self._controller.on_tree_selection_changed(ids, names)

    def current_category(self) -> str:
        """Return the currently selected category name."""
        return self._slicer.current_category()

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self._selector.current_project()
