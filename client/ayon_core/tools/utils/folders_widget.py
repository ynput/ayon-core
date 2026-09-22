from __future__ import annotations

import collections
import typing
from dataclasses import dataclass, field
from typing import Optional

from qtpy import QtWidgets, QtGui, QtCore

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.lib.icon_definitions import (
    AwesomeFontIcon,
    MaterialSymbolsIcon,
)
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.common_models import (
    ProjectsModel,
    HierarchyModel,
    HierarchyExpectedSelection,
)
from ayon_core.ui.components import (
    AYButton,
    AYLineEdit,
    AYTreeView
)
from ayon_core.ui.components.async_loader import AsyncLoader

from ayon_core.ui.style_types import get_ayon_style
from ayon_core.ui.variants import QTreeViewVariants
from ayon_core.ui.components.tree_view import CenteredIconDelegate

from .models import RecursiveSortFilterProxyModel
from .lib import get_qt_icon

if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models import (
        FolderItem,
        FolderTypeItem,
        StatusItem,
    )

FOLDERS_MODEL_SENDER_NAME = "qt_folders_model"
FOLDER_ID_ROLE = QtCore.Qt.UserRole + 1
FOLDER_NAME_ROLE = QtCore.Qt.UserRole + 2
FOLDER_PATH_ROLE = QtCore.Qt.UserRole + 3
FOLDER_TYPE_ROLE = QtCore.Qt.UserRole + 4
FOLDER_PATH_FILTER_ROLE = QtCore.Qt.UserRole + 6
FOLDER_STATUS_ROLE = QtCore.Qt.UserRole + 7
FOLDER_STATUS_ICON_ROLE = QtCore.Qt.UserRole + 8


# Plain ints for the hot loops. PySide6 enums are Python enums and every
#   'Qt.DisplayRole' attribute access or arithmetic on them costs
#   microseconds, which adds up to a lot over thousands of items.
_ID_ROLE = int(FOLDER_ID_ROLE)
_NAME_ROLE = int(FOLDER_NAME_ROLE)
_PATH_ROLE = int(FOLDER_PATH_ROLE)
_TYPE_ROLE = int(FOLDER_TYPE_ROLE)
_FILTER_ROLE = int(FOLDER_PATH_FILTER_ROLE)
_STATUS_ROLE = int(FOLDER_STATUS_ROLE)
_STATUS_ICON_ROLE = int(FOLDER_STATUS_ICON_ROLE)
_DISPLAY_ROLE = int(QtCore.Qt.DisplayRole)
_DECORATION_ROLE = int(QtCore.Qt.DecorationRole)
_TOOLTIP_ROLE = int(QtCore.Qt.ToolTipRole)
_ITEM_FLAGS = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

# Refreshes changing more rows than this are applied as a full rebuild.
#   Inserting rows one by one into a live model (with a sorting proxy
#   and a view attached) scales badly, a rebuild does not.
_MAX_INCREMENTAL_CHANGES = 500


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
    root_rows: list[list[QtGui.QStandardItem]]
    items_by_id: dict[str, QtGui.QStandardItem]
    status_items_by_id: dict[str, QtGui.QStandardItem]


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
    # Snapshot the diff (if any) was computed against
    base_snapshot: _FoldersSnapshot
    diff: Optional[_FoldersDiff] = None
    tree: Optional[_BuiltTree] = None


