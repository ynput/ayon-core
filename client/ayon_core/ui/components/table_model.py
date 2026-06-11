"""Paginated Qt table model with lazy loading support.

Tree-mode batch fetching
------------------------
When a subtree is expanded, Qt calls ``fetchMore()`` for every child node
that declares ``has_children=True``.  Those calls all arrive in the same
event-loop tick.  Without batching each call produces a separate async
task and therefore a separate server round-trip.

Supply the optional *fetch_page_batch* callback to collapse all of those
calls into a single round-trip::

    def fetch_batch(
        requests: list[BatchFetchRequest],
    ) -> dict[str | None, list[dict]]:
        # One HTTP call for all parent_ids in the batch.
        ...

The model accumulates pending fetch requests during an event-loop tick,
dispatches them as one :class:`AsyncTask` via a zero-delay
``QTimer.singleShot(0)``, and fans out the results to the per-node
``_on_page_ready`` handler when they arrive.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable
import random

from qtpy.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    Signal,  # type: ignore[attr-defined]
)
from qtpy.QtGui import QBrush, QColor

from qtmaterialsymbols import get_icon  # type: ignore

from .task_queue import AsyncTask, get_task_queue

log = logging.getLogger(__name__)


class _TableNode:
    """Internal node used by PaginatedTableModel to represent a row.

    Stores the row data dict, parent/child references, and per-node
    pagination state (used in tree mode).
    """

    __slots__ = (
        "node_id",
        "row_data",
        "parent",
        "children",
        "children_loaded",
        "current_page",
        "has_more",
        "is_fetching",
    )

    def __init__(
        self,
        node_id: str | None,
        row_data: dict[str, Any],
        parent: _TableNode | None,
    ) -> None:
        self.node_id = node_id
        self.row_data = row_data
        self.parent = parent
        self.children: list[_TableNode] = []
        self.children_loaded: bool = False
        self.current_page: int = 0
        self.has_more: bool = True
        self.is_fetching: bool = False

    @property
    def is_root(self) -> bool:
        """Return True if this node is the invisible root."""
        return self.parent is None

    @property
    def row_has_children(self) -> bool:
        """Return True if the row data declares this node as a folder."""
        return bool(self.row_data.get("has_children", False))


@dataclass
class BatchFetchRequest:
    """Describes a single child-page request within a batch fetch call.

    A list of these is passed to the optional *fetch_page_batch* callback
    of :class:`PaginatedTableModel`.  Each entry corresponds to one node
    whose children need to be fetched; the callback should return a dict
    mapping each ``parent_id`` to its list of row dicts.

    Attributes:
        page: Page number (0-based).
        page_size: Maximum number of rows to return.
        sort_key: Column key for server-side sorting, or ``None``.
        descending: ``True`` for descending sort order.
        parent_id: The ``"id"`` value of the parent row, or ``None`` for
            the invisible root (never used in batch - root is always
            fetched individually).
    """

    page: int
    page_size: int
    sort_key: str | None
    descending: bool
    parent_id: str | None


@dataclass
class TableColumn:
    """Describes a single column in a PaginatedTableModel.

    Attributes:
        key: Dictionary key used to look up cell values in row data.
        label: Display text shown in the header.
        width: Preferred column width hint in pixels. 0 means auto.
        sortable: Whether the column can be sorted by clicking the header.
        icon: Optional material icon name shown in the filter dropdown.
        tree_position: Whether the column is used for tree indentation.
        widget_factory: Optional callable ``(index, parent) -> QWidget``.
            When set, the delegate opens a persistent editor for every
            cell in this column instead of painting text/icons.  The
            factory receives the display-model ``QModelIndex`` and the
            viewport widget as ``parent``.  ``setEditorData`` is called
            automatically by Qt whenever the model emits ``dataChanged``
            for that index, so server-push updates reach the widget
            without any extra wiring.
    """

    key: str
    label: str
    width: int = 0
    sortable: bool = True
    filterable: bool = True
    icon: str | None = None
    tree_position: bool = False
    widget_factory: "Callable[[Any, Any], Any] | None" = None


class PaginatedTableModel(QAbstractItemModel):
    """A Qt model that lazily loads rows page-by-page via a callback.

    Rows are fetched on demand using Qt's canFetchMore / fetchMore
    mechanism.  Each call to fetchMore retrieves one page of data from
    the supplied ``fetch_page`` callable.

    In **flat mode** (default) the model behaves like a plain table:
    no disclosure triangles, no nesting.  In **tree mode** rows whose
    dict contains ``"has_children": True`` become expandable folders;
    expanding them triggers a fresh ``fetch_page`` call with the
    folder's ``"id"`` value passed as ``parent_id``.

    **Batch fetching** (tree mode only): when *fetch_page_batch* is
    supplied, all ``fetchMore()`` calls that arrive in the same
    event-loop tick (e.g. Qt calling ``fetchMore`` for every child of a
    just-expanded folder) are coalesced into a single
    :class:`BatchFetchRequest` list and dispatched as one async task.
    This reduces N sibling fetches from N server round-trips to one.

    Args:
        fetch_page: Callable with signature
            ``(page, page_size, sort_key, descending, parent_id) ->
            list[dict]``.  ``parent_id`` is ``None`` for root-level
            items and the row's ``"id"`` value for nested items.
        fetch_page_batch: Optional callable with signature
            ``(requests: list[BatchFetchRequest]) ->
            dict[parent_id, list[dict]]``.  When supplied, tree-mode
            child fetches are batched into a single call per event-loop
            tick instead of one call per node.  The root-level fetch
            always uses *fetch_page* and is never batched.
        columns: Column definitions.  When ``None``, columns are inferred
            from the keys of the first fetched row.
        page_size: Number of rows per page.
        no_async: When ``True``, pages are fetched synchronously on the
            main thread instead of via the :class:`AsyncTaskQueue`.
            Useful in tests to avoid worker-thread/paint-event races.
        parent: Optional parent QObject.
    """

    tree_mode_changed = Signal(bool)
    loading_changed = Signal(bool)  # True while any fetch is in-flight
    page_fetched = Signal(int, int)  # (page_number, total_root_rows_loaded)
    fetch_error = Signal(str)  # error message when a fetch fails
    pending_count_changed = Signal(int)  # number of in-flight fetch tasks

    def __init__(
        self,
        fetch_page: Callable[
            [int, int, str | None, bool, str | None], list[dict[str, Any]]
        ],
        fetch_page_batch: (
            Callable[
                [list[BatchFetchRequest]],
                dict[str | None, list[dict[str, Any]]],
            ]
            | None
        ) = None,
        columns: list[TableColumn] | None = None,
        page_size: int = 50,
        no_async: bool = False,
        parent: QObject | None = None,
    ) -> None:
        """Initialise the model and fetch the first page.

        Args:
            fetch_page: Callable
                ``(page, page_size, sort_key, descending, parent_id)
                -> list[dict]``.
            fetch_page_batch: Optional batch callable
                ``(requests: list[BatchFetchRequest]) ->
                dict[parent_id, list[dict]]``.  When provided, non-root
                child fetches are coalesced per event-loop tick.
            columns: Explicit column definitions, or ``None`` to infer.
            page_size: Rows per page.
            no_async: When ``True``, fetch pages synchronously on the
                calling thread instead of via the AsyncTaskQueue worker.
                Useful in tests to avoid worker-thread/paint-event races.
            parent: Parent QObject.
        """
        super().__init__(parent)
        self._fetch_page = fetch_page
        self._fetch_page_batch: (
            Callable[
                [list[BatchFetchRequest]],
                dict[str | None, list[dict[str, Any]]],
            ]
            | None
        ) = fetch_page_batch
        self._explicit_columns: list[TableColumn] | None = columns
        self._columns: list[TableColumn] = columns or []
        self._page_size: int = page_size
        self._sort_column: int = -1
        self._sort_order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
        self._tree_mode: bool = False
        self._tree_position: int = -1

        # Internal node tree.  _all_nodes prevents Python GC from collecting
        # nodes that are held only via QModelIndex.internalPointer().
        self._root: _TableNode = _TableNode(
            node_id=None, row_data={}, parent=None
        )
        self._all_nodes: set[_TableNode] = {self._root}

        # Async fetch state
        self._no_async: bool = no_async
        self._request_id: str = self._generate_request_id()
        self._pending_tasks: int = 0

        # Batch-fetch coalescing state (populated by _fetch_next_page when
        # _fetch_page_batch is set, consumed by _dispatch_batch).
        self._pending_batch_nodes: list[_TableNode] = []
        self._batch_scheduled: bool = False

        # Column states received by apply_settings that do not match any
        # column in the current data source.  Preserved so a subsequent
        # capture_settings() can emit them losslessly.
        self._unknown_column_states: list[Any] = []

        self._fetch_next_page(self._root)

    # Properties --------------------------------------------------------------

    @property
    def columns(self) -> list[TableColumn]:
        """Return the current column definitions.

        Returns:
            List of TableColumn instances.
        """
        return list(self._columns)

    @property
    def page_count(self) -> int:
        """Return the number of root pages fetched so far.

        Returns:
            Current root page index.
        """
        return self._root.current_page

    @property
    def is_loading(self) -> bool:
        """Return True while at least one fetch task is in-flight.

        Returns:
            True if any page fetch is currently pending or running.
        """
        return self._pending_tasks > 0

    @property
    def tree_position(self) -> int:
        """Return the current tree column index, or 0 if tree mode is off."""
        if self._tree_position == -1:
            self._tree_position = 0
            for i, col in enumerate(self._columns):
                if col.tree_position:
                    self._tree_position = i
                    break
        return self._tree_position if self._tree_mode else 0

    # QAbstractItemModel interface --------------------------------------------

    def index(  # noqa: N802
        self,
        row: int,
        column: int,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> QModelIndex:
        """Return a model index for row/column under parent.

        Args:
            row: Row number under parent.
            column: Column number.
            parent: Parent index (invalid = root).

        Returns:
            Valid QModelIndex, or invalid if out of range.
        """
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        parent_node = self._node_from_index(parent)
        if row >= len(parent_node.children):
            return QModelIndex()
        return self.createIndex(row, column, parent_node.children[row])

    def parent(  # type: ignore[override]
        self,
        index: QModelIndex | QPersistentModelIndex,
    ) -> QModelIndex:
        """Return the parent index of the given index.

        Args:
            index: Child index.

        Returns:
            Parent QModelIndex, or invalid for root-level items.
        """
        if not index.isValid():
            return QModelIndex()
        node: _TableNode = index.internalPointer()  # type: ignore[assignment]
        parent_node = node.parent
        if parent_node is None or parent_node.is_root:
            return QModelIndex()
        grandparent = parent_node.parent
        row = grandparent.children.index(parent_node)  # type: ignore[union-attr]
        return self.createIndex(row, 0, parent_node)

    def rowCount(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        """Return the number of loaded children under parent.

        Args:
            parent: Parent index (invalid = root).

        Returns:
            Number of loaded child rows.
        """
        if parent.column() > 0:
            return 0
        return len(self._node_from_index(parent).children)

    def columnCount(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> int:
        """Return the number of columns.

        Args:
            parent: Unused; column count is the same for all nodes.

        Returns:
            Number of columns.
        """
        return len(self._columns)

    def hasChildren(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> bool:
        """Return whether the node at parent has or can have children.

        Controls whether Qt draws a disclosure triangle even before
        children are loaded.

        Args:
            parent: Parent index (invalid = root).

        Returns:
            True if the node has loaded children, has more pages, or
            (in tree mode only) the row data declares ``has_children``.
        """
        node = self._node_from_index(parent)
        if node.is_root:
            return bool(node.children) or node.has_more
        if not self._tree_mode:
            return False
        if node.children_loaded:
            return bool(node.children)
        return node.row_has_children

    def canFetchMore(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> bool:
        """Return whether more rows can be fetched for parent.

        Args:
            parent: Parent index (invalid = root).

        Returns:
            ``True`` when more pages are available for this node.
        """
        node = self._node_from_index(parent)
        if node.is_root:
            return node.has_more
        if not self._tree_mode:
            return False
        if not node.row_has_children:
            return False
        if not node.children_loaded:
            return True
        return node.has_more

    def fetchMore(  # noqa: N802
        self,
        parent: QModelIndex | QPersistentModelIndex = QModelIndex(),
    ) -> None:
        """Fetch the next page of rows for parent.

        Args:
            parent: Parent index (invalid = root).
        """
        self._fetch_next_page(self._node_from_index(parent))

    def data(
        self,
        index: QModelIndex | QPersistentModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return data for the given index and role.

        Args:
            index: Model index identifying the cell.
            role: Qt item data role.

        Returns:
            Cell value appropriate for the requested role, or ``None``.
        """
        if not index.isValid():
            return None
        node: _TableNode | None = index.internalPointer()  # type: ignore[assignment]
        if node is None:
            return None
        col = index.column()
        if col < 0 or col >= len(self._columns):
            return None

        row_dict = node.row_data
        col_key = self._columns[col].key

        if role == Qt.ItemDataRole.DisplayRole:
            value = row_dict.get(col_key)
            if value is None:
                return ""
            return str(value)

        if role == Qt.ItemDataRole.DecorationRole:
            icon_key = f"{col_key}__icon"
            icon_name = row_dict.get(icon_key)
            if icon_name:
                icon_color = row_dict.get(f"{col_key}__color", "#ffffff")
                icon_fill = row_dict.get(f"{col_key}__icon_fill", False)
                return get_icon(icon_name, color=icon_color, fill=icon_fill)
            return None

        if role == Qt.ItemDataRole.ForegroundRole:
            color_key = f"{col_key}__color"
            color = row_dict.get(color_key)
            if isinstance(color, str):
                return QBrush(QColor(color))
            return None

        if role == Qt.ItemDataRole.UserRole:
            return row_dict

        return None

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        """Return header data for the given section and orientation.

        Args:
            section: Column (horizontal) or row (vertical) index.
            orientation: Header orientation.
            role: Qt item data role.

        Returns:
            Column label for horizontal DisplayRole, otherwise ``None``.
        """
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            if 0 <= section < len(self._columns):
                return self._columns[section].label
        return None

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Set the active sort column and order, then reload data.

        Sorting always resets from page 0 at all levels.

        Args:
            column: Zero-based index of the column to sort by. If out of
                range, the call is ignored.
            order: Sort order (ascending or descending).
        """
        if column < 0 or column >= len(self._columns):
            return
        self._sort_column = column
        self._sort_order = order
        self.reset_data()  # refetch page 0 using new sort

    # Public interface --------------------------------------------------------

    def set_tree_mode(self, enabled: bool) -> None:
        """Switch between flat table mode and hierarchical tree mode.

        Emits ``tree_mode_changed`` and reloads from page 0.

        Args:
            enabled: ``True`` to enable tree mode, ``False`` for flat.
        """
        if self._tree_mode == enabled:
            return
        self._tree_mode = enabled
        self.tree_mode_changed.emit(enabled)
        self.reset_data()

    def set_page(self, page: int) -> None:
        """Reset the model and begin fetching from the given page.

        Args:
            page: 0-based page number to start from.
        """
        old_request_id = self._request_id
        if not self._no_async:
            get_task_queue().clear_context_tasks(old_request_id)
        self._request_id = self._generate_request_id()
        self._pending_tasks = 0
        self._pending_batch_nodes = []
        self._batch_scheduled = False
        self.beginResetModel()
        self._root = _TableNode(node_id=None, row_data={}, parent=None)
        self._root.current_page = page
        self._all_nodes = {self._root}
        self._columns = self._explicit_columns or []
        self.endResetModel()
        # Emit loading signals *after* endResetModel so that any slot
        # connected to loading_changed observes a consistent model state.
        self._update_loading_state()
        self._fetch_next_page(self._root)

    def set_page_size(self, size: int) -> None:
        """Update the page size and reset the model from page 0.

        Args:
            size: New page size (rows per page).
        """
        self._page_size = size
        self.reset_data()

    def set_columns(self, columns: list[TableColumn]) -> None:
        """Set the columns and reset the model from page 0.

        Args:
            columns: List of columns to display.
        """
        self._explicit_columns = columns
        self.reset_data()

    def reset_data(self) -> None:
        """Reset the model and re-fetch from page 0."""
        old_request_id = self._request_id
        if not self._no_async:
            get_task_queue().clear_context_tasks(old_request_id)
        self._request_id = self._generate_request_id()
        self._pending_tasks = 0
        self._pending_batch_nodes = []
        self._batch_scheduled = False
        self.beginResetModel()
        self._root = _TableNode(node_id=None, row_data={}, parent=None)
        self._all_nodes = {self._root}
        self._columns = self._explicit_columns or []
        self.endResetModel()
        # Emit loading signals *after* endResetModel so that any slot
        # connected to loading_changed observes a consistent model state.
        self._update_loading_state()
        self._fetch_next_page(self._root)

    def apply_settings(self, settings: Any) -> None:
        """Apply a :class:`ViewSettings` to this model.

        Reorders, hides and resizes columns by *key* (matching against
        ``TableColumn.key``), then sets the active sort.  All changes
        are batched into a single :meth:`reset_data` call so the model
        only refetches page 0 once.

        Hidden columns are kept in the model so the header can toggle
        their visibility cheaply; only the column *order* changes here.
        Width semantics: a :attr:`ColumnState.width` of ``None`` leaves
        the current column width untouched; an explicit integer
        overrides :attr:`TableColumn.width`.  ``0`` is treated as *auto*
        for compatibility with :class:`TableColumn`.

        Unknown column keys are tracked internally so a subsequent
        :meth:`capture_settings` can re-emit them losslessly even
        though they do not exist in the current data source.

        Args:
            settings: A :class:`ViewSettings` instance.  Imported lazily
                to avoid a circular import between ``views`` and
                ``table_model``.
        """
        from .views.data_models import ColumnState, ViewSettings

        if not isinstance(settings, ViewSettings):
            raise TypeError(
                f"apply_settings expected ViewSettings, got "
                f"{type(settings).__name__}"
            )

        # Reorder the catalog (_explicit_columns) according to the
        # incoming ColumnState order.  Columns not mentioned in the
        # settings keep their relative order and are appended at the
        # end so newly-added data-source columns are not lost.
        catalog: list[TableColumn] = list(self._explicit_columns or [])
        by_key: dict[str, TableColumn] = {c.key: c for c in catalog}

        reordered: list[TableColumn] = []
        seen_keys: set[str] = set()
        unknown_states: list[ColumnState] = []

        for state in settings.columns:
            col = by_key.get(state.name)
            if col is None:
                unknown_states.append(state)
                continue
            if state.width is not None:
                # 0 means auto (matches TableColumn semantics); any other
                # value overrides the column's default width.
                col.width = max(0, int(state.width))
            reordered.append(col)
            seen_keys.add(state.name)

        for col in catalog:
            if col.key not in seen_keys:
                reordered.append(col)

        # Match the sort column by key against the new column order.
        sort_column = -1
        if settings.sort_by:
            for i, col in enumerate(reordered):
                if col.key == settings.sort_by:
                    sort_column = i
                    break

        sort_order = (
            Qt.SortOrder.DescendingOrder
            if settings.sort_desc
            else Qt.SortOrder.AscendingOrder
        )

        self._explicit_columns = reordered
        self._sort_column = sort_column
        self._sort_order = sort_order
        self._tree_position = -1  # force recomputation on next read
        self._unknown_column_states = list(unknown_states)

        self.reset_data()

    def capture_settings(self) -> Any:
        """Capture the current model state as a :class:`ViewSettings`.

        The returned settings contain the column order/widths and sort
        configuration only — visibility, pinning, filter and grouping
        are owned by the view widgets and are filled in by
        :class:`ViewBindings` (Phase 2).

        Any unknown column states preserved by the most recent
        :meth:`apply_settings` call are appended verbatim so a
        roundtrip stays lossless.

        Returns:
            A new :class:`ViewSettings` instance.
        """
        from .views.data_models import ColumnState, ViewSettings

        cols: list[ColumnState] = [
            ColumnState(
                name=c.key,
                visible=True,
                width=c.width if c.width > 0 else None,
            )
            for c in self._columns
        ]
        # Re-emit unknown column states that were preserved on apply so
        # roundtripping through a model that doesn't recognise them
        # still produces the original payload.
        cols.extend(getattr(self, "_unknown_column_states", []))

        sort_by: str | None = None
        if 0 <= self._sort_column < len(self._columns):
            sort_by = self._columns[self._sort_column].key

        return ViewSettings(
            columns=cols,
            sort_by=sort_by,
            sort_desc=(self._sort_order == Qt.SortOrder.DescendingOrder),
        )

    def get_distinct_values(self, key: str) -> list[str]:
        """Return sorted distinct non-empty string values for a column.

        In flat mode scans root-level rows; in tree mode scans all
        loaded nodes across all levels.

        Args:
            key: Column key to inspect.

        Returns:
            Sorted list of unique string values found in loaded rows.
        """
        seen: set[str] = set()
        nodes = (
            self._all_nodes if self._tree_mode else set(self._root.children)
        )
        for node in nodes:
            if node.is_root:
                continue
            val = node.row_data.get(key)
            if val is not None:
                s = str(val).strip()
                if s:
                    seen.add(s)
        return sorted(seen)

    # Internal helpers --------------------------------------------------------

    def _node_from_index(
        self, index: QModelIndex | QPersistentModelIndex
    ) -> _TableNode:
        """Return the internal node for a model index.

        Args:
            index: A valid or invalid QModelIndex.

        Returns:
            The corresponding _TableNode; returns root for invalid
            indexes.
        """
        if not index.isValid():
            return self._root
        return index.internalPointer()  # type: ignore[return-value]

    @staticmethod
    def _generate_request_id() -> str:
        """Return a unique request identifier for task-queue scoping."""
        return str(uuid.uuid1())

    def _index_for_node(self, node: _TableNode) -> QModelIndex:
        """Return the QModelIndex that identifies node (column 0).

        Args:
            node: A non-root table node.

        Returns:
            Valid QModelIndex for non-root nodes, invalid for root.
        """
        if node.is_root:
            return QModelIndex()
        parent = node.parent
        row = parent.children.index(node)  # type: ignore[union-attr]
        return self.createIndex(row, 0, node)

    def _update_loading_state(self) -> None:
        """Emit loading-progress signals based on current pending task
        count."""
        self.pending_count_changed.emit(self._pending_tasks)
        self.loading_changed.emit(self._pending_tasks > 0)

    def _on_page_ready(
        self,
        node: _TableNode,
        request_id: str,
        results: list[dict[str, Any]] | None,
    ) -> None:
        """Handle fetch results on the main thread.

        Called via Qt.QueuedConnection from AsyncTaskQueue so it always
        executes on the Qt main thread, making it safe to call Qt model
        mutation methods.

        Args:
            node: The node whose page was fetched.
            request_id: The request id that was active when the task was
                enqueued.  Used to discard stale results.
            results: Row dicts returned by _fetch_page, or None on error.
        """
        # Stale callback: release the guard and discard.
        # Do NOT decrement _pending_tasks for stale callbacks — the
        # reset_data() call already set the counter to 0 for the new
        # context.  Decrementing here would corrupt the new context's count.
        if request_id != self._request_id or node not in self._all_nodes:
            # Always release the fetching guard so the node is never stuck
            # in-flight, even for stale callbacks.
            node.is_fetching = False
            log.debug(
                "Discarding stale fetch result for node %r (request %s vs %s)",
                node.node_id,
                request_id,
                self._request_id,
            )
            return

        # Confirmed current-context callback: update the in-flight counter.
        # Keep is_fetching=True until ALL model mutations below are finished.
        # endInsertRows() emits rowsInserted synchronously, which can cause
        # Qt's tree-view slot to call canFetchMore/fetchMore re-entrantly.
        # The guard must still be set at that point so _fetch_next_page
        # returns immediately and avoids a recursive re-fetch of the same page.
        self._pending_tasks = max(0, self._pending_tasks - 1)

        _was_children_loaded = node.children_loaded

        if results is None:
            # Task failed — fetch_error already logged by AsyncTaskQueue.
            self.fetch_error.emit(
                f"Failed to fetch page {node.current_page} "
                f"(parent_id={node.node_id!r})"
            )
            node.has_more = False
            node.children_loaded = True
            node.is_fetching = False
            # Emit loading state after updating node state.
            self._update_loading_state()
            return

        if not results:
            node.has_more = False
            node.children_loaded = True
            node.is_fetching = False
            self._update_loading_state()
            return

        if not self._columns and self._explicit_columns is None:
            self._columns = self._infer_columns(results[0])

        parent_index = self._index_for_node(node)
        first_new = len(node.children)
        last_new = first_new + len(results) - 1
        self.beginInsertRows(parent_index, first_new, last_new)
        for row_data in results:
            child = _TableNode(
                node_id=row_data.get("id"),
                row_data=row_data,
                parent=node,
            )
            node.children.append(child)
            self._all_nodes.add(child)
        self.endInsertRows()

        node.children_loaded = True
        if len(results) < self._page_size:
            node.has_more = False

        fetched_page = node.current_page
        node.current_page += 1

        # Release the re-entrancy guard now that all model mutations are done.
        # Any canFetchMore/fetchMore calls that arrived re-entrantly during
        # endInsertRows were blocked by is_fetching=True; they can now proceed
        # on the next event-loop iteration if the node still has more pages.
        node.is_fetching = False

        # Emit loading-state signals AFTER rows are in the model so that
        # any slot reacting to is_loading=False already sees the new rows.
        self._update_loading_state()
        self.page_fetched.emit(fetched_page, len(self._root.children))

        # On the first child-load for a non-root node, emit dataChanged so
        # proxy models (e.g. AYTableFilterProxyModel) re-evaluate this row's
        # filter status now that real children are available.
        if (
            not node.is_root
            and not _was_children_loaded
            and node.children_loaded
        ):
            idx = self._index_for_node(node)
            self.dataChanged.emit(idx, idx)

    def _get_fetch_priority(self, node: _TableNode, page: int) -> int:
        """Return the async-task priority for a child-page fetch.

        The default implementation uses priority **1** (High) for the
        very first page of any node and **2** (Normal) for subsequent
        pages.  Subclasses may override this method to implement dynamic
        priority logic — for example, lowering the priority to **20**
        (Background prefetch) when the parent node's row is not currently
        visible in the table's viewport.

        Priority scale (lower value = higher priority):

        - ``0`` - Critical / visible first-page fetches
        - ``1`` - High / visible subsequent-page fetches
        - ``2`` - Normal / thumbnail fetches
        - ``20`` - Low / off-screen prefetch

        Args:
            node: The parent node whose children are being fetched.
            page: Zero-based index of the page being requested.

        Returns:
            Integer task priority passed to
            :class:`~ayon_core.ui.components.task_queue.AsyncTask`.
        """
        return 1 if page == 0 else 2

    def _fetch_next_page(self, node: _TableNode) -> None:
        """Enqueue an async task to fetch the next page of children for *node*.

        Uses a per-node re-entrancy guard (``node.is_fetching``) to
        prevent duplicate tasks.  The actual data-fetch runs in the
        shared :class:`AsyncTaskQueue` worker thread; results are
        delivered back on the main thread via :meth:`_on_page_ready`.

        When *fetch_page_batch* is configured and *node* is not the
        invisible root, the node is added to ``_pending_batch_nodes`` and
        a zero-delay timer schedules :meth:`_dispatch_batch`.  This
        coalesces all sibling fetches that arrive in the same event-loop
        tick into a single server call.

        Priority is determined by :meth:`_get_fetch_priority`, which
        defaults to 1 (High) for the first page and 2 (Normal) for
        subsequent pages.  Subclasses may override
        :meth:`_get_fetch_priority` to adjust priority dynamically.

        Args:
            node: The parent node whose next page of children to fetch.
        """
        if node.is_fetching:
            return
        node.is_fetching = True

        sort_key = None
        if 0 <= self._sort_column < len(self._columns):
            sort_key = self._columns[self._sort_column].key
        descending = self._sort_order == Qt.SortOrder.DescendingOrder

        page = node.current_page
        page_size = self._page_size
        node_id = node.node_id
        request_id = self._request_id

        priority = self._get_fetch_priority(node, page)

        self._pending_tasks += 1
        self._update_loading_state()

        # Batch path: coalesce non-root child fetches when a batch
        # callback is available.  The root is always fetched individually
        # because it is the first call and nothing can be batched with it.
        if self._fetch_page_batch is not None and not node.is_root:
            self._pending_batch_nodes.append(node)
            if not self._batch_scheduled:
                self._batch_scheduled = True
                QTimer.singleShot(0, self._dispatch_batch)
            return

        if self._no_async:
            # Synchronous path: fetch inline and deliver result immediately.
            # Used in tests to avoid cross-thread paint-event races.
            try:
                result = self._fetch_page(
                    page, page_size, sort_key, descending, node_id
                )
            except Exception:
                result = None
            self._on_page_ready(node, request_id, result)
            return

        task = AsyncTask(
            name=f"fetch_page_{node_id or 'root'}_{page}",
            function=lambda: self._fetch_page(
                page, page_size, sort_key, descending, node_id
            ),
            callback=lambda result: self._on_page_ready(
                node, request_id, result
            ),
            priority=priority,
            context_id=request_id,
            cancellable=True,
        )
        get_task_queue().enqueue(task)

    def _dispatch_batch(self) -> None:
        """Dispatch all accumulated pending batch-fetch requests.

        Called via ``QTimer.singleShot(0)`` so it runs on the main thread
        at the start of the next event-loop iteration, after all
        ``fetchMore()`` calls for the current expansion wave have been
        collected into ``_pending_batch_nodes``.

        The method creates one :class:`AsyncTask` (or runs synchronously
        when ``no_async=True``) carrying all pending requests.  Results
        are fanned out to the per-node ``_on_page_ready`` handler via
        :meth:`_on_batch_ready`.
        """
        self._batch_scheduled = False
        nodes = list(self._pending_batch_nodes)
        self._pending_batch_nodes = []

        if not nodes:
            return

        sort_key = None
        if 0 <= self._sort_column < len(self._columns):
            sort_key = self._columns[self._sort_column].key
        descending = self._sort_order == Qt.SortOrder.DescendingOrder
        request_id = self._request_id

        requests = [
            BatchFetchRequest(
                page=node.current_page,
                page_size=self._page_size,
                sort_key=sort_key,
                descending=descending,
                parent_id=node.node_id,
            )
            for node in nodes
        ]

        log.debug(
            "Dispatching batch of %d fetch requests (request=%s)",
            len(requests),
            request_id,
        )

        assert self._fetch_page_batch is not None  # guarded by caller
        batch_fn = self._fetch_page_batch

        # Use the highest-urgency (lowest numeric) priority among the
        # batched nodes so that a batch containing at least one visible
        # node runs at visible priority rather than the default priority=1.
        batch_priority = min(
            self._get_fetch_priority(n, n.current_page) for n in nodes
        )

        if self._no_async:
            try:
                result: dict[str | None, list[dict[str, Any]]] | None = (
                    batch_fn(requests)
                )
            except Exception:
                log.exception("Batch fetch raised")
                result = None
            self._on_batch_ready(nodes, request_id, result)
            return

        task = AsyncTask(
            name=f"fetch_batch_{len(nodes)}_nodes",
            function=lambda: batch_fn(requests),
            callback=lambda res: self._on_batch_ready(nodes, request_id, res),
            priority=batch_priority,
            context_id=request_id,
            cancellable=True,
        )
        get_task_queue().enqueue(task)

    def _on_batch_ready(
        self,
        nodes: list[_TableNode],
        request_id: str,
        results: dict[str | None, list[dict[str, Any]]] | None,
    ) -> None:
        """Fan out batch results to per-node handlers.

        Delegates each node's slice of the results to :meth:`_on_page_ready`
        so that all existing insertion, loading-state, and dataChanged
        logic is reused without duplication.

        Args:
            nodes: The nodes whose children were requested in the batch.
            request_id: The request id active when the batch was dispatched.
                Used to discard stale results.
            results: Mapping of ``parent_id -> list[row_dict]`` returned by
                the batch callback, or ``None`` on error.
        """
        for node in nodes:
            node_results: list[dict[str, Any]] | None
            if results is None:
                node_results = None
            else:
                node_results = results.get(node.node_id, [])
            self._on_page_ready(node, request_id, node_results)

    @staticmethod
    def _infer_columns(row: dict[str, Any]) -> list[TableColumn]:
        """Infer column definitions from a sample row dictionary.

        Reserved keys (``id``, ``has_children``) and decorator suffixes
        (``__icon``, ``__color``, ``__fill``) are excluded.

        Args:
            row: A representative row dictionary.

        Returns:
            List of inferred TableColumn instances.
        """
        columns: list[TableColumn] = []
        for key in row:
            if key in ("id", "has_children"):
                continue
            if key.endswith(("__icon", "__color", "__fill")):
                continue
            label = key.replace("_", " ").title()
            columns.append(TableColumn(key=key, label=label))
        return columns


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

TABLE_TEST_DATA: list[dict[str, Any]] = [
    {
        "name": f"Asset {i:03d}",
        "status": [
            "Not ready",
            "Ready to start",
            "In progress",
            "Pending review",
            "Approved",
            "On hold",
            "Omitted",
        ][i % 7],
        "status__icon": [
            "fiber_new",
            "timer",
            "play_arrow",
            "visibility",
            "task_alt",
            "back_hand",
            "block",
        ][i % 7],
        "status__color": [
            "#434a56",
            "#bababa",
            "#3498db",
            "#ff9b0a",
            "#00f0b4",
            "#fa6e46",
            "#cb1a1a",
        ][i % 7],
        "type": random.choice(
            [
                "Model",
                "Texture",
                "Rig",
                "Animation",
                "Look-dev",
                "Compositing",
                "Grading",
            ]
        ),
        "author": random.choice(
            [
                "Alice",
                "Bob",
                "Charlie",
                "Diana",
                "Steve",
                "Eva",
                "Frank",
                "Grace",
            ]
        ),
        "version": f"v{(i % 10) + 1:03d}",
    }
    for i in range(200)
]


def make_test_fetch(
    data: list[dict[str, Any]],
) -> Callable[[int, int, str | None, bool, str | None], list[dict[str, Any]]]:
    """Create a flat fetch_page callback from static data.

    ``parent_id`` is accepted but ignored — all data lives at root level.

    Args:
        data: The full dataset to paginate.

    Returns:
        A callable suitable for PaginatedTableModel.
    """

    def _fetch(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None = None,  # noqa: ARG001
    ) -> list[dict[str, Any]]:
        print(
            f"[test]  Fetching page {page} (page_size={page_size}, "
            f"sort_key={sort_key!r}, descending={descending})"
        )
        rows = data
        if sort_key:
            rows = sorted(
                data,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page * page_size
        end = start + page_size
        return rows[start:end]

    return _fetch


# ---------------------------------------------------------------------------
# Hierarchical test data
# ---------------------------------------------------------------------------

_FOLDER_ICON = "folder"
_FOLDER_COLOR = "#8898a8"


def _make_hierarchical_test_data(
    n: int,
    subfolders_per_root: int = 8,
) -> dict[str | None, list[dict[str, Any]]]:
    """Generate hierarchical test data with a configurable number of leaf
    entries.

    Two root folders (Assets, Shots) are always present.  Under each,
    ``subfolders_per_root`` sub-folders are generated from a fixed name
    pool.  Leaf entries are distributed as evenly as possible across all
    sub-folders.

    The function is deterministic: the same arguments always produce the
    same dataset because a seeded :class:`random.Random` instance is
    used internally.

    Args:
        n: Total number of leaf entries to generate.
        subfolders_per_root: Number of sub-folders to create under each
            root folder.  Capped at 10 for asset folders (the size of
            the name pool); shot folders are auto-named so there is no
            cap.

    Returns:
        A mapping of parent_id -> list[row_dict] suitable for use with
        :func:`_make_hierarchical_test_fetch`.
    """
    rng = random.Random(42)

    _statuses = [
        ("Not ready", "fiber_new", "#434a56"),
        ("Ready to start", "timer", "#bababa"),
        ("In progress", "play_arrow", "#3498db"),
        ("Pending review", "visibility", "#ff9b0a"),
        ("Approved", "task_alt", "#00f0b4"),
        ("On hold", "back_hand", "#fa6e46"),
        ("Omitted", "block", "#cb1a1a"),
    ]
    _asset_folder_pool = [
        "Hero",
        "Villain",
        "Sidekick",
        "Creature",
        "NPC_A",
        "NPC_B",
        "Prop_Vehicle",
        "Prop_Furniture",
        "Environment_City",
        "Environment_Forest",
    ]
    _asset_task_names = ["model", "rig", "lookdev", "texture", "layout"]
    _asset_types = ["Model", "Texture", "Rig", "Look-dev"]
    _shot_task_names = [
        "Animation",
        "Lighting",
        "Compositing",
        "Grading",
        "FX",
    ]
    _shot_types = ["Animation", "Lighting", "Compositing", "Grading"]
    _authors = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace"]

    num_asset = min(subfolders_per_root, len(_asset_folder_pool))
    asset_names = _asset_folder_pool[:num_asset]
    asset_ids = [name.lower() for name in asset_names]

    num_shots = subfolders_per_root
    shot_names = [f"SH{(i + 1) * 10:03d}" for i in range(num_shots)]
    shot_ids = [name.lower() for name in shot_names]

    total_subfolders = num_asset + num_shots
    base, remainder = divmod(n, total_subfolders)
    counts = [
        base + (1 if i < remainder else 0) for i in range(total_subfolders)
    ]
    asset_counts = counts[:num_asset]
    shot_counts = counts[num_asset:]

    def _make_entries(
        parent_id: str,
        count: int,
        task_names: list[str],
        task_types: list[str],
    ) -> list[dict[str, Any]]:
        entries = []
        for i in range(count):
            status, icon, color = rng.choice(_statuses)
            entries.append(
                {
                    "id": f"{parent_id}_{i:04d}",
                    "name": rng.choice(task_names),
                    "name__icon": "package_2",
                    "status": status,
                    "status__icon": icon,
                    "status__color": color,
                    "type": rng.choice(task_types),
                    "author": rng.choice(_authors),
                    "version": f"v{rng.randint(1, 20):03d}",
                    "thumb": "",  # placeholder for thumbnail column
                    "thumb__icon": "panorama",  # placeholder for thumbnail column  # noqa: E501
                }
            )
        return entries

    def _folder_row(folder_id: str, folder_name: str) -> dict[str, Any]:
        return {
            "id": folder_id,
            "name": folder_name,
            "has_children": True,
            "name__icon": _FOLDER_ICON,
            "name__color": _FOLDER_COLOR,
        }

    result: dict[str | None, list[dict[str, Any]]] = {
        None: [
            _folder_row("assets", "Assets"),
            _folder_row("shots", "Shots"),
        ],
        "assets": [
            _folder_row(fid, name) for fid, name in zip(asset_ids, asset_names)
        ],
        "shots": [
            _folder_row(sid, name) for sid, name in zip(shot_ids, shot_names)
        ],
    }

    for folder_id, count in zip(asset_ids, asset_counts):
        result[folder_id] = _make_entries(
            folder_id, count, _asset_task_names, _asset_types
        )
    for shot_id, count in zip(shot_ids, shot_counts):
        result[shot_id] = _make_entries(
            shot_id, count, _shot_task_names, _shot_types
        )

    return result


HIERARCHICAL_TEST_DATA = _make_hierarchical_test_data(500)


def make_hierarchical_test_fetch(
    data: dict[str | None, list[dict[str, Any]]],
) -> Callable[[int, int, str | None, bool, str | None], list[dict[str, Any]]]:
    """Create a fetch_page callback from hierarchical test data.

    Args:
        data: Mapping of parent_id -> list[row_dict].
              ``None`` key holds the root-level rows.

    Returns:
        A callable suitable for PaginatedTableModel in tree mode.
    """

    def _fetch(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        print(
            f"[test]  Fetching page {page} (page_size={page_size}, "
            f"sort_key={sort_key!r}, descending={descending}, "
            f"parent_id={parent_id!r})"
        )
        rows = list(data.get(parent_id, []))
        if sort_key:
            rows = sorted(
                rows,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page * page_size
        end = start + page_size
        return rows[start:end]

    return _fetch


def make_hierarchical_test_fetch_batch(
    data: dict[str | None, list[dict[str, Any]]],
) -> Callable[
    [list[BatchFetchRequest]], dict[str | None, list[dict[str, Any]]]
]:
    """Create a *fetch_page_batch* callback from hierarchical test data.

    Wraps :func:`make_hierarchical_test_fetch` so that several child
    fetch requests are resolved in one call, mimicking a batched server
    API.  Use together with ``fetch_page_batch=`` on
    :class:`PaginatedTableModel` to exercise the batch code path.

    Args:
        data: Mapping of parent_id -> list[row_dict].
              ``None`` key holds the root-level rows.

    Returns:
        A callable suitable for ``PaginatedTableModel(fetch_page_batch=…)``
        in tree mode.
    """
    single_fetch = make_hierarchical_test_fetch(data)

    def _batch_fetch(
        requests: list[BatchFetchRequest],
    ) -> dict[str | None, list[dict[str, Any]]]:
        print(
            f"[test]  Batch fetch for {len(requests)} parent(s): "
            f"{[r.parent_id for r in requests]!r}"
        )
        return {
            req.parent_id: single_fetch(
                req.page,
                req.page_size,
                req.sort_key,
                req.descending,
                req.parent_id,
            )
            for req in requests
        }

    return _batch_fetch


if __name__ == "__main__":
    import sys

    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    fetch = make_test_fetch(TABLE_TEST_DATA)
    model = PaginatedTableModel(fetch_page=fetch, page_size=25)
    print(f"[test]  Rows: {model.rowCount()}, Columns: {model.columnCount()}")
    print(f"[test]  Columns: {[c.label for c in model.columns]}")
    has_more = model.canFetchMore()
    print(f"[test]  Has more: {has_more}")
