from __future__ import annotations

import collections
import hashlib
from typing import Any

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import TASKS_MODEL_SENDER_NAME
from ayon_core.tools.utils.lib import RefreshThread, get_qt_icon
from ayon_core.ui.components.table_view import AYTableView


TASK_DATA_ROLE = QtCore.Qt.ItemDataRole.UserRole
log = Logger.get_logger(__name__)
_ACTIVE_REFRESH_THREADS: set[RefreshThread] = set()
_THREAD_SHUTDOWN_CONNECTED = False


def _wait_for_refresh_threads() -> None:
    """Keep Qt from destroying task threads while they are running."""
    for thread in list(_ACTIVE_REFRESH_THREADS):
        if thread.isRunning():
            thread.wait()


def _track_refresh_thread(thread: RefreshThread) -> None:
    """Keep a process-level reference until a task refresh has finished."""
    global _THREAD_SHUTDOWN_CONNECTED

    _ACTIVE_REFRESH_THREADS.add(thread)
    thread.finished.connect(
        lambda: _ACTIVE_REFRESH_THREADS.discard(thread)
    )
    app = QtWidgets.QApplication.instance()
    if app is not None and not _THREAD_SHUTDOWN_CONNECTED:
        app.aboutToQuit.connect(_wait_for_refresh_threads)
        _THREAD_SHUTDOWN_CONNECTED = True