def _set_item_data(
    item: QtGui.QStandardItem,
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


def _create_row(
    folder_item: FolderItem,
    label_path: str,
) -> list[QtGui.QStandardItem]:
    """Create detached items for one folder row, without icons."""
    item = QtGui.QStandardItem(folder_item.label)
    item.setFlags(_ITEM_FLAGS)
    _set_item_data(item, folder_item, label_path)

    # Status column, same user data as the folder column
    status_item = QtGui.QStandardItem()
    status_item.setFlags(_ITEM_FLAGS)
    _set_item_data(status_item, folder_item, label_path)
    status_item.setData(folder_item.status, _TOOLTIP_ROLE)
    return [item, status_item]


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
    children_by_parent = collections.defaultdict(list)
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
        row = _create_row(folder_item, label_path_by_id[folder_id])
        items_by_id[folder_id] = row[0]
        status_items_by_id[folder_id] = row[1]
        # Parents are always created first. Appending to a detached
        #   parent is cheap as there is no model to notify.
        parent_id = folder_item.parent_id
        if parent_id is None:
            root_rows.append(row)
        else:
            items_by_id[parent_id].appendRow(row)
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


class FoldersQtModel(QtGui.QStandardItemModel):
    """Folders model which cares about refresh of folders.

    Folders are loaded with 'AsyncLoader', see the UI data loading standard
    in 'ayon_core.ui.components.async_loader'. Server query, hierarchy walk
    and creation of the item tree happen in a worker thread. A refresh of
    the same project applies only changes, which keeps expanded and
    selected state in views.

    The model contains both **Folders** and **Status** columns.
    Visibility of the status column is controlled by the view.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
    """
    _default_folder_icon = None
    refreshed = QtCore.Signal()
    loading_changed = QtCore.Signal(bool)

    def __init__(self, controller):
        super().__init__()

        self.setColumnCount(2)
        self.setHeaderData(0, QtCore.Qt.Horizontal, "Folders")
        self.setHeaderData(1, QtCore.Qt.Horizontal, "")

        loader = AsyncLoader("folders", priority=1, parent=self)
        loader.loading_changed.connect(self.loading_changed)

        self._controller = controller
        self._loader = loader
        self._items_by_id: dict[str, QtGui.QStandardItem] = {}
        self._status_items_by_id: dict[str, QtGui.QStandardItem] = {}
        self._snapshot = _FoldersSnapshot()
        self._last_project_name = None

        self._has_content = False
        self._is_refreshing = False

    @property
    def is_refreshing(self):
        """Model is refreshing.

        Returns:
            bool: True if model is refreshing.
        """
        return self._is_refreshing

    @property
    def has_content(self):
        """Has at least one folder.

        Returns:
            bool: True if model has at least one folder.
        """

        return self._has_content

    def is_loading(self) -> bool:
        """Folders are being loaded."""
        return self._loader.is_loading()

    def refresh(self):
        """Refresh folders for last selected project.

        Force to update folders model from controller. This may or may not
        trigger query from server, that's based on controller's cache.
        """

        self.set_project_name(self._last_project_name)

    def get_index_by_id(self, item_id):
        """Get index by folder id.

        Returns:
            QtCore.QModelIndex: Index of the folder. Can be invalid if folder
                is not available.
        """
        item = self._items_by_id.get(item_id)
        if item is None:
            return QtCore.QModelIndex()
        return self.indexFromItem(item)

    def get_item_id_by_path(self, folder_path):
        """Get folder id by path.

        Args:
            folder_path (str): Folder path.

        Returns:
            Union[str, None]: Folder id or None if folder is not available.

        """
        folder_items_by_id = self._snapshot.folder_items_by_id
        for folder_id in self._items_by_id:
            if folder_items_by_id[folder_id].path == folder_path:
                return folder_id
        return None

    def get_project_name(self):
        """Project name which model currently use.

        Returns:
            Union[str, None]: Currently used project name.
        """

        return self._last_project_name

    def set_project_name(self, project_name):
        """Refresh folders items.

        Data are loaded in a worker thread because the controller may
        query the server if folders are not cached.
        """

        if not project_name:
            self._loader.cancel()
            self._last_project_name = project_name
            self._clear_items()
            self._is_refreshing = False
            self.refreshed.emit()
            return

        self._is_refreshing = True

        if self._last_project_name != project_name:
            self._clear_items()
        self._last_project_name = project_name

        base_snapshot = self._snapshot
        self._loader.request(
            lambda: self._fetch_data(project_name, base_snapshot),
            self._on_data_fetched,
            self._on_fetch_failed,
        )

    @classmethod
    def _get_default_folder_icon(cls):
        if cls._default_folder_icon is None:
            cls._default_folder_icon = get_qt_icon(
                AwesomeFontIcon(
                    "fa.folder",
                    color=get_default_entity_icon_color(),
                )
            )
        return cls._default_folder_icon

    def _clear_items(self):
        self._snapshot = _FoldersSnapshot()
        self._has_content = False
        if not self._items_by_id:
            return
        self.beginResetModel()
        self._items_by_id = {}
        self._status_items_by_id = {}
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())
        self.endResetModel()

    def _get_fetch_items(self, project_name):
        """Get data from controller. Called in a worker thread.

        Returns:
            tuple[dict[str, FolderItem], list[FolderTypeItem],
                list[StatusItem]]: Folder items by id, folder type items
                and status items.
        """
        folder_items = self._controller.get_folder_items(
            project_name, FOLDERS_MODEL_SENDER_NAME
        )
        folder_type_items = []
        if hasattr(self._controller, "get_folder_type_items"):
            folder_type_items = self._controller.get_folder_type_items(
                project_name, FOLDERS_MODEL_SENDER_NAME
            )

        status_items = []
        if hasattr(self._controller, "get_project_status_items"):
            status_items = self._controller.get_project_status_items(
                project_name, sender=FOLDERS_MODEL_SENDER_NAME
            )
        return folder_items, folder_type_items, status_items

    def _fetch_data(
        self,
        project_name: str,
        base_snapshot: _FoldersSnapshot,
    ) -> _FetchResult:
        """Fetch folders and prepare everything possible off the UI thread.

        Runs in a worker thread. Must not touch the model.
        """
        (
            folder_items_by_id, folder_type_items, status_items
        ) = self._get_fetch_items(project_name)
        folder_items_by_id = folder_items_by_id or {}
        ordered_ids, label_path_by_id = _walk_hierarchy(folder_items_by_id)
        snapshot = _FoldersSnapshot(
            folder_items_by_id,
            label_path_by_id,
            list(folder_type_items or []),
            list(status_items or []),
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

    def _on_data_fetched(self, result: _FetchResult) -> None:
        if result.project_name != self._last_project_name:
            return
        if result.base_snapshot is not self._snapshot:
            # Model changed while fetching, fetch again
            self.refresh()
            return
        if result.tree is not None:
            self._apply_tree(result.tree, result.snapshot)
        else:
            self._apply_diff(result.diff, result.snapshot)
        self._has_content = bool(self._items_by_id)
        self._is_refreshing = False
        self.refreshed.emit()

    def _on_fetch_failed(self, exc: BaseException) -> None:
        # Keep showing what is already there
        self._is_refreshing = False
        self.refreshed.emit()

    def _get_icons(
        self,
        snapshot: _FoldersSnapshot,
    ) -> tuple[dict[str, QtGui.QIcon], dict[str, Optional[QtGui.QIcon]]]:
        """Create icons for folder types and statuses.

        Must be called on the UI thread.
        """
        default_color = get_default_entity_icon_color()
        type_icons = {}
        for folder_type in snapshot.folder_type_items:
            if folder_type.icon:
                type_icons[folder_type.name] = get_qt_icon(
                    MaterialSymbolsIcon(
                        folder_type.icon,
                        color=folder_type.color or default_color,
                    )
                )

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
        item: QtGui.QStandardItem,
        status_item: QtGui.QStandardItem,
        type_icons: dict[str, QtGui.QIcon],
        status_icons: dict[str, Optional[QtGui.QIcon]],
    ) -> None:
        icon = type_icons.get(folder_item.folder_type)
        if icon is None:
            icon = self._get_default_folder_icon()
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
        if not diff.size:
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
        detached_rows: dict[str, list[QtGui.QStandardItem]] = {}
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
            label_path = label_path_by_id[folder_id]
            item = self._items_by_id[folder_id]
            status_item = self._status_items_by_id[folder_id]
            item.setData(folder_item.label, _DISPLAY_ROLE)
            _set_item_data(item, folder_item, label_path)
            _set_item_data(status_item, folder_item, label_path)
            status_item.setData(folder_item.status, _TOOLTIP_ROLE)
            self._set_row_icons(
                folder_item, item, status_item, type_icons, status_icons
            )

        added_ids = set(diff.added_ids)
        for folder_id in diff.added_ids:
            folder_item = folder_items_by_id[folder_id]
            row = _create_row(folder_item, label_path_by_id[folder_id])
            self._set_row_icons(
                folder_item, row[0], row[1], type_icons, status_icons
            )
            self._items_by_id[folder_id] = row[0]
            self._status_items_by_id[folder_id] = row[1]
            detached_rows[folder_id] = row

        # Build new subtrees while detached, then attach them to the model
        #   so the model emits as few signals as possible.
        to_attach = []
        for folder_id in diff.added_ids + diff.moved_ids:
            if folder_id not in detached_rows:
                continue
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


