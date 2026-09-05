"""Left-hand slicer panel with project selector, category slicer, and tree."""

from __future__ import annotations

from typing import Any

from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.combo_box import AYComboBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.slicer import AYSlicer
from ayon_core.ui.components.task_queue import get_task_queue
from ayon_core.ui.components.task_queue_monitor import AsyncTaskQueueMonitor
from ayon_core.ui.components.tree_model import LazyTreeModel
from ayon_core.ui.components.tree_view import AYTreeView, QItemSelection
from qtpy import QtCore, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
from ayon_core.tools.utils import ProjectsCombobox

from ._browser_slicer_filters import MyTasksToggleButton
from .tasks_widget import BrowserTasksWidget

log = Logger.get_logger(__name__)


class ReviewTreeView(AYTreeView):
    """Tree view used inside the review slicer."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, variant=AYTreeView.Variants.Low)


class BrowserSlicer(AYContainer):
    """Left-hand panel with project selector, category slicer and tree."""

    #: Attempts, one per 100 ms timer tick, spent waiting for the project
    #: switch and then the lazily fetched folder rows.
    _MAX_SELECTION_ATTEMPTS = 30

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

    def __init__(
        self,
        controller: BrowserWidgetController,
        loader_controller,
        *args: Any,
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
        self._pending_context: tuple[str, str] | None = None
        self._folder_selection_chain: list[str] = []
        self._folder_selection_attempt = 0
        self._folder_selection_timer = QtCore.QTimer(self)
        self._folder_selection_timer.setSingleShot(True)
        self._folder_selection_timer.setInterval(100)
        self._folder_selection_timer.timeout.connect(
            self._retry_folder_selection
        )

        self._selector = ProjectsCombobox(
            loader_controller,
            self,
            handle_expected_selection=True,
            variant=AYComboBox.Variants.Low,
        )
        self._selector.set_select_item_visible(True)
        self._selector.set_libraries_separator_visible(True)
        self._selector.set_standard_filter_enabled(
            loader_controller.is_standard_projects_filter_enabled()
        )
        self.add_widget(self._selector, stretch=0)

        self._slicer = AYSlicer(
            item_list=self.CATEGORIES,
            initial_text=initial_category,
        )
        self._my_tasks_btn = MyTasksToggleButton(self)
        self._slicer.add_trailing_widget(self._my_tasks_btn)
        self._go_to_current_btn = AYButton(
            variant=AYButton.Variants.Nav,
            icon="my_location",
            tooltip="Select the current context in the hierarchy",
        )
        self._go_to_current_btn.clicked.connect(
            self.select_current_context
        )
        self._slicer.add_trailing_widget(self._go_to_current_btn)
        self.add_widget(self._slicer, stretch=0)
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
        self._tasks.task_selection_changed.connect(
            self._on_task_selection_changed
        )
        self._tasks.refreshed.connect(
            lambda: self._tasks.set_selected_task_names(self._task_names)
        )
        self._my_tasks_btn.toggled.connect(self._apply_my_tasks_filter)
        self._controller.my_tasks_filter_changed.connect(
            self._on_controller_my_tasks_filter_changed
        )
        self._selector.selection_changed.connect(self._controller.set_project)
        loader_controller.register_event_callback(
            "controller.reset.finished",
            self._on_controller_reset_finished,
        )

        # Initialise the toggle's visibility for the starting category
        # now that the tasks widget it feeds into exists.
        self._my_tasks_btn.set_category(
            BrowserSlicerCategory(initial_category)
        )

    def _on_controller_reset_finished(self) -> None:
        """Keep the project selector in sync with the host's context.

        Mirrors the legacy loader tool: the current-context project is
        always kept selectable regardless of the library filter, and the
        combobox is refreshed since its own auto-refresh (triggered by
        the shared projects model) is skipped for same-sender refreshes.
        """
        context = self._loader_controller.get_current_context() or {}
        self._selector.set_current_context_project(
            context.get("project_name") or ""
        )
        self._selector.refresh()

    def set_model(self, model: LazyTreeModel) -> None:
        """Attach a tree model to the view and slicer proxy.

        Args:
            model: The lazy tree model to display.
        """
        self._slicer.set_model(model, view=self._tree_view)

    def _on_category_changed(self, category: str) -> None:
        self._controller.set_category(category)
        # Update the toggle's visibility for the new mode first (this
        # clears "My Tasks" -- via its own toggled signal -- when
        # switching away from Hierarchy) before the tasks widget
        # re-fetches using the now-current scope.
        self._my_tasks_btn.set_category(BrowserSlicerCategory(category))
        enabled = category == BrowserSlicerCategory.HIERARCHY.value
        self._tasks.setEnabled(enabled)
        if enabled:
            self._tasks.set_context(
                self._controller.current_project,
                list(self._last_selection_ids or []),
                task_id_scope=self._controller.get_task_id_scope(),
            )
        else:
            self._tasks.set_context(self._controller.current_project, [])
        self._update_current_context_button(category)

    def _apply_my_tasks_filter(self, enabled: bool) -> None:
        """Apply the "My Tasks" toggle to the controller and task list."""
        self._controller.set_my_tasks_filter(enabled)
        self._tasks.set_task_id_scope(self._controller.get_task_id_scope())

    def _on_controller_my_tasks_filter_changed(self, enabled: bool) -> None:
        """React to the filter changing from outside the toggle itself.

        Currently only reached when a saved View is applied (see
        ``BrowserTable._apply_view_extras``); keeps the toggle's
        checked state and the task list's scope in sync with it.
        """
        self._my_tasks_btn.blockSignals(True)
        self._my_tasks_btn.setChecked(enabled)
        self._my_tasks_btn.blockSignals(False)
        self._tasks.set_task_id_scope(self._controller.get_task_id_scope())

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
        self._slicer.set_current_category(
            BrowserSlicerCategory.HIERARCHY.value
        )
        if project_name != self._controller.current_project:
            self._selector.set_selection(project_name)
        self._folder_selection_timer.stop()
        self._pending_context = (project_name, folder_id)
        self._folder_selection_chain = []
        self._folder_selection_attempt = 0
        self._advance_context_selection(0)

    def _advance_context_selection(self, attempt: int) -> None:
        """Move the pending context selection forward by one attempt.

        Two things have to land before the folder can be selected, and
        neither is synchronous at startup. The project switch requested
        above is a no-op while the projects combo box is still populating,
        and the hierarchy must not be queried until it has landed -
        ``get_folder_id_path`` would otherwise run against an empty
        project name. Only then are the tree rows fetched, lazily, which
        is what :meth:`_select_folder_chain` waits on.

        Args:
            attempt: Number of attempts already spent.
        """
        if self._pending_context is None:
            return
        if attempt >= self._MAX_SELECTION_ATTEMPTS:
            self._clear_pending_selection()
            return

        project_name, folder_id = self._pending_context
        if self._controller.current_project != project_name:
            self._folder_selection_attempt = attempt + 1
            self._folder_selection_timer.start()
            return

        if not self._folder_selection_chain:
            self._folder_selection_chain = (
                self._controller.get_folder_id_path(folder_id)
            )
            if not self._folder_selection_chain:
                self._clear_pending_selection()
                return
        self._select_folder_chain(self._folder_selection_chain, attempt)

    def _clear_pending_selection(self) -> None:
        """Forget an in-flight context selection."""
        self._pending_context = None
        self._folder_selection_chain = []
        self._folder_selection_attempt = 0

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
        if not chain or attempt >= self._MAX_SELECTION_ATTEMPTS:
            self._clear_pending_selection()
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
            self._clear_pending_selection()
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
        self._clear_pending_selection()

    def _retry_folder_selection(self) -> None:
        self._advance_context_selection(self._folder_selection_attempt)

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
            task_id_scope=self._controller.get_task_id_scope(),
        )

    def set_task_names(self, names: list[str]) -> None:
        """Update task-list selection from the active filter criterion."""
        self._task_names = list(names)
        self._tasks.set_selected_task_names(self._task_names)

    def _on_task_selection_changed(
        self,
        names: list[str],
        task_ids: list[str],
    ) -> None:
        """Update loader selection IDs and the name-based table filter."""
        self._loader_controller.set_selected_tasks(set(task_ids))
        self.task_names_changed.emit(names)

    def current_category(self) -> str:
        """Return the currently selected category name."""
        return self._slicer.current_category()

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self._selector.get_selected_project_name() or ""
