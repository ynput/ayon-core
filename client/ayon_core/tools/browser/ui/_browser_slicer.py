"""Left-hand slicer panel with project selector, category slicer, and tree."""

from __future__ import annotations

from typing import Any

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.slicer import AYSlicer
from ayon_core.ui.components.task_queue import get_task_queue
from ayon_core.ui.components.task_queue_monitor import AsyncTaskQueueMonitor
from ayon_core.ui.components.tree_model import LazyTreeModel
from ayon_core.ui.components.tree_view import AYTreeView, QItemSelection
from ayon_core.tools.utils import GoToCurrentButton
from qtpy import QtCore, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.browser_controller import BrowserController
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory

from ._project_selector import ProjectSelector
from .tasks_widget import BrowserTasksWidget

log = Logger.get_logger(__name__)


class ReviewTreeView(AYTreeView):
    """Tree view used inside the review slicer."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, variant=AYTreeView.Variants.Low)


class BrowserSlicer(AYContainer):
    """Left-hand panel with project selector, category slicer and tree."""

    CATEGORIES = [
        {
            "text": BrowserSlicerCategory.HIERARCHY.value,
            "short_text": "HIE",
            "icon": "table_rows",
            "color": "#f4f5f5",
        },
        {
            "text": BrowserSlicerCategory.REVIEWS.value,
            "short_text": "REV",
            "icon": "subscriptions",
            "color": "#f4f5f5",
        },
    ]
    task_names_changed = QtCore.Signal(list)
    folder_navigation_finished = QtCore.Signal(str)
    folder_navigation_failed = QtCore.Signal(str)

    def __init__(
        self,
        controller: BrowserController,
        loader_controller,
        *args: Any,
        initial_project: str = "",
        initial_category: str = BrowserSlicerCategory.HIERARCHY.value,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_margin=0,
            layout_spacing=4,
            **kwargs,
        )
        self.setMinimumWidth(250)
        self._controller = controller
        self._loader_controller = loader_controller
        self._task_names: list[str] = []
        self._last_selection_ids: tuple[str, ...] | None = None
        self._folder_selection_chain: list[str] = []
        self._folder_selection_attempt = 0
        self._folder_selection_timer = QtCore.QTimer(self)
        self._folder_selection_timer.setSingleShot(True)
        self._folder_selection_timer.setInterval(100)
        self._folder_selection_timer.timeout.connect(
            self._retry_folder_selection
        )

        self._selector = ProjectSelector(
            controller,
            initial_project=initial_project,
        )
        self.add_widget(self._selector, stretch=0)

        self._slicer = AYSlicer(
            item_list=self.CATEGORIES,
            initial_text=initial_category,
        )
        self._go_to_current_btn = GoToCurrentButton(self)
        self._go_to_current_btn.setToolTip(
            "Select the current context in the hierarchy"
        )
        self._go_to_current_btn.clicked.connect(
            self.select_current_context
        )
        category_layout = QtWidgets.QHBoxLayout()
        category_layout.setContentsMargins(0, 0, 0, 0)
        category_layout.setSpacing(4)
        category_layout.addWidget(self._slicer, stretch=1)
        category_layout.addWidget(self._go_to_current_btn, stretch=0)
        self.add_layout(category_layout, stretch=0)
        self._update_current_context_button(initial_category)

        self._tree_view = ReviewTreeView(self)
        self.add_widget(self._tree_view, stretch=1)

        self._tasks = BrowserTasksWidget(
            loader_controller,
            self,
        )
        self.add_widget(self._tasks, stretch=0)

        self._progress = AsyncTaskQueueMonitor(get_task_queue(), parent=self)
        self.add_widget(self._progress, stretch=0)

        self._slicer.category_changed.connect(self._on_category_changed)
        self._tree_view.selection_changed.connect(self._on_selection_changed)
        self._tasks.task_names_changed.connect(self.task_names_changed)
        self._tasks.refreshed.connect(
            lambda: self._tasks.set_selected_task_names(self._task_names)
        )

    def set_model(self, model: LazyTreeModel) -> None:
        """Attach a tree model to the view and slicer proxy.

        Args:
            model: The lazy tree model to display.
        """
        self._slicer.set_model(model, view=self._tree_view)

    def _on_category_changed(self, category: str) -> None:
        self._controller.set_category(category)
        enabled = category == BrowserSlicerCategory.HIERARCHY.value
        self._tasks.setEnabled(enabled)
        if enabled:
            self._tasks.set_context(
                self._controller.current_project,
                list(self._last_selection_ids or []),
            )
        else:
            self._tasks.set_context(self._controller.current_project, [])
        self._update_current_context_button(category)

    def _update_current_context_button(self, category: str) -> None:
        context = self._loader_controller.get_current_context() or {}
        self._go_to_current_btn.setVisible(
            category == BrowserSlicerCategory.HIERARCHY.value
            and bool(context.get("project_name") and context.get("folder_id"))
        )

    def select_current_context(self) -> None:
        """Select the host's current folder in the hierarchy tree."""
        context = self._loader_controller.get_current_context()
        project_name = context.get("project_name", "")
        folder_id = context.get("folder_id")
        if not project_name or not folder_id:
            return
        self.select_folder(project_name, folder_id)

    def select_folder(self, project_name: str, folder_id: str) -> None:
        """Select and reveal a folder in the hierarchy tree."""
        self._slicer.set_current_category(
            BrowserSlicerCategory.HIERARCHY.value
        )
        if project_name != self._controller.current_project:
            self._selector.set_current_project(project_name)
        chain = self._controller.get_folder_id_path(folder_id)
        self._folder_selection_timer.stop()
        self._folder_selection_chain = chain
        self._folder_selection_attempt = 0
        if not chain:
            self.folder_navigation_failed.emit(folder_id)
            return
        self._select_folder_chain(chain, 0)

    def _get_view_index_by_id(self, folder_id: str) -> QtCore.QModelIndex:
        model = self._tree_view.model()
        source_model = (
            model.sourceModel()
            if isinstance(model, QtCore.QAbstractProxyModel)
            else model
        )
        source_index = source_model.get_index_by_id(folder_id)
        if (
            source_index.isValid()
            and isinstance(model, QtCore.QAbstractProxyModel)
        ):
            return model.mapFromSource(source_index)
        return source_index

    def _select_folder_chain(
        self,
        chain: list[str],
        attempt: int,
    ) -> None:
        if not chain:
            return
        if attempt >= 30:
            self._folder_selection_chain = []
            self._folder_selection_attempt = 0
            self.folder_navigation_failed.emit(chain[-1])
            return
        available_count = 0
        for folder_id in chain:
            index = self._get_view_index_by_id(folder_id)
            if not index.isValid():
                break
            available_count += 1
            if folder_id != chain[-1]:
                self._tree_view.expand(index)

        if available_count < len(chain):
            self._folder_selection_chain = chain
            self._folder_selection_attempt = attempt + 1
            self._folder_selection_timer.start()
            return

        index = self._get_view_index_by_id(chain[-1])
        if not index.isValid():
            return
        selection_model = self._tree_view.selectionModel()
        selection_model.select(
            index,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        self._tree_view.setCurrentIndex(index)
        self._tree_view.scrollTo(
            index,
            QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        self._folder_selection_chain = []
        self._folder_selection_attempt = 0
        self.folder_navigation_finished.emit(chain[-1])

    def _retry_folder_selection(self) -> None:
        if not self._folder_selection_chain:
            return
        self._select_folder_chain(
            self._folder_selection_chain,
            self._folder_selection_attempt,
        )

    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
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
        selection_key = tuple(ids)
        if selection_key == self._last_selection_ids:
            return
        self._last_selection_ids = selection_key
        log.debug("Selected: %s, Deselected: %s", selected, deselected)
        log.debug("Current selection ids: %s", ids)
        self._controller.on_tree_selection_changed(ids, names)
        self._tasks.set_context(
            self._controller.current_project,
            ids,
        )

    def set_task_names(self, names: list[str]) -> None:
        """Update task-list selection from the active filter criterion."""
        self._task_names = list(names)
        self._tasks.set_selected_task_names(self._task_names)

    def current_category(self) -> str:
        """Return the currently selected category name."""
        return self._slicer.current_category()

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self._selector.current_project()