class FoldersProxyModel(RecursiveSortFilterProxyModel):
    def __init__(self):
        super().__init__()

        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

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

    def set_folder_ids_filter(self, folder_ids: Optional[list[str]]):
        if self._folder_ids_filter == folder_ids:
            return
        self._folder_ids_filter = folder_ids
        self.invalidateFilter()

    def filterAcceptsRow(self, row, parent_index):
        # Fast path, this is called for every row the proxy maps
        if (
            self._folder_ids_filter is None
            and not self._name_filter_terms
            and not self.has_filter_pattern()
        ):
            return True

        source_index = self.sourceModel().index(row, 0, parent_index)
        if self._folder_ids_filter is not None:
            if not self._folder_ids_filter:
                return False
            folder_id = source_index.data(FOLDER_ID_ROLE)
            if folder_id not in self._folder_ids_filter:
                return False

        if not self._match_name_filter(source_index):
            return False

        return super().filterAcceptsRow(row, parent_index)


class FoldersWidget(QtWidgets.QWidget):
    """Folders widget.

    Widget that handles folders view, model and selection.

    Expected selection handling is disabled by default. If enabled, the
    widget will handle the expected in predefined way. Widget is listening
    to event 'expected_selection_changed' with expected event data below,
    the same data must be available when called method
    'get_expected_selection_data' on controller.

    {
        "folder": {
            "current": bool,               # Folder is what should be set now
            "folder_id": Union[str, None], # Folder id that should be selected
        },
        ...
    }

    Selection is confirmed by calling method 'expected_folder_selected' on
    controller.


    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        parent (QtWidgets.QWidget): The parent widget.
        handle_expected_selection (bool): If True, the widget will handle
            the expected selection. Defaults to False.
    """

    double_clicked = QtCore.Signal(QtGui.QMouseEvent)
    selection_changed = QtCore.Signal()
    refreshed = QtCore.Signal()

    def __init__(
        self,
        controller,
        parent,
        handle_expected_selection=False,
    ):
        super().__init__(parent)

        folders_view = AYTreeView(self)
        folders_view.setSelectionMode(AYTreeView.SelectionMode.SingleSelection)

        folders_model = FoldersQtModel(controller)
        folders_proxy_model = FoldersProxyModel()
        folders_proxy_model.setSourceModel(folders_model)
        folders_proxy_model.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)

        folders_view.setModel(folders_proxy_model)

        header = folders_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.ResizeMode.Stretch
        )
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeMode.Fixed
        )
        header.resizeSection(1, 30)
        folders_view.setColumnHidden(1, True)
        folders_view.setItemDelegateForColumn(
            1,
            CenteredIconDelegate(
                parent=folders_view,
                style_model=get_ayon_style().model,
                variant=QTreeViewVariants.Default.value,
            )
        )

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(folders_view, 1)

        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_selection_change,
        )
        controller.register_event_callback(
            "folders.refresh.finished",
            self._on_folders_refresh_finished
        )
        controller.register_event_callback(
            "controller.refresh.finished",
            self._on_controller_refresh
        )
        controller.register_event_callback(
            "expected_selection_changed",
            self._on_expected_selection_change
        )

        selection_model = folders_view.selectionModel()
        selection_model.selectionChanged.connect(self._on_selection_change)
        folders_view.double_clicked.connect(self.double_clicked)
        folders_model.refreshed.connect(self._on_model_refresh)
        folders_model.loading_changed.connect(folders_view.set_loading)

        self._controller = controller
        self._folders_view = folders_view
        self._folders_model = folders_model
        self._folders_proxy_model = folders_proxy_model

        self._handle_expected_selection = handle_expected_selection
        self._expected_selection = None

    @property
    def is_refreshing(self):
        """Model is refreshing.

        Returns:
            bool: True if model is refreshing.
        """

        return self._folders_model.is_refreshing

    @property
    def has_content(self):
        """Has at least one folder.

        Returns:
            bool: True if model has at least one folder.
        """

        return self._folders_model.has_content

    def set_name_filter(self, name):
        """Set filter of folder name.

        Args:
            name (str): The string filter.
        """

        self._folders_proxy_model.set_name_filter(name)
        if name:
            self._folders_view.expandAll()

    def set_folder_ids_filter(self, folder_ids: Optional[list[str]]):
        """Set filter of folder ids.

        Args:
            folder_ids (list[str]): The list of folder ids.

        """
        self._folders_proxy_model.set_folder_ids_filter(folder_ids)

    def set_loading_delay(self, delay: int):
        """Delay before loading placeholder shows in the folders view.

        Args:
            delay (int): Delay in milliseconds.

        """
        self._folders_view.set_loading_delay(delay)

    def set_header_visible(self, visible: bool):
        self._folders_view.setHeaderHidden(not visible)

    def set_status_column_visible(self, visible: bool):
        self._folders_view.setColumnHidden(1, not visible)

    def refresh(self):
        """Refresh folders model.

        Force to update folders model from controller.
        """

        self._folders_model.refresh()

    def get_project_name(self):
        """Project name in which folders widget currently is.

        Returns:
            Union[str, None]: Currently used project name.
        """

        return self._folders_model.get_project_name()

    def set_project_name(self, project_name):
        """Set project name.

        Do not use this method when controller is handling selection of
        project using 'selection.project.changed' event.

        Args:
            project_name (str): Project name.
        """

        self._folders_model.set_project_name(project_name)

    def get_selected_folder_id(self):
        """Get selected folder id.

        Returns:
            Union[str, None]: Folder id which is selected.
        """

        return self._get_selected_item_id()

    def get_selected_folder_path(self):
        """Get selected folder id.

        Returns:
            Union[str, None]: Folder path which is selected.
        """

        return self._get_selected_item_value(FOLDER_PATH_ROLE)

    def get_selected_folder_label(self):
        """Selected folder label.

        Returns:
            Union[str, None]: Selected folder label.
        """

        item_id = self._get_selected_item_id()
        return self.get_folder_label(item_id)

    def get_folder_label(self, folder_id):
        """Folder label for a given folder id.

        Returns:
            Union[str, None]: Folder label.
        """

        index = self._folders_model.get_index_by_id(folder_id)
        if index.isValid():
            return index.data(QtCore.Qt.DisplayRole)
        return None

    def set_selected_folder(self, folder_id):
        """Change selection.

        Args:
            folder_id (Union[str, None]): Folder id or None to deselect.

        Returns:
            bool: Requested folder was selected.
        """
        if folder_id is None:
            self._folders_view.clearSelection()
            return True

        if folder_id == self._get_selected_item_id():
            return True
        index = self._folders_model.get_index_by_id(folder_id)
        if not index.isValid():
            return False

        proxy_index = self._folders_proxy_model.mapFromSource(index)
        if not proxy_index.isValid():
            return False

        selection_model = self._folders_view.selectionModel()
        selection_model.setCurrentIndex(
            proxy_index,
            QtCore.QItemSelectionModel.ClearAndSelect
            | QtCore.QItemSelectionModel.Rows
        )
        return True

    def set_selected_folder_path(self, folder_path):
        """Set selected folder by path.

        Args:
            folder_path (str): Folder path.

        Returns:
            bool: Requested folder was selected.

        """
        if folder_path is None:
            self._folders_view.clearSelection()
            return True

        folder_id = self._folders_model.get_item_id_by_path(folder_path)
        if folder_id is None:
            return False
        return self.set_selected_folder(folder_id)

    def set_deselectable(self, enabled):
        """Set deselectable mode.

        Items in view can be deselected.

        Args:
            enabled (bool): Enable deselectable mode.
        """

        self._folders_view.set_deselectable(enabled)

    def _get_selected_index(self):
        return self._folders_model.get_index_by_id(
            self.get_selected_folder_id()
        )

    def _on_project_selection_change(self, event):
        project_name = event["project_name"]
        self.set_project_name(project_name)

    def _on_folders_refresh_finished(self, event):
        if event["sender"] != FOLDERS_MODEL_SENDER_NAME:
            self.set_project_name(event["project_name"])

    def _on_controller_refresh(self):
        self._update_expected_selection()

    def _on_model_refresh(self):
        if self._expected_selection:
            self._set_expected_selection()
        self._folders_proxy_model.sort(0)
        self.refreshed.emit()

    def _get_selected_item_id(self):
        return self._get_selected_item_value(FOLDER_ID_ROLE)

    def _get_selected_item_value(self, role):
        selection_model = self._folders_view.selectionModel()
        for index in selection_model.selectedRows():
            item_id = index.data(role)
            if item_id is not None:
                return item_id
        return None

    def _on_selection_change(self):
        item_id = self._get_selected_item_id()
        self._controller.set_selected_folder(item_id)
        self.selection_changed.emit()

    # Expected selection handling
    def _on_expected_selection_change(self, event):
        self._update_expected_selection(event.data)

    def _update_expected_selection(self, expected_data=None):
        if not self._handle_expected_selection:
            return

        if expected_data is None:
            expected_data = self._controller.get_expected_selection_data()

        folder_data = expected_data.get("folder")
        if not folder_data or not folder_data["current"]:
            return

        folder_id = folder_data["id"]
        self._expected_selection = folder_id
        if not self._folders_model.is_refreshing:
            self._set_expected_selection()

    def _set_expected_selection(self):
        if not self._handle_expected_selection:
            return

        folder_id = self._expected_selection
        self._expected_selection = None
        if folder_id is not None:
            self.set_selected_folder(folder_id)
        self._controller.expected_folder_selected(folder_id)