class BrowserTasksWidget(QtWidgets.QWidget):
    """Browser-native task selector using the shared AYON table styling."""

    refreshed = QtCore.Signal()
    task_selection_changed = QtCore.Signal(list, list)

    def __init__(self, controller, parent=None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._project_name = ""
        self._folder_ids: list[str] = []
        self._selected_names: set[str] = set()
        self._selected_ids: set[str] = set()
        self._refresh_threads: dict[str, RefreshThread] = {}
        self._current_thread_id: str | None = None
        self._suppress_selection_changed = False

        self._model = QtGui.QStandardItemModel(self)
        self._model.setHorizontalHeaderLabels(["Task name", "Task type"])

        self._view = AYTableView(
            self,
            variant=AYTableView.Variants.Low,
        )
        self._view.setModel(self._model)
        self._view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._view.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._view.setShowGrid(False)
        self._view.setRootIsDecorated(False)
        self._view.setItemsExpandable(False)
        self._view.setIndentation(0)
        self._view.header().setSortIndicatorShown(False)
        self._view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

    def set_context(
        self,
        project_name: str,
        folder_ids: list[str],
    ) -> None:
        """Load tasks for the selected project and folders."""
        self._project_name = project_name
        self._folder_ids = list(folder_ids)
        if not project_name or not folder_ids:
            self._current_thread_id = None
            self._replace_rows([])
            self.refreshed.emit()
            return

        thread_id = hashlib.sha256(
            f"{project_name}|{'|'.join(sorted(folder_ids))}".encode()
        ).hexdigest()
        self._current_thread_id = thread_id
        if thread_id in self._refresh_threads:
            return
        thread = RefreshThread(
            thread_id,
            self._fetch_tasks,
            project_name,
            list(folder_ids),
        )
        self._refresh_threads[thread_id] = thread
        _track_refresh_thread(thread)
        thread.refresh_finished.connect(self._on_refresh_finished)
        thread.start()

    def refresh(self) -> None:
        """Reload tasks for the current context."""
        self.set_context(self._project_name, self._folder_ids)

    def set_selected_task_names(self, names: list[str]) -> None:
        """Select all rows whose task name is in *names*."""
        previous_names = set(self._selected_names)
        self._selected_names = set(names)
        self._apply_selection()
        self._sync_selected_rows(previous_names)

    def _apply_selection(self) -> None:
        """Apply the stored task names to the table selection."""
        selection_model = self._view.selectionModel()
        self._suppress_selection_changed = True
        try:
            selection_model.clearSelection()
            first_index = None
            for row in range(self._model.rowCount()):
                index = self._model.index(row, 0)
                data = index.data(TASK_DATA_ROLE) or {}
                if data.get("name") not in self._selected_names:
                    continue
                selection_model.select(
                    QtCore.QItemSelection(
                        index,
                        self._model.index(
                            row, self._model.columnCount() - 1
                        ),
                    ),
                    QtCore.QItemSelectionModel.SelectionFlag.Select,
                )
                if first_index is None:
                    first_index = index
            if first_index is not None:
                self._view.setCurrentIndex(first_index)
        finally:
            self._suppress_selection_changed = False
        self._view.viewport().update()

    def _sync_selected_rows(
        self,
        previous_names: set[str] | None = None,
    ) -> None:
        """Emit selected display names and all IDs stored on their rows."""
        names: set[str] = set()
        task_ids: set[str] = set()
        for index in self._view.selectionModel().selectedRows(0):
            data = index.data(TASK_DATA_ROLE) or {}
            name = data.get("name")
            if name:
                names.add(name)
            task_ids.update(data.get("ids") or [])

        if previous_names is None:
            previous_names = self._selected_names
        if names == previous_names and task_ids == self._selected_ids:
            return

        self._selected_names = names
        self._selected_ids = task_ids
        self.task_selection_changed.emit(
            sorted(names),
            sorted(task_ids),
        )

    def _fetch_tasks(
        self,
        project_name: str,
        folder_ids: list[str],
    ) -> tuple[list[Any], list[Any]]:
        task_items = self._controller.get_task_items(
            project_name,
            folder_ids,
            sender=TASKS_MODEL_SENDER_NAME,
        )
        task_type_items = self._controller.get_task_type_items(
            project_name,
            sender=TASKS_MODEL_SENDER_NAME,
        )
        return task_items, task_type_items

    def _on_refresh_finished(self, thread_id: str) -> None:
        thread = self._refresh_threads.pop(thread_id, None)
        if thread is None:
            return
        if thread_id != self._current_thread_id:
            return

        result = thread.get_result()
        if thread.failed or result is None:
            log.error(
                "Failed to refresh Browser tasks: %s",
                thread.get_exception(),
            )
            self._replace_rows([])
            self.refreshed.emit()
            return

        task_items, task_type_items = result
        type_items_by_name = {
            item.name: item for item in task_type_items
        }
        sort_by_type = (
            self._controller.get_task_sorting_mode(self._project_name)
            == "type"
        )
        items_by_name: dict[str, list[Any]] = collections.defaultdict(list)
        for task_item in task_items:
            items_by_name[task_item.name].append(task_item)
        grouped_items = sorted(
            items_by_name.values(),
            key=lambda items: (
                min(item.task_type_order for item in items)
                if sort_by_type
                else items[0].name.lower(),
                items[0].name.lower(),
            ),
        )
        rows = [
            self._create_task_row(
                items,
                type_items_by_name,
            )
            for items in grouped_items
        ]
        rows.append(self._create_no_task_row())
        self._replace_rows(rows)
        self.refreshed.emit()

    def _create_task_row(
        self,
        task_items: list[Any],
        type_items_by_name: dict[str, Any],
    ) -> list[QtGui.QStandardItem]:
        task_item = task_items[0]
        task_type_item = type_items_by_name.get(task_item.task_type)
        icon_name = "task_alt"
        icon_color = get_default_entity_icon_color()
        if task_type_item is not None:
            icon_name = task_type_item.icon or icon_name
            icon_color = task_type_item.color or icon_color
        icon = get_qt_icon(
            MaterialSymbolsIcon(icon_name, color=icon_color)
        )
        data = {
            "ids": [item.task_id for item in task_items],
            "name": task_item.name,
        }
        name_item = QtGui.QStandardItem(icon, task_item.name)
        name_item.setData(data, TASK_DATA_ROLE)
        task_types = sorted({
            item.task_type for item in task_items if item.task_type
        })
        type_item = QtGui.QStandardItem(
            ", ".join(task_types)
        )
        for item in (name_item, type_item):
            item.setEditable(False)
        return [name_item, type_item]

    def _create_no_task_row(self) -> list[QtGui.QStandardItem]:
        icon = get_qt_icon(
            MaterialSymbolsIcon(
                "indeterminate_check_box",
                color=get_default_entity_icon_color(),
            )
        )
        name_item = QtGui.QStandardItem(icon, "No task")
        name_item.setData(
            {"ids": [], "name": "No task"},
            TASK_DATA_ROLE,
        )
        empty_type = QtGui.QStandardItem("")
        for item in (name_item, empty_type):
            item.setEditable(False)
        return [name_item, empty_type]

    def _replace_rows(
        self,
        rows: list[list[QtGui.QStandardItem]],
    ) -> None:
        previous_names = set(self._selected_names)
        available_names = {
            row[0].data(TASK_DATA_ROLE).get("name")
            for row in rows
            if row[0].data(TASK_DATA_ROLE)
        }
        self._selected_names.intersection_update(available_names)
        self._suppress_selection_changed = True
        try:
            self._model.removeRows(0, self._model.rowCount())
            for row in rows:
                self._model.appendRow(row)
        finally:
            self._suppress_selection_changed = False
        self._apply_selection()
        self._sync_selected_rows(previous_names)

    def _on_selection_changed(self) -> None:
        if self._suppress_selection_changed:
            return
        self._sync_selected_rows()
