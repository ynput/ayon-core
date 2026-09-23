"""Left-hand slicer panel with project selector, category slicer, and tree."""

from __future__ import annotations

import typing
from typing import Any

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components import AYLineEdit
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.combo_box import AYComboBox
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.task_queue import get_task_queue
from ayon_core.ui.components.task_queue_monitor import AsyncTaskQueueMonitor
from ayon_core.ui.components.tree_model import BulkTreeModel
from ayon_core.ui.components.tree_view import AYTreeView, QItemSelection
from ayon_core.ui.style_types import get_ayon_style
from ayon_core.ui.variants import QTreeViewVariants
from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
from ayon_core.tools.utils import ProjectsCombobox
from ayon_core.tools.utils.folders_widget import CenteredIconDelegate

from .tasks_widget import BrowserTasksWidget
from .folders_model import (
    BrowserFoldersModel,
    BrowserFoldersProxyModel,
    FOLDER_ID_ROLE,
)

if typing.TYPE_CHECKING:
    from ayon_core.tools.browser.abstract import AbstractBrowserController
    from ayon_core.tools.browser.ui.browser_controller import (
        BrowserWidgetController,
    )

log = Logger.get_logger(__name__)

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


class TreeFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Proxy that filters tree items, recursively including 'fuzzy' search """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(
            QtCore.Qt.CaseSensitivity.CaseInsensitive
        )
        self.setFilterRole(QtCore.Qt.ItemDataRole.DisplayRole)
        self.setRecursiveFilteringEnabled(True)  # Qt 5.10+
        self._filter_terms: list[str] = []

    def set_filter_text(self, text: str) -> None:
        """Update the active search terms and re-apply the filter."""
        self._filter_terms = text.casefold().split()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if not self._filter_terms:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return True
        index = source_model.index(source_row, 0, source_parent)
        text = index.data(self.filterRole())
        if not text:
            return False
        text = str(text).casefold()
        return all(term in text for term in self._filter_terms)


class SlicerCategories(AYContainer):
    category_changed = QtCore.Signal(str)
    my_tasks_requested = QtCore.Signal(bool)
    go_to_current_clicked = QtCore.Signal()
    filter_changed = QtCore.Signal(str)

    def __init__(
        self,
        category: str,
        ui_controller: BrowserWidgetController,
        be_controller: AbstractBrowserController,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            parent=parent,
        )
        self._be_controller = be_controller

        self._combo = AYComboBox(
            items=CATEGORIES,
            variant=AYComboBox.Variants.Low,
            show_chevron=False,
        )
        self._filter_field = AYLineEdit(placeholder="Search")
        self._filter_btn = AYButton(
            variant=AYButton.Variants.Nav,
            icon="search",
            icon_on="close",
            checkable=True,
        )
        self._my_tasks_btn = AYButton(
            variant=AYButton.Variants.Nav,
            icon="assignment_ind",
            checkable=True,
            tooltip="Only show folders that have a task assigned to you.",
            parent=self,
        )

        self._go_to_current_btn = AYButton(
            variant=AYButton.Variants.Nav,
            icon="my_location",
            tooltip="Select the current context in the hierarchy",
        )

        self.add_widget(self._combo)
        self.add_widget(self._filter_field, stretch=1)
        self.add_widget(self._filter_btn)
        self.add_widget(self._my_tasks_btn)
        self.add_widget(self._go_to_current_btn)

        self._filter_field.setVisible(False)

        self._filter_field.installEventFilter(self)

        # signals
        self._filter_btn.toggled.connect(self._on_button_toggled)
        self._filter_field.textChanged.connect(self.filter_changed)
        self._combo.activated.connect(self._on_category_activated)
        self._my_tasks_btn.toggled.connect(self.my_tasks_requested)
        self._go_to_current_btn.clicked.connect(
            self.go_to_current_clicked
        )
        ui_controller.my_tasks_filter_changed.connect(
            self._on_controller_my_tasks_filter_changed
        )

        # Initialise the toggle's visibility for the starting category
        # now that the tasks widget it feeds into exists.
        self._update_buttons(BrowserSlicerCategory(category))

    def eventFilter(self, obj, event):
        """Close search field on Escape key press."""
        if (
            obj is self._filter_field
            and event.type() == QtCore.QEvent.Type.KeyPress
            and event.key() == QtCore.Qt.Key.Key_Escape
        ):
            # triggers _on_button_toggled
            self._filter_btn.setChecked(False)
            return True
        return super().eventFilter(obj, event)

    def filter_text(self) -> str:
        return self._filter_field.text()

    def current_category(self) -> str:
        return self._combo.currentText()

    def set_current_category(self, category: str) -> None:
        """Select a category by its display text."""
        if category == self._combo.currentText():
            return
        self._combo.blockSignals(True)
        self._combo.setCurrentText(category)
        self._combo.blockSignals(False)
        self._set_current_category(category)

    def _on_controller_my_tasks_filter_changed(self, enabled: bool) -> None:
        self._my_tasks_btn.blockSignals(True)
        self._my_tasks_btn.setChecked(enabled)
        self._my_tasks_btn.blockSignals(False)

    def _on_category_activated(self, index: int) -> None:
        """Emit the selected category."""
        self._set_current_category(self._combo.itemText(index))

    def _set_current_category(self, category: str) -> None:
        category_v = BrowserSlicerCategory(category)
        self._update_buttons(category_v)
        self.category_changed.emit(category)

    def _on_button_toggled(self, checked):
        self._combo.setVisible(not checked)
        self._filter_field.setVisible(checked)
        if checked:
            self._filter_field.setFocus()
        else:
            # clear the filter when closing search
            self._filter_field.clear()

    def _update_buttons(self, category: BrowserSlicerCategory) -> None:
        context = self._be_controller.get_current_context() or {}
        applicable = category == BrowserSlicerCategory.HIERARCHY
        self._go_to_current_btn.setVisible(
            applicable
            and bool(context.get("project_name") and context.get("folder_id"))
        )
        if not applicable and self._my_tasks_btn.isChecked():
            self._my_tasks_btn.setChecked(False)
        self._my_tasks_btn.setVisible(applicable)


class BrowserFolderTreeView(AYTreeView):
    """Tree view used inside the review slicer."""

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent, variant=AYTreeView.Variants.Low)
        self.setHeaderHidden(True)
        self.setUniformRowHeights(True)


class BrowserSlicer(AYContainer):
    """Left-hand panel with project selector, category slicer and tree."""

    #: Attempts, one per 100 ms timer tick, spent waiting for the project
    #: switch and then the fetched folder rows.
    _MAX_SELECTION_ATTEMPTS = 30

    task_names_changed = QtCore.Signal(list)

    def __init__(
        self,
        ui_controller: BrowserWidgetController,
        be_controller: AbstractBrowserController,
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
        self._ui_controller = ui_controller
        self._be_controller = be_controller
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
            be_controller,
            self,
            handle_expected_selection=True,
            variant=AYComboBox.Variants.Low,
        )
        self._selector.set_select_item_visible(True)
        self._selector.set_standard_filter_enabled(
            be_controller.is_standard_projects_filter_enabled()
        )
        self.add_widget(self._selector, stretch=0)

        self._categories = SlicerCategories(
            initial_category,
            ui_controller,
            be_controller,
        )
        self.add_widget(self._categories, stretch=0)

        self._folders_view = BrowserFolderTreeView(self)

        self._folders_model = BrowserFoldersModel(
            ui_controller, be_controller
        )
        self._folders_proxy = BrowserFoldersProxyModel()
        self._folders_proxy.setSourceModel(self._folders_model)
        self._folders_view.setModel(self._folders_proxy)

        header = self._folders_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(1, 30)
        self._folders_view.setItemDelegateForColumn(
            1,
            CenteredIconDelegate(
                parent=self._folders_view,
                style_model=get_ayon_style().model,
                variant=QTreeViewVariants.Default.value,
            )
        )

        self._reviews_view = BrowserFolderTreeView(self)
        self._reviews_model = BulkTreeModel(
            fetch_all=self._ui_controller.fetch_reviews
        )
        self._reviews_proxy = TreeFilterProxyModel(self)
        self._reviews_proxy.setSourceModel(self._reviews_model)
        self._reviews_view.setModel(self._reviews_proxy)

        self.add_widget(self._folders_view, stretch=1)
        self.add_widget(self._reviews_view, stretch=1)

        self._set_view(initial_category)

        self._tasks = BrowserTasksWidget(
            be_controller,
            self,
        )
        self.add_widget(self._tasks, stretch=0)

        self._progress = AsyncTaskQueueMonitor(get_task_queue(), parent=self)
        self.add_widget(self._progress, stretch=0)

        self._categories.category_changed.connect(self._on_category_changed)
        self._categories.go_to_current_clicked.connect(
            self.select_current_context
        )
        self._categories.my_tasks_requested.connect(
            self._apply_my_tasks_filter
        )
        self._categories.filter_changed.connect(
            self._on_text_filter_changed
        )
        self._folders_view.selection_changed.connect(
            self._on_folders_selection_changed
        )
        self._folders_model.reset_finished.connect(self._on_folders_reset)
        self._reviews_view.selection_changed.connect(
            self._on_reviews_selection_changed
        )
        self._reviews_model.loading_changed.connect(
            self._on_reviews_loading_changed
        )
        self._tasks.task_selection_changed.connect(
            self._on_task_selection_changed
        )
        self._tasks.refreshed.connect(self._on_tasks_refreshed)
        self._ui_controller.my_tasks_filter_changed.connect(
            self._on_controller_my_tasks_filter_changed
        )
        self._selector.selection_changed.connect(self._on_project_change)
        be_controller.register_event_callback(
            "controller.reset.finished",
            self._on_controller_reset_finished,
        )

    def _on_project_change(self, project_name: str) -> None:
        self._ui_controller.set_project(project_name)
        # The "My Tasks" scope is re-resolved for the new project by the
        # controller, but without a filter-changed signal - re-apply it.
        self._sync_my_tasks_scope()
        self.reset()

    def _on_controller_reset_finished(self) -> None:
        """Keep the project selector in sync with the host's context.

        Mirrors the legacy loader tool: the current-context project is
        always kept selectable regardless of the library filter, and the
        combobox is refreshed since its own auto-refresh (triggered by
        the shared projects model) is skipped for same-sender refreshes.
        """
        context = self._be_controller.get_current_context() or {}
        self._selector.set_current_context_project(
            context.get("project_name") or ""
        )
        self._selector.refresh()

    def reset(self) -> None:
        category = self.current_category()
        if category == BrowserSlicerCategory.HIERARCHY.value:
            self._folders_model.reset()
        else:
            self._reviews_model.reset()

    def _on_category_changed(self, category: str) -> None:
        self._set_view(category)
        self._ui_controller.set_category(category)
        enabled = category == BrowserSlicerCategory.HIERARCHY.value
        self._tasks.setEnabled(enabled)
        if enabled:
            self._tasks.set_context(
                self._ui_controller.current_project,
                list(self._last_selection_ids or []),
                task_id_scope=self._ui_controller.get_task_id_scope(),
            )
        else:
            self._tasks.set_context(
                self._ui_controller.current_project,
                [],
            )
        self.reset()

    def _apply_my_tasks_filter(self, enabled: bool) -> None:
        """Apply the "My Tasks" toggle to the controller and task list."""
        self._ui_controller.set_my_tasks_filter(enabled)
        self._tasks.set_task_id_scope(self._ui_controller.get_task_id_scope())

    def _on_text_filter_changed(self, text: str):
        """Update the proxy filter when the user types.

        A non-empty search expands the whole tree so recursively
        matched rows - whose ancestors may otherwise still be
        collapsed - are actually visible, matching the Launcher
        folders widget's behaviour on a non-empty filter.
        """
        self._folders_proxy.set_name_filter(text)
        self._reviews_proxy.set_filter_text(text)

        if text:
            self._current_view().expandAll()

    def _on_controller_my_tasks_filter_changed(self, enabled: bool) -> None:
        """React to the filter changing from outside the toggle itself.

        Currently only reached when a saved View is applied (see
        ``BrowserTable._apply_view_extras``); keeps the toggle's
        checked state and the task list's scope in sync with it.
        """
        self._sync_my_tasks_scope()

    def _sync_my_tasks_scope(self) -> None:
        """Apply the controller's "My Tasks" scope to folders and tasks."""
        self._folders_proxy.set_folder_ids_filter(
            self._ui_controller.get_folder_id_scope()
        )
        self._tasks.set_task_id_scope(
            self._ui_controller.get_task_id_scope()
        )

    def _set_view(self, category: str) -> None:
        folders_visible = category == BrowserSlicerCategory.HIERARCHY.value
        review_visible = not folders_visible
        self._folders_view.setVisible(folders_visible)
        self._reviews_view.setVisible(review_visible)
        filter_text = self._categories.filter_text()
        if filter_text:
            if folders_visible:
                self._folders_view.expandAll()
            else:
                self._reviews_view.expandAll()

    def select_current_context(self) -> None:
        """Select the host's current folder in the hierarchy tree."""
        context = self._be_controller.get_current_context()
        project_name = context.get("project_name", "")
        folder_id = context.get("folder_id")
        if not project_name or not folder_id:
            return
        self._categories.set_current_category(
            BrowserSlicerCategory.HIERARCHY.value
        )
        if project_name != self._ui_controller.current_project:
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
        project name. Only then does the tree's fetch land,
        which is what :meth:`_select_folder_chain` waits on.

        Args:
            attempt: Number of attempts already spent.
        """
        if self._pending_context is None:
            return
        if attempt >= self._MAX_SELECTION_ATTEMPTS:
            self._clear_pending_selection()
            return

        project_name, folder_id = self._pending_context
        if self._ui_controller.current_project != project_name:
            self._folder_selection_attempt = attempt + 1
            self._folder_selection_timer.start()
            return

        if not self._folder_selection_chain:
            self._folder_selection_chain = (
                self._ui_controller.get_folder_id_path(folder_id)
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

    def _current_view(self) -> BrowserFolderTreeView:
        """Return the tree view shown for the current category."""
        if self.current_category() == BrowserSlicerCategory.HIERARCHY.value:
            return self._folders_view
        return self._reviews_view

    def _get_view_index_by_id(self, folder_id: str) -> QtCore.QModelIndex:
        model = self._current_view().model()
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
        view = self._current_view()
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
                view.expand(index)

        if available_count < len(chain):
            self._folder_selection_chain = chain
            self._folder_selection_attempt = attempt + 1
            self._folder_selection_timer.start()
            return

        index = self._get_view_index_by_id(chain[-1])
        if not index.isValid():
            self._clear_pending_selection()
            return
        selection_model = view.selectionModel()
        selection_model.select(
            index,
            QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )
        view.setCurrentIndex(index)
        view.scrollTo(
            index,
            QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
        )
        self._clear_pending_selection()

    def _retry_folder_selection(self) -> None:
        self._advance_context_selection(self._folder_selection_attempt)

    def _on_folders_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        # Read the canonical full selection rather than the delta
        # arguments, which are unreliable under ExtendedSelection.
        explicit_ids: list[str] = []
        selected_rows = []
        for index in self._folders_view.selectionModel().selectedRows():
            folder_id = index.data(FOLDER_ID_ROLE)
            if folder_id:
                explicit_ids.append(folder_id)
                selected_rows.append((folder_id, index))

        ids = list(explicit_ids)
        if self._ui_controller.include_folder_children:
            for folder_id, index in selected_rows:
                parent = index.parent()
                while parent.isValid():
                    parent_id = parent.data(FOLDER_ID_ROLE)
                    if parent_id in ids:
                        ids.remove(folder_id)
                        break
                    parent = parent.parent()

        # Key on the explicit selection: the tasks list shows tasks of
        # every selected row, even ones collapsed into a selected
        # ancestor above. The controller ignores unchanged 'ids' itself.
        selection_key = tuple(explicit_ids)
        if selection_key == self._last_selection_ids:
            return
        self._last_selection_ids = selection_key
        log.debug("Selected: %s, Deselected: %s", selected, deselected)
        log.debug(
            "Current selection ids: %s (top-level: %s)", explicit_ids, ids
        )
        self._ui_controller.on_tree_selection_changed(ids)
        self._tasks.set_context(
            self._ui_controller.current_project,
            explicit_ids,
            task_id_scope=self._ui_controller.get_task_id_scope(),
        )

    def _on_folders_reset(self):
        self._folders_proxy.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
        # A search typed while the folders were still loading had
        # nothing to expand yet - expand the now-filled tree.
        if self._categories.filter_text():
            self._folders_view.expandAll()

    def _on_reviews_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        # Read the canonical full selection rather than the delta
        # arguments, which are unreliable under ExtendedSelection.
        ids: list[str] = []
        for idx in self._reviews_view.selectionModel().selectedRows():
            data = idx.data(QtCore.Qt.ItemDataRole.UserRole)
            if data:
                entity_id = data.get("id", "")
                if entity_id:
                    ids.append(entity_id)

        selection_key = tuple(ids)
        if selection_key == self._last_selection_ids:
            return
        self._last_selection_ids = selection_key
        log.debug("Selected: %s, Deselected: %s", selected, deselected)
        log.debug("Current selection ids: %s", ids)
        self._ui_controller.on_tree_selection_changed(ids)
        self._tasks.set_context(
            self._ui_controller.current_project,
            ids,
            task_id_scope=self._ui_controller.get_task_id_scope(),
        )

    def _on_reviews_loading_changed(self, loading: bool) -> None:
        """Re-expand the view once a still-loading model finishes.

        A search typed while the model's data has not arrived yet
        filters an (as far as the proxy can tell) empty tree, so the
        expandAll() in _on_search_changed() has nothing to expand.
        Once loading finishes and the proxy has re-synced against the
        now-populated model, re-run it for any search still active.
        """
        if loading or self._reviews_view is None:
            return

        if self._categories.filter_text():
            self._reviews_view.expandAll()

    def set_task_names(self, names: list[str]) -> None:
        """Update task-list selection from the active filter criterion."""
        self._task_names = list(names)
        self._tasks.set_selected_task_names(self._task_names)

    def _on_tasks_refreshed(self) -> None:
        """Re-apply the filter's task names to the refreshed task list.

        Re-selecting rows here is not a user action, so it must not feed
        back into the Task filter - tasks it names may not exist under the
        folder now in context. Only the loader's selected ids are brought
        back in step, since those describe the current context.
        """
        self._tasks.set_selected_task_names(self._task_names)
        self._ui_controller.set_selected_task_ids(
            self._tasks.selected_task_ids()
        )

    def _on_task_selection_changed(
        self,
        names: list[str],
        task_ids: list[str],
    ) -> None:
        """Update loader selection IDs and the name-based table filter."""
        self._ui_controller.set_selected_task_ids(task_ids)
        self.task_names_changed.emit(names)

    def current_category(self) -> str:
        """Return the currently selected category name."""
        return self._categories.current_category()

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self._selector.get_selected_project_name() or ""