class SimpleSelectionModel(object):
    """Model handling selection changes.

    Triggering events:
    - "selection.project.changed"
    - "selection.folder.changed"
    """

    event_source = "selection.model"

    def __init__(self, controller):
        self._controller = controller

        self._project_name = None
        self._folder_id = None
        self._task_id = None
        self._task_name = None

    def get_selected_project_name(self):
        return self._project_name

    def set_selected_project(self, project_name):
        self._project_name = project_name
        self._controller.emit_event(
            "selection.project.changed",
            {"project_name": project_name},
            self.event_source
        )

    def get_selected_folder_id(self):
        return self._folder_id

    def set_selected_folder(self, folder_id):
        if folder_id == self._folder_id:
            return
        self._folder_id = folder_id
        self._controller.emit_event(
            "selection.folder.changed",
            {
                "project_name": self._project_name,
                "folder_id": folder_id,
            },
            self.event_source
        )


class SimpleFoldersController(object):
    def __init__(self):
        self._event_system = self._create_event_system()
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._selection_model = SimpleSelectionModel(self)
        self._expected_selection = HierarchyExpectedSelection(
            self, handle_project=False, handle_folder=True, handle_task=False
        )

    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    # Model functions
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)

    def get_expected_selection_data(self):
        self._expected_selection.get_expected_selection_data()

    def expected_folder_selected(self, folder_id):
        self._expected_selection.expected_folder_selected(folder_id)

    def _create_event_system(self):
        return QueuedEventSystem()


