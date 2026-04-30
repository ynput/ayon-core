"""Right-hand panel that shows a paginated table of versions."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterator

from ayon_ui_qt.components.card_view import AYCardView
from ayon_ui_qt.components.container import AYContainer, AYHBoxLayout
from ayon_ui_qt.components.table_filter import AYTableFilter
from ayon_ui_qt.components.table_model import TableColumn
from ayon_ui_qt.components.table_view import AYTableView
from ayon_ui_qt.components.task_queue import AsyncTask, get_task_queue
from ayon_ui_qt.image_cache import ImageCache
from ayon_ui_qt.style import get_ayon_style_data
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger
from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.loader.ui.review_group_by import (
    GROUP_BY_PRODUCT_KEY,
    GroupByOption,
    get_attribute_icon,
)
from ayon_core.tools.loader.ui.review_types import ReviewCategory

from ._review_model import VisibilityAwarePaginatedTableModel
from ._review_thumbnails import (
    LazyThumbnailWidget,
    PlaceholderThumbnail,
    _make_card_async_fetcher,
    _review_card_mapper,
    _thumbnail_loader,
)
from ._review_toolbar import Customize, DisplayType, GroupByMenu

log = Logger.get_logger(__name__)


class _ExpansionPhase(Enum):
    IDLE = "idle"
    VISIBLE = "visible"
    SPECULATIVE = "speculative"


class ReviewTable(AYContainer):
    """Right-hand panel that shows a paginated table of versions."""

    display_type_changed = QtCore.Signal(QtWidgets.QAbstractItemView)

    def __init__(
        self,
        controller: ReviewController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=8,
            layout_spacing=4,
            **kwargs,
        )
        self._controller = controller
        self._table = AYTableView(self)
        self._model = VisibilityAwarePaginatedTableModel(
            fetch_page=self._controller.fetch_versions_page,
            fetch_page_batch=(self._controller.fetch_versions_page_batch),
            columns=self._build_columns(self._controller.current_category),
            page_size=250,
        )
        self._model.set_view(self._table)

        initial_tree_mode = self._controller.group_by_key != "none"
        self._controller.set_tree_mode(initial_tree_mode)
        self._model.set_tree_mode(initial_tree_mode)

        self._table_filter = AYTableFilter(model=self._model, parent=self)
        self._table.setModel(self._table_filter.filter_model)

        _card_fetcher = _make_card_async_fetcher(self._model)

        def _card_mapper(row_data: dict) -> dict:
            data = _review_card_mapper(row_data)
            data["async_file_cacher"] = _card_fetcher
            return data

        self._card_view = AYCardView(
            parent=self,
            card_width=200,
            card_spacing=8,
            card_data_mapper=_card_mapper,
        )
        self._card_view.setModel(self._table_filter.filter_model)

        self._table.header().setSortIndicator(
            1, QtCore.Qt.SortOrder.AscendingOrder
        )

        self._group_by_menu = GroupByMenu(
            parent=self,
            options=self._controller.get_group_by_options(),
            default_key=self._controller.group_by_key,
        )
        self._group_by_menu.group_by_changed.connect(self._on_group_by_changed)
        self._group_by_menu.setVisible(
            self._controller.current_category == ReviewCategory.HIERARCHY.value
        )
        self._controller.group_by_options_changed.connect(
            self._on_group_by_options_changed
        )

        self._display_type = DisplayType(self, initial_display_type="table")
        self._display_type.display_type_changed.connect(
            self._on_display_type_changed
        )

        self._customize = Customize(parent=self, initial_card_width=200)
        self._customize.set_show_empty_groups(
            not self._controller.hide_empty_groups
        )
        self._customize.show_empty_groups_changed.connect(
            self._on_show_empty_groups_changed
        )
        self._customize.card_size_changed.connect(
            self._card_view.set_card_width
        )
        self._customize.featured_version_order_changed.connect(
            self._on_featured_version_order_changed
        )

        toolbar_lyt = AYHBoxLayout(self, margin=0, spacing=4)
        toolbar_lyt.addWidget(self._table_filter, stretch=1)
        toolbar_lyt.addWidget(self._group_by_menu, stretch=0)
        toolbar_lyt.addWidget(self._display_type, stretch=0)
        toolbar_lyt.addWidget(self._customize, stretch=0)
        self.add_layout(toolbar_lyt, stretch=0)

        self._views_stack = QtWidgets.QStackedLayout()
        self._views_stack.addWidget(self._table)
        self._views_stack.addWidget(self._card_view)
        self._views_stack.setCurrentWidget(self._table)
        views_container = QtWidgets.QWidget(self)
        views_container.setLayout(self._views_stack)
        self.add_widget(views_container)

        self._auto_expand: bool = False
        self._deferred_expand_queue: list[QtCore.QPersistentModelIndex] = []
        self._expansion_phase: _ExpansionPhase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys: set[str] = set()
        self._scroll_catch_up_timer: QtCore.QTimer | None = None

        self._model.rowsInserted.connect(self._on_rows_inserted_expand)
        self._model.loading_changed.connect(
            self._on_loading_changed,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        self._table.verticalScrollBar().valueChanged.connect(
            self._on_scroll_catch_up
        )
        self._model.page_fetched.connect(self._on_page_fetched)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def table(self) -> AYTableView:
        return self._table

    @property
    def card_view(self) -> AYCardView:
        return self._card_view

    @property
    def active_view(self) -> AYTableView | AYCardView:
        return self._views_stack.currentWidget()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def reset_data(self) -> None:
        """Reset the underlying model data."""
        self._model.reset_data()

    def refresh_filter(self) -> None:
        """Re-apply the active filter criteria."""
        self._table_filter.filter_model.refresh_filter()

    def set_auto_expand(self, enabled: bool) -> None:
        """Enable or disable automatic expansion of folder rows.

        When *enabled*, every folder row inserted into the model is
        immediately expanded so that its children are fetched and
        displayed.  Disabling discards any pending deferred-expansion
        work.

        Args:
            enabled: ``True`` to auto-expand, ``False`` to disable.
        """
        self._auto_expand = enabled
        if enabled:
            self._expansion_phase = _ExpansionPhase.VISIBLE
        else:
            self._deferred_expand_queue.clear()
            self._expansion_phase = _ExpansionPhase.IDLE

    def on_project_info_changed(self) -> None:
        """Rebuild columns now that version attributes are available."""
        self._enqueued_thumb_keys.clear()
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._group_by_menu.set_options(
            self._controller.get_group_by_options(),
            self._controller.group_by_key,
        )
        self._model.reset_data()
        self._model.set_columns(
            self._build_columns(self._controller.current_category)
        )

    def on_category_changed(self, category: str) -> None:
        """Reset the table when the slicer category changes.

        Syncs the model's tree-mode flag with the controller — the
        controller has already normalised its own ``group_by_key`` and
        ``tree_mode`` for the new category in
        :meth:`ReviewController.set_category`.

        Args:
            category: New category value string.
        """
        self._auto_expand = False
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys.clear()
        self._model.set_tree_mode(self._controller.tree_mode)
        self._group_by_menu.set_options(
            self._controller.get_group_by_options(),
            self._controller.group_by_key,
        )
        self._model.reset_data()
        self._model.set_columns(self._build_columns(category))
        self._group_by_menu.setVisible(
            category == ReviewCategory.HIERARCHY.value
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _reset_expansion_state(self) -> None:
        """Clear expansion state and queues."""
        self._auto_expand = False
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys.clear()

    def _on_display_type_changed(self, display_type: str) -> None:
        log.debug("Display type changed: %s", display_type)
        if display_type == "grid":
            self._views_stack.setCurrentWidget(self._card_view)
        else:
            self._views_stack.setCurrentWidget(self._table)

        active = self._views_stack.currentWidget()
        if not shiboken.isValid(active.viewport()):
            return

        active.viewport().update()

        if active is self._card_view:
            self._card_view.refresh_visible_editors()

        if active is self._table:
            self._eagerly_enqueue_visible_thumbnails()


        self.display_type_changed.emit(active)

    def _on_group_by_options_changed(
        self, options: dict[str, GroupByOption]
    ) -> None:
        self._group_by_menu.set_options(
            list(options.values()), self._controller.group_by_key
        )

    def _on_group_by_changed(self, group_by_key: str) -> None:
        self._controller.set_group_by(group_by_key)
        tree_mode = group_by_key != "none"
        self._controller.set_tree_mode(tree_mode)
        self._model.set_tree_mode(tree_mode)
        self._reset_expansion_state()
        self._model.reset_data()

    def _on_show_empty_groups_changed(self, show_empty: bool) -> None:
        self._controller.set_hide_empty_groups(not show_empty)
        self._reset_expansion_state()
        self._model.reset_data()

    def _on_featured_version_order_changed(self, order: list[str]) -> None:
        """Propagate a new featured-version priority to the controller.

        When group-by is set to ``"product"`` the table data is
        immediately re-fetched so the view reflects the new order.

        Args:
            order: Ordered list of GraphQL featured-version type keys.
        """
        self._controller.set_featured_version_order(order)
        if self._controller.group_by_key == GROUP_BY_PRODUCT_KEY:
            self._reset_expansion_state()
            self._model.reset_data()

    def _on_page_fetched(self, page: int, total_pages: int) -> None:
        """Repaint and eagerly pre-fetch visible thumbnails.

        After repainting, iterate over all rows visible in the table
        viewport and enqueue thumbnail fetch tasks (priority 2) for
        those not yet requested.  Card-view thumbnails are handled by
        each card's own ``async_file_cacher``, but the card view still
        needs an explicit ``refresh_visible_editors`` call so that
        newly-arrived rows get their card widgets created while the
        card view is the active display.
        """
        active = self._views_stack.currentWidget()
        if not shiboken.isValid(active.viewport()):
            return
        active.viewport().update()
        if active is self._table:
            self._eagerly_enqueue_visible_thumbnails()
        elif active is self._card_view:
            self._card_view.refresh_visible_editors()

    def _table_row_height(self) -> int:
        first_row_index = self._table.indexAt(QtCore.QPoint(0, 0))
        return (
            self._table.rowHeight(first_row_index)
            if self._table.children()
            else 32
        )

    def _iter_visible_proxy_indices(
        self,
    ) -> Iterator[QtCore.QModelIndex]:
        """Yield unique proxy indices that intersect the viewport.

        The walk uses ``indexAt`` by vertical pixel position so nested
        tree rows are included. Duplicate indices are suppressed.
        """
        vp = self._table.viewport()
        vp_rect = vp.rect()
        if vp_rect.isEmpty():
            return

        row_height = self._table_row_height()
        y = vp_rect.top()
        seen: set[QtCore.QPersistentModelIndex] = set()

        while y <= vp_rect.bottom():
            proxy_idx = self._table.indexAt(QtCore.QPoint(0, y))
            if not proxy_idx.isValid():
                y += row_height
                continue

            persistent_idx = QtCore.QPersistentModelIndex(proxy_idx)
            if persistent_idx not in seen:
                seen.add(persistent_idx)
                yield proxy_idx

            vis = self._table.visualRect(proxy_idx)
            if vis.isValid() and vis.height() > 0:
                y = vis.bottom() + 1
            else:
                y += row_height

    def _eagerly_enqueue_visible_thumbnails(self) -> None:
        """Enqueue thumbnail tasks for currently visible version rows.

        Already-enqueued or already-cached keys are skipped.
        """
        ic = ImageCache.get_instance()
        request_id = self._model.request_id
        project = self._controller.current_project
        if not project:
            return

        vp = self._table.viewport()
        if vp.rect().isEmpty():
            return

        for proxy_idx in self._iter_visible_proxy_indices():
            row_dict = proxy_idx.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            thumbnail_id = row_dict.get("thumbnailId", "")
            version_id = row_dict.get("_version_id") or row_dict.get("id", "")
            if not thumbnail_id or not version_id:
                continue

            key = f"{project}/{version_id}/{thumbnail_id}"
            if key in self._enqueued_thumb_keys or ic.has(key):
                continue

            self._enqueued_thumb_keys.add(key)

            def _update_viewport(
                _fpath: str, _vp: QtWidgets.QWidget = vp
            ) -> None:
                if shiboken.isValid(_vp):
                    _vp.update()

            get_task_queue().enqueue(
                AsyncTask(
                    name=f"eager_thumb_{key}",
                    function=lambda k=key: _thumbnail_loader(k),
                    callback=_update_viewport,
                    priority=2,
                    context_id=request_id,
                    cancellable=True,
                )
            )

    # ------------------------------------------------------------------
    # Auto-expand logic
    # ------------------------------------------------------------------

    def _on_rows_inserted_expand(
        self,
        parent: QtCore.QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Expand newly inserted folder rows when auto-expand is active.

        Expansion is split into two phases:

        1. **Visible phase** — rows whose proxy rect intersects the
           viewport are expanded straight away (priority 0/1 fetches).
           ``_expansion_phase`` remains ``"visible"`` until
           ``loading_changed(False)`` fires.
        2. **Speculative phase** — off-screen rows are collected into
           ``_deferred_expand_queue`` and expanded in batches of 20 via
           recurring ``QTimer.singleShot(0)`` calls.

        Args:
            parent: Source model parent index of the inserted rows.
            first: First inserted row (0-based).
            last: Last inserted row (0-based, inclusive).
        """
        if not self._auto_expand:
            return

        proxy_model = self._table_filter.filter_model
        vp_rect = self._table.viewport().rect()

        for row in range(first, last + 1):
            src_idx = self._model.index(row, 0, parent)
            if not self._model.canFetchMore(src_idx):
                continue

            proxy_idx = proxy_model.mapFromSource(src_idx)
            if not proxy_idx.isValid():
                continue

            visual = self._table.visualRect(proxy_idx)
            if vp_rect.intersects(visual):
                self._table.expand(proxy_idx)
            else:
                self._deferred_expand_queue.append(
                    QtCore.QPersistentModelIndex(src_idx)
                )

    def _on_loading_changed(self, is_loading: bool) -> None:
        """Transition to speculative phase when visible loads finish.

        Connected to ``PaginatedTableModel.loading_changed`` with a
        ``QueuedConnection`` to avoid re-entrant issues.

        Args:
            is_loading: ``True`` while fetch tasks are pending.
        """
        if is_loading:
            return
        if self._expansion_phase == _ExpansionPhase.VISIBLE:
            if not self._deferred_expand_queue:
                self._expansion_phase = _ExpansionPhase.IDLE
                return
            self._expansion_phase = _ExpansionPhase.SPECULATIVE
            self._expand_deferred_batch()
        elif self._expansion_phase == _ExpansionPhase.SPECULATIVE:
            if self._deferred_expand_queue:
                QtCore.QTimer.singleShot(0, self._expand_deferred_batch)
            else:
                self._expansion_phase = _ExpansionPhase.IDLE

    def _expand_deferred_batch(self) -> None:
        """Expand the next chunk of off-screen deferred rows.

        Pops up to 20 items from ``_deferred_expand_queue`` and expands
        them.  If more rows remain, re-schedules itself via
        ``QTimer.singleShot(0)`` to keep the UI responsive.

        Only runs during the ``"speculative"`` phase.
        """
        _BATCH_SIZE = 20

        if not self._auto_expand:
            self._deferred_expand_queue.clear()
            self._expansion_phase = _ExpansionPhase.IDLE
            return

        if self._expansion_phase != _ExpansionPhase.SPECULATIVE:
            return

        proxy_model = self._table_filter.filter_model
        batch = self._deferred_expand_queue[:_BATCH_SIZE]
        self._deferred_expand_queue = self._deferred_expand_queue[_BATCH_SIZE:]

        for persistent_idx in batch:
            if not persistent_idx.isValid():
                continue
            if not self._model.canFetchMore(persistent_idx):
                continue
            proxy_idx = proxy_model.mapFromSource(persistent_idx)
            if proxy_idx.isValid():
                self._table.expand(proxy_idx)

        if self._deferred_expand_queue:
            QtCore.QTimer.singleShot(0, self._expand_deferred_batch)

    def _on_scroll_catch_up(self) -> None:
        """Expand visible unexpanded groups the user scrolled to.

        Debounced via a 100 ms single-shot timer so that rapid scroll
        events are coalesced into a single pass.
        """
        if not self._auto_expand:
            return

        if self._scroll_catch_up_timer is None:
            self._scroll_catch_up_timer = QtCore.QTimer(self)
            self._scroll_catch_up_timer.setSingleShot(True)
            self._scroll_catch_up_timer.setInterval(100)
            self._scroll_catch_up_timer.timeout.connect(
                self._expand_visible_unexpanded
            )
        self._scroll_catch_up_timer.start()

    def _expand_visible_unexpanded(self) -> None:
        """Expand any collapsed expandable rows currently in the viewport.

        Acts as a catch-up for rows that speculative Phase 2 hasn't
        reached yet.  Does **not** cancel speculative work.
        """
        if not self._auto_expand:
            return

        proxy_model = self._table_filter.filter_model
        vp = self._table.viewport()
        if vp.rect().isEmpty():
            return

        for proxy_idx in self._iter_visible_proxy_indices():
            if self._table.isExpanded(proxy_idx):
                continue
            src_idx = proxy_model.mapToSource(proxy_idx)
            if src_idx.isValid() and self._model.canFetchMore(src_idx):
                self._table.expand(proxy_idx)

    # ------------------------------------------------------------------
    # Column builder
    # ------------------------------------------------------------------

    def _build_columns(self, category: str) -> list[TableColumn]:
        _style = get_ayon_style_data("AYTableView", "default")
        font = self._table.font()
        metrics = QtGui.QFontMetrics(font)
        h_pad = _style.get("header-padding", [4, 8])[0] * 4
        indicator_width = _style.get("indicator-width", 16)

        def _w(col_name: str, default: int = 75) -> int:
            return max(
                metrics.horizontalAdvance(col_name) + h_pad + indicator_width,
                default,
            )

        controller = self._controller

        def _thumb_widget_factory(
            index: QtCore.QModelIndex,
            parent: QtWidgets.QWidget,
        ) -> PlaceholderThumbnail:
            """Return a cheap placeholder; the real thumbnail is lazy.

            Args:
                index: Display-model index for the cell.
                parent: Viewport widget passed by the delegate.

            Returns:
                A :class:`PlaceholderThumbnail` sized ``(66, 32)``.
            """
            row_dict = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            thumbnail_id = row_dict.get("thumbnailId", "")
            version_id = row_dict.get("_version_id") or row_dict.get("id", "")
            project = controller.current_project
            request_id = self._model.request_id

            def _make_real() -> LazyThumbnailWidget | None:
                if not thumbnail_id or not version_id or not project:
                    return None
                key = f"{project}/{version_id}/{thumbnail_id}"
                return LazyThumbnailWidget(
                    key=key,
                    context_id=request_id,
                    size=(66, 32),
                )

            return PlaceholderThumbnail(
                make_real=_make_real,
                parent=parent,
                alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
            )

        common = [
            TableColumn(
                "thumb",
                "Thumbnail",
                width=_w("Thumbnail"),
                sortable=False,
                filterable=False,
                widget_factory=_thumb_widget_factory,
            ),
            TableColumn(
                "product/version",
                "Product/Version",
                width=_w("Product/Version", 300),
                icon="layers",
                tree_position=True,
            ),
            TableColumn(
                "status",
                "Status",
                width=_w("Status", 120),
                icon="circle",
            ),
        ]

        attributes = [
            TableColumn(
                name,
                data.get("title", name),
                width=_w(data.get("title", name)),
                icon=get_attribute_icon(
                    name, data.get("type"), data.get("enum")
                ),
            )
            for name, data in self._controller.version_attributes.items()
        ]

        hierarchy = [
            TableColumn(
                "entityType",
                "Entity Type",
                width=_w("Entity Type"),
                icon="layers",
            ),
            TableColumn(
                "productType",
                "Product Type",
                width=_w("Product Type"),
                icon="category",
            ),
            TableColumn(
                "folderName",
                "Folder Name",
                width=_w("Folder Name"),
                icon="folder",
            ),
            TableColumn("author", "Author", width=_w("Author"), icon="person"),
            TableColumn(
                "version",
                "Version",
                width=_w("Version"),
                icon="history",
            ),
            TableColumn(
                "productName",
                "Product Name",
                width=_w("Product Name", 150),
                icon="inventory_2",
            ),
            TableColumn(
                "taskType",
                "Task Type",
                width=_w("Task Type"),
                icon="task_alt",
            ),
            TableColumn("task", "Task", width=_w("Task"), icon="task"),
            TableColumn("tags", "Tags", width=_w("Tags"), icon="label"),
        ]

        review_sessions = [
            TableColumn("tags", "Tags", width=_w("Tags"), icon="label"),
            TableColumn(
                "productType",
                "Product Type",
                width=_w("Product Type"),
                icon="category",
            ),
            TableColumn(
                "taskType",
                "Task Type",
                width=_w("Task Type"),
                icon="task_alt",
            ),
            TableColumn(
                "entityType",
                "Entity Type",
                width=_w("Entity Type"),
                icon="layers",
            ),
            TableColumn("author", "Author", width=_w("Author"), icon="person"),
            TableColumn(
                "version",
                "Version",
                width=_w("Version"),
                icon="history",
            ),
            TableColumn(
                "productName",
                "Product Name",
                width=_w("Product Name", 150),
                icon="inventory_2",
            ),
        ]

        if category == ReviewCategory.HIERARCHY.value:
            return common + hierarchy + attributes
        return common + review_sessions + attributes
