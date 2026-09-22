"""Folders hierarchy model used by the browser slicer.

Loading is optimized for large hierarchies (tens of thousands of folders):

- Server fetch, hierarchy walk and creation of the ``QStandardItem`` tree
  all run in a worker thread. Items are built *detached* (not part of any
  model), which is cheap and thread-safe because ``QStandardItem`` is not
  a ``QObject`` and emits nothing until it is inserted into a model.
- The main thread only assigns icons (``QIcon`` creation must stay on the
  GUI thread) and attaches the handful of top-level rows in a single
  model reset.
- The model does not override ``data``/``flags`` in Python. The status
  column is made of real items, so sorting and painting never call back
  into Python per row.
- A refresh of an already loaded project applies a diff instead of
  a reset, which keeps expanded and selected state in the view and costs
  next to nothing when nothing changed.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

from qtpy.QtCore import Qt, QSortFilterProxyModel, QModelIndex, Signal
from qtpy.QtGui import QStandardItemModel, QStandardItem, QIcon

from ayon_core.lib import Logger, MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon

from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models import (
        StatusItem,
        FolderItem,
        FolderTypeItem,
    )

log = Logger.get_logger(__name__)

FOLDER_ID_ROLE = Qt.UserRole + 1
FOLDER_NAME_ROLE = Qt.UserRole + 2
FOLDER_PATH_ROLE = Qt.UserRole + 3
FOLDER_TYPE_ROLE = Qt.UserRole + 4
FOLDER_STATUS_ROLE = Qt.UserRole + 5
FOLDER_STATUS_ICON_ROLE = Qt.UserRole + 6
FOLDER_PATH_FILTER_ROLE = Qt.UserRole + 7
FOLDERS_MODEL_SENDER_NAME = "qt_folders_model"

# Plain ints for the hot loops. PySide6 enums are Python enums and every
#   'Qt.DisplayRole' attribute access or arithmetic on them costs
#   microseconds, which adds up to a lot over thousands of items.
_ID_ROLE = int(FOLDER_ID_ROLE)
_NAME_ROLE = int(FOLDER_NAME_ROLE)
_PATH_ROLE = int(FOLDER_PATH_ROLE)
_TYPE_ROLE = int(FOLDER_TYPE_ROLE)
_STATUS_ROLE = int(FOLDER_STATUS_ROLE)
_STATUS_ICON_ROLE = int(FOLDER_STATUS_ICON_ROLE)
_FILTER_ROLE = int(FOLDER_PATH_FILTER_ROLE)
_DISPLAY_ROLE = int(Qt.DisplayRole)
_DECORATION_ROLE = int(Qt.DecorationRole)
_TOOLTIP_ROLE = int(Qt.ToolTipRole)
_ITEM_FLAGS = Qt.ItemIsEnabled | Qt.ItemIsSelectable

# Refreshes changing more rows than this are applied as a full rebuild.
#   Inserting rows one by one into a live model (with a sorting proxy
#   and a view attached) scales badly, a rebuild does not.
_MAX_INCREMENTAL_CHANGES = 500


class BrowserFoldersProxyModel(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()

        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setRecursiveFilteringEnabled(True)

        self._folder_ids_filter = None
        self._name_filter_terms = []

    def set_name_filter(self, name: str) -> None:
        self._name_filter_terms = name.casefold().split()
        self.invalidateFilter()

    def _match_name_filter(self, source_index) -> bool:
        if not self._name_filter_terms:
            return True
        folder_path_filter = source_index.data(FOLDER_PATH_FILTER_ROLE)
        if not folder_path_filter:
            return False
        return all(
            term in folder_path_filter for term in self._name_filter_terms
        )

    def set_folder_ids_filter(self, folder_ids: set[str] | None):
        if self._folder_ids_filter == folder_ids:
            return
        self._folder_ids_filter = folder_ids
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent_index):
        if self._folder_ids_filter is None and not self._name_filter_terms:
            return True

        source_index = self.sourceModel().index(row, 0, parent_index)
        if self._folder_ids_filter is not None:
            if not self._folder_ids_filter:
                return False
            folder_id = source_index.data(FOLDER_ID_ROLE)
            if folder_id not in self._folder_ids_filter:
                return False

        return self._match_name_filter(source_index)


@dataclass
class _FoldersSnapshot:
    """Data the model currently shows. Never mutated once created.

    Worker threads compare against it to compute what changed, so a new
    snapshot is always created instead of changing an existing one.
    """
    folder_items_by_id: dict[str, FolderItem] = field(default_factory=dict)
    label_path_by_id: dict[str, str] = field(default_factory=dict)
    folder_type_items: list[FolderTypeItem] = field(default_factory=list)
    status_items: list[StatusItem] = field(default_factory=list)


@dataclass
class _BuiltTree:
    """Detached item tree created in a worker thread."""
    root_rows: list[list[QStandardItem]]
    items_by_id: dict[str, QStandardItem]
    status_items_by_id: dict[str, QStandardItem]


@dataclass
class _FoldersDiff:
    """Changes between the snapshot the model shows and new data.

    All id lists are ordered parents first.
    """
    added_ids: list[str]
    moved_ids: list[str]
    removed_ids: list[str]
    changed_ids: list[str]

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_ids
            or self.moved_ids
            or self.removed_ids
            or self.changed_ids
        )

    @property
    def size(self) -> int:
        return (
            len(self.added_ids)
            + len(self.moved_ids)
            + len(self.removed_ids)
            + len(self.changed_ids)
        )


@dataclass
class _FetchResult:
    project_name: str
    snapshot: _FoldersSnapshot
    # Snapshot the diff (if any) was computed against.
    base_snapshot: _FoldersSnapshot
    diff: Optional[_FoldersDiff] = None
    tree: Optional[_BuiltTree] = None


def _create_row(
    folder_item: FolderItem,
    label_path: str,
) -> tuple[QStandardItem, QStandardItem]:
    """Create detached items for one folder row, without icons."""
    item = QStandardItem(folder_item.label)
    item.setFlags(_ITEM_FLAGS)
    _set_item_data(item, folder_item, label_path)

    status_item = QStandardItem()
    status_item.setFlags(_ITEM_FLAGS)
    status_item.setData(folder_item.entity_id, _ID_ROLE)
    status_item.setData(folder_item.status, _TOOLTIP_ROLE)
    return item, status_item


def _set_item_data(
    item: QStandardItem,
    folder_item: FolderItem,
    label_path: str,
) -> None:
    item.setData(folder_item.entity_id, _ID_ROLE)
    item.setData(folder_item.name, _NAME_ROLE)
    item.setData(folder_item.path, _PATH_ROLE)
    item.setData(folder_item.folder_type, _TYPE_ROLE)
    item.setData(folder_item.status, _STATUS_ROLE)
    item.setData(
        f"{folder_item.path} {label_path}".casefold(), _FILTER_ROLE
    )


def _walk_hierarchy(
    folder_items_by_id: dict[str, FolderItem],
) -> tuple[list[str], dict[str, str]]:
    """Walk hierarchy from the project root, parents first.

    Folders whose parent is not available are skipped, same as their
    children.

    Returns:
        tuple: Folder ids in breadth-first order and label path by
            folder id.
    """
    children_by_parent = defaultdict(list)
    for folder_id, folder_item in folder_items_by_id.items():
        children_by_parent[folder_item.parent_id].append(folder_id)

    ordered_ids = []
    label_path_by_id = {}
    queue = [(None, "")]
    for parent_id, parent_path in queue:
        for folder_id in children_by_parent.get(parent_id, ()):
            label_path = (
                f"{parent_path}/{folder_items_by_id[folder_id].label}"
            )
            label_path_by_id[folder_id] = label_path
            ordered_ids.append(folder_id)
            queue.append((folder_id, label_path))
    return ordered_ids, label_path_by_id


def _build_tree(
    folder_items_by_id: dict[str, FolderItem],
    ordered_ids: list[str],
    label_path_by_id: dict[str, str],
) -> _BuiltTree:
    """Build detached item tree. Safe to call from a worker thread."""
    items_by_id = {}
    status_items_by_id = {}
    root_rows = []
    for folder_id in ordered_ids:
        folder_item = folder_items_by_id[folder_id]
        item, status_item = _create_row(
            folder_item, label_path_by_id[folder_id]
        )
        items_by_id[folder_id] = item
        status_items_by_id[folder_id] = status_item
        # Parents are always created first. Appending to a detached
        #   parent is cheap as there is no model to notify.
        parent_id = folder_item.parent_id
        if parent_id is None:
            root_rows.append([item, status_item])
        else:
            items_by_id[parent_id].appendRow([item, status_item])
    return _BuiltTree(root_rows, items_by_id, status_items_by_id)


def _compute_diff(
    base: _FoldersSnapshot,
    new: _FoldersSnapshot,
    ordered_ids: list[str],
) -> _FoldersDiff:
    old_items = base.folder_items_by_id
    old_label_paths = base.label_path_by_id
    new_items = new.folder_items_by_id
    new_label_paths = new.label_path_by_id

    added_ids = []
    moved_ids = []
    changed_ids = []
    for folder_id in ordered_ids:
        old_item = old_items.get(folder_id)
        if old_item is None or folder_id not in old_label_paths:
            added_ids.append(folder_id)
            continue
        new_item = new_items[folder_id]
        if old_item.parent_id != new_item.parent_id:
            moved_ids.append(folder_id)
        if (
            old_item != new_item
            or old_label_paths[folder_id] != new_label_paths[folder_id]
        ):
            changed_ids.append(folder_id)

    removed_ids = [
        folder_id
        for folder_id in old_label_paths
        if folder_id not in new_label_paths
    ]
    return _FoldersDiff(added_ids, moved_ids, removed_ids, changed_ids)


class BrowserFoldersModel(QStandardItemModel):
    """Folders model which cares about refresh of folders.

    The model contains both **Folders** and **Status** columns.
    Visibility of the status column is controlled by the view.

    Args:
        ui_controller: Browser widget controller.
        controller: The control object providing folder items.
    """
    loading_changed = Signal(bool)

    FILTER_ROLE = FOLDER_PATH_FILTER_ROLE

    def __init__(self, ui_controller, controller):
        super().__init__()

        self.setColumnCount(2)
        self.setHeaderData(0, Qt.Horizontal, "Folders")
        self.setHeaderData(1, Qt.Horizontal, "")

        self._ui_controller = ui_controller
        self._controller = controller
        self._items_by_id: dict[str, QStandardItem] = {}
        self._status_items_by_id: dict[str, QStandardItem] = {}
        self._snapshot = _FoldersSnapshot()

        self._last_project_name = None
        self._context_id: str = f"folders_model_{id(self)}"
        self._generation = 0
        self._pending_task: Optional[AsyncTask] = None
        self._is_loading = False

    def is_loading(self) -> bool:
        return self._is_loading

    def reset(self):
        """Refresh folders for last selected project.

        Force to update folders model from controller. This may or may not
        trigger query from server, that's based on controller's cache.
        """
        self._generation += 1
        if self._pending_task is not None:
            self._pending_task.cancel()
            self._pending_task = None

        project_name = self._ui_controller.current_project
        if not project_name:
            self._last_project_name = project_name
            self._clear_items()
            self._set_loading(False)
            return

        if self._last_project_name != project_name:
            self._clear_items()
        self._last_project_name = project_name

        generation = self._generation
        base_snapshot = self._snapshot
        task = AsyncTask(
            name="fetch_all_folders",
            function=lambda: self._fetch_folders_data(
                project_name, base_snapshot
            ),
            callback=lambda result: self._on_data_fetched(
                generation, result
            ),
            # Folders are the entry point of the browser, load them
            #   before anything else waiting in the queue.
            priority=1,
            context_id=self._context_id,
            cancellable=True,
        )
        self._pending_task = task
        self._set_loading(True)
        get_task_queue().enqueue(task)

    def get_index_by_id(self, item_id):
        """Get index by folder id.

        Returns:
            QModelIndex: Index of the folder. Can be invalid if folder
                is not available.
        """
        item = self._items_by_id.get(item_id)
        if item is None:
            return QModelIndex()
        return self.indexFromItem(item)

    def _set_loading(self, is_loading: bool) -> None:
        if self._is_loading == is_loading:
            return
        self._is_loading = is_loading
        self.loading_changed.emit(is_loading)

    def _clear_items(self):
        self._snapshot = _FoldersSnapshot()
        if not self._items_by_id:
            return
        self.beginResetModel()
        self._items_by_id = {}
        self._status_items_by_id = {}
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())
        self.endResetModel()

    def _fetch_folders_data(
        self,
        project_name: str,
        base_snapshot: _FoldersSnapshot,
    ) -> _FetchResult:
        """Fetch folders and prepare everything possible off the GUI thread.

        Runs in a worker thread. Must not touch the model.
        """
        folder_items_by_id = self._controller.get_folder_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        ) or {}
        folder_type_items = self._controller.get_folder_type_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        status_items = self._controller.get_project_status_items(
            project_name, sender=FOLDERS_MODEL_SENDER_NAME
        )
        ordered_ids, label_path_by_id = _walk_hierarchy(
            folder_items_by_id
        )
        snapshot = _FoldersSnapshot(
            folder_items_by_id,
            label_path_by_id,
            list(folder_type_items),
            list(status_items),
        )
        result = _FetchResult(
            project_name=project_name,
            snapshot=snapshot,
            base_snapshot=base_snapshot,
        )

        # Icons of all items would change -> rebuild
        icons_changed = (
            base_snapshot.folder_type_items != snapshot.folder_type_items
            or base_snapshot.status_items != snapshot.status_items
        )
        if base_snapshot.label_path_by_id and not icons_changed:
            diff = _compute_diff(base_snapshot, snapshot, ordered_ids)
            if diff.size <= _MAX_INCREMENTAL_CHANGES:
                result.diff = diff
                return result

        result.tree = _build_tree(
            folder_items_by_id, ordered_ids, label_path_by_id
        )
        return result

    def _on_data_fetched(
        self,
        generation: int,
        result: Optional[_FetchResult],
    ) -> None:
        """Apply fetched data on the main thread.

        Results of outdated requests are ignored.

        Args:
            generation: Generation of the request.
            result: Prepared data from worker thread. 'None' if the fetch
                failed.
        """
        if generation != self._generation:
            return

        self._pending_task = None
        try:
            if result is None:
                return
            if result.project_name != self._last_project_name:
                return
            if result.base_snapshot is not self._snapshot:
                # Model changed while fetching, should not happen as every
                #   change bumps the generation, but be safe.
                self.reset()
                return
            if result.tree is not None:
                self._apply_tree(result.tree, result.snapshot)
            elif result.diff is not None:
                self._apply_diff(result.diff, result.snapshot)
        finally:
            if self._pending_task is None:
                self._set_loading(False)

    def _get_icons(
        self,
        snapshot: _FoldersSnapshot,
    ) -> tuple[dict[str, QIcon], dict[str, QIcon | None]]:
        """Create icons for folder types and statuses.

        Must be called on the main thread.
        """
        default_color = get_default_entity_icon_color()
        type_icons = {}
        for folder_type in snapshot.folder_type_items:
            type_icons[folder_type.name] = get_qt_icon(MaterialSymbolsIcon(
                folder_type.icon or "folder",
                color=folder_type.color or default_color,
            ))
        type_icons[None] = get_qt_icon(MaterialSymbolsIcon(
            "folder", color=default_color
        ))

        status_icons = {}
        for status in snapshot.status_items:
            icon = None
            if status.icon:
                icon = get_qt_icon(
                    MaterialSymbolsIcon(status.icon, color=status.color)
                )
            status_icons[status.name] = icon
        return type_icons, status_icons

    def _set_row_icons(
        self,
        folder_item: FolderItem,
        item: QStandardItem,
        status_item: QStandardItem,
        type_icons: dict[str, QIcon],
        status_icons: dict[str, QIcon | None],
    ) -> None:
        icon = type_icons.get(folder_item.folder_type)
        if icon is None:
            icon = type_icons[None]
        item.setData(icon, _DECORATION_ROLE)
        status_icon = status_icons.get(folder_item.status)
        item.setData(status_icon, _STATUS_ICON_ROLE)
        status_item.setData(status_icon, _DECORATION_ROLE)

    def _apply_tree(
        self,
        tree: _BuiltTree,
        snapshot: _FoldersSnapshot,
    ) -> None:
        type_icons, status_icons = self._get_icons(snapshot)
        folder_items_by_id = snapshot.folder_items_by_id
        status_items_by_id = tree.status_items_by_id
        # Items are still detached, setting data does not emit anything
        for folder_id, item in tree.items_by_id.items():
            self._set_row_icons(
                folder_items_by_id[folder_id],
                item,
                status_items_by_id[folder_id],
                type_icons,
                status_icons,
            )

        self.beginResetModel()
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())
        for row in tree.root_rows:
            root_item.appendRow(row)
        self._items_by_id = tree.items_by_id
        self._status_items_by_id = tree.status_items_by_id
        self._snapshot = snapshot
        self.endResetModel()

    def _apply_diff(
        self,
        diff: _FoldersDiff,
        snapshot: _FoldersSnapshot,
    ) -> None:
        """Apply changes in place, keeping view state untouched."""
        if diff.is_empty:
            self._snapshot = snapshot
            return

        folder_items_by_id = snapshot.folder_items_by_id
        label_path_by_id = snapshot.label_path_by_id
        old_parent_by_id = {
            folder_id: folder_item.parent_id
            for folder_id, folder_item in (
                self._snapshot.folder_items_by_id.items()
            )
        }
        root_item = self.invisibleRootItem()

        # Detach moved and removed rows. Moved rows are taken first so
        #   they are not destroyed with a removed ancestor. Taken rows
        #   keep their children.
        detached_rows: dict[str, list[QStandardItem]] = {}
        removed_ids = set(diff.removed_ids)
        for folder_id in diff.moved_ids + diff.removed_ids:
            if (
                folder_id in removed_ids
                and old_parent_by_id.get(folder_id) in removed_ids
            ):
                # Goes away with its parent
                continue
            item = self._items_by_id[folder_id]
            parent_item = item.parent() or root_item
            detached_rows[folder_id] = parent_item.takeRow(item.row())

        for folder_id in diff.removed_ids:
            self._items_by_id.pop(folder_id, None)
            self._status_items_by_id.pop(folder_id, None)

        type_icons, status_icons = self._get_icons(snapshot)
        for folder_id in diff.changed_ids:
            folder_item = folder_items_by_id[folder_id]
            item = self._items_by_id[folder_id]
            status_item = self._status_items_by_id[folder_id]
            item.setData(folder_item.label, _DISPLAY_ROLE)
            _set_item_data(item, folder_item, label_path_by_id[folder_id])
            status_item.setData(folder_item.status, _TOOLTIP_ROLE)
            self._set_row_icons(
                folder_item, item, status_item, type_icons, status_icons
            )

        added_ids = set(diff.added_ids)
        for folder_id in diff.added_ids:
            folder_item = folder_items_by_id[folder_id]
            item, status_item = _create_row(
                folder_item, label_path_by_id[folder_id]
            )
            self._set_row_icons(
                folder_item, item, status_item, type_icons, status_icons
            )
            self._items_by_id[folder_id] = item
            self._status_items_by_id[folder_id] = status_item
            detached_rows[folder_id] = [item, status_item]

        # Build new subtrees while detached, then attach them to the model
        #   so the model emits as few signals as possible.
        to_place = [
            folder_id
            for folder_id in diff.added_ids + diff.moved_ids
            if folder_id in detached_rows
        ]
        to_attach = []
        for folder_id in to_place:
            parent_id = folder_items_by_id[folder_id].parent_id
            if parent_id in added_ids:
                self._items_by_id[parent_id].appendRow(
                    detached_rows[folder_id]
                )
            else:
                to_attach.append(folder_id)

        for folder_id in to_attach:
            parent_id = folder_items_by_id[folder_id].parent_id
            parent_item = (
                root_item if parent_id is None
                else self._items_by_id[parent_id]
            )
            parent_item.appendRow(detached_rows[folder_id])

        self._snapshot = snapshot