class SimpleFoldersWidget(FoldersWidget):
    def __init__(self, controller=None, *args, **kwargs):
        if controller is None:
            controller = SimpleFoldersController()
        super(SimpleFoldersWidget, self).__init__(controller, *args, **kwargs)

    def set_project_name(self, project_name):
        self._controller.set_selected_project(project_name)
        super(SimpleFoldersWidget, self).set_project_name(project_name)

    def _on_project_selection_change(self, event):
        """Ignore project selection change from controller.

        Only who can trigger project change is this widget with
            'set_project_name' which already cares about project change.

        Args:
            event (Event): Triggered event.
        """
        pass


class FoldersFiltersWidget(QtWidgets.QWidget):
    """Helper widget for most commonly used filters in context selection."""
    text_changed = QtCore.Signal(str)
    my_tasks_changed = QtCore.Signal(bool)

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        # TODO: fix the focus/unfoucs text color when click out of window
        # text changing to black which looking odd fix this at all AYLineEdit
        folders_filter_input = AYLineEdit(
            placeholder="Folder name filter...",
            variant=AYLineEdit.Variants.Search_Field,
            parent=self,
        )

        my_tasks_checkbox = AYButton(
            icon="assignment_ind",
            checkable=True,
            tooltip="Only show folders that have a task assigned to you.",
            parent=parent,
        )
        my_tasks_checkbox.setChecked(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(folders_filter_input, 1)
        layout.addWidget(my_tasks_checkbox, 0)

        folders_filter_input.textChanged.connect(self.text_changed)
        my_tasks_checkbox.toggled.connect(self.my_tasks_changed)

        self._folders_filter_input = folders_filter_input
        self._my_tasks_checkbox = my_tasks_checkbox

    def is_my_tasks_checked(self) -> bool:
        return self._my_tasks_checkbox.isChecked()

    def text(self) -> str:
        return self._folders_filter_input.text()

    def set_text(self, text: str) -> None:
        self._folders_filter_input.setText(text)

    def set_my_tasks_checked(self, checked: bool) -> None:
        self._my_tasks_checkbox.setChecked(checked)

    def _on_my_tasks_change(self, state: bool) -> None:
        self.my_tasks_changed.emit(state)
