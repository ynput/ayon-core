"""Right-hand panel that shows a paginated table of versions."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterator, Literal

import ayon_api
from ayon_core.ui.components.card_view import AYCardView
from ayon_core.ui.components.buttons import AYButton
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.table_filter import (
    AYTableFilter,
    FilterCriterion,
)
from ayon_core.ui.components.table_model import FilterEntry, TableColumn
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.combo_box import AYComboBox
from ayon_core.ui.components.views import (
    AYViewSelector,
    ServerViewManager,
    View,
    ViewBindings,
    ViewSettings,
)
from ayon_core.ui.image_cache import ImageCache
from ayon_core.ui.style import get_ayon_style_data
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.browser_controller import BrowserController
from ayon_core.tools.browser.ui.browser_group_by import (
    GROUP_BY_PRODUCT_KEY,
    GroupByOption,
    get_attribute_icon,
)
from ayon_core.tools.browser.ui.browser_types import BrowserSlicerCategory
from ayon_core.tools.browser.view_defaults import BROWSER_VIEW_DEFAULTS

from ._browser_model import VisibilityAwarePaginatedTableModel
from ._browser_thumbnails import (
    LazyThumbnailWidget,
    PlaceholderThumbnail,
    _make_card_async_fetcher,
    _browser_card_mapper,
    _thumbnail_loader,
)
from ._browser_toolbar import (
    AddColumnButton,
    Customize,
    DisplayType,
    GroupByMenu,
)

log = Logger.get_logger(__name__)

BROWSER_VIEW_TYPE = "desktop.browser"


class LoadedInSceneDelegate(QtWidgets.QStyledItemDelegate):
    """Display and colorize the loaded-in-scene state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._colors = {
            1: QtGui.QColor(80, 170, 80),
            0: QtGui.QColor(90, 90, 90),
        }
        self._default_color = QtGui.QColor(90, 90, 90)

    def displayText(self, value, locale):
        if value == 0:
            return "No"
        if value == 1:
            return "Yes"
        return "N/A"

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)

        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        value = row_data.get("inScene")
        if isinstance(value, bool):
            value = int(value)
            option.text = self.displayText(value, QtCore.QLocale())
        color = self._colors.get(value, self._default_color)
        option.palette.setBrush(QtGui.QPalette.ColorRole.Text, color)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_CACHED_CURRENT_USER: str = ""
_CACHED_CURRENT_USER_FETCHED: bool = False


def _get_current_user() -> str:
    """Return the current user name, fetching once and caching thereafter.

    The AYON user does not change during a session, so a single network
    call is sufficient.  Returns an empty string when the call fails or
    the user is not authenticated.

    Returns:
        The authenticated user's name, or ``""`` on failure.
    """
    global _CACHED_CURRENT_USER, _CACHED_CURRENT_USER_FETCHED  # noqa: PLW0603
    if not _CACHED_CURRENT_USER_FETCHED:
        _CACHED_CURRENT_USER_FETCHED = True
        try:
            info = ayon_api.get_user() or {}
            _CACHED_CURRENT_USER = str(info.get("name", "") or "")
        except Exception:  # noqa: BLE001
            log.debug("Could not fetch current user name", exc_info=True)
    return _CACHED_CURRENT_USER


class _ExpansionPhase(Enum):
    IDLE = "idle"
    VISIBLE = "visible"
    SPECULATIVE = "speculative"


class BrowserTable(AYContainer):
    """Right-hand panel that shows a paginated table of versions."""

    display_type_changed = QtCore.Signal(QtWidgets.QAbstractItemView)
    default_view_message = QtCore.Signal(str, bool)
    filter_criteria_changed = QtCore.Signal(list)
    selection_refresh_requested = QtCore.Signal()

    def __init__(
        self,
        controller: BrowserController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=0,
            layout_spacing=0,
            **kwargs,
        )
        self._controller = controller
        self._table = AYTableView(self)
        self._table.set_row_height(BROWSER_VIEW_DEFAULTS.row_height)
        self._table.viewport().installEventFilter(self)
        self._version_combo: AYComboBox | None = None
        self._table.header().setSectionsMovable(True)
        self._table.header().setMouseTracking(True)
        self._table.header().installEventFilter(self)
        self._table.header().setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.header().customContextMenuRequested.connect(
            self._on_header_context_menu
        )
        columns = self._build_columns(self._controller.current_category)
        self._controller.set_requested_columns(
            {
                column.key
                for column in columns
                if column.key in BROWSER_VIEW_DEFAULTS.visible_column_keys
            }
        )
        self._model = VisibilityAwarePaginatedTableModel(
            fetch_page=self._controller.fetch_versions_page,
            fetch_page_batch=(self._controller.fetch_versions_page_batch),
            columns=columns,
            page_size=250,
        )
        self._model.set_view(self._table)

        initial_tree_mode = self._controller.group_by_key != "none"
        self._controller.set_tree_mode(initial_tree_mode)
        self._model.set_tree_mode(initial_tree_mode)

        self._table_filter = AYTableFilter(
            model=self._model,
            parent=self,
            filters=self._build_filters(),
            filter_locally=False,
            local_filter_keys=self._controller.get_extension_filter_keys(),
        )
        self._table_filter.filters_changed.connect(
            self._on_filters_changed
        )
        self._table_filter.filters_changed.connect(
            self.filter_criteria_changed
        )
        self._table.setModel(self._table_filter.filter_model)
        self._apply_default_column_state(columns)
        self._refresh_btn = AYButton(
            icon="sync",
            variant=AYButton.Variants.Surface,
        )
        self._refresh_btn.setToolTip("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_filter)

        _card_fetcher = _make_card_async_fetcher(self._model)

        def _card_mapper(row_data: dict) -> dict:
            data = _browser_card_mapper(row_data)
            data["async_file_cacher"] = _card_fetcher
            return data

        self._card_view = AYCardView(
            parent=self,
            card_width=BROWSER_VIEW_DEFAULTS.card_width,
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
            self._controller.current_category
            == BrowserSlicerCategory.HIERARCHY.value
        )
        self._controller.group_by_options_changed.connect(
            self._on_group_by_options_changed
        )

        self._display_type = DisplayType(
            self,
            initial_display_type=BROWSER_VIEW_DEFAULTS.display_type,
        )
        self._display_type.display_type_changed.connect(
            self._on_display_type_changed
        )
        self._customize = Customize(
            parent=self,
            initial_card_width=BROWSER_VIEW_DEFAULTS.card_width,
            initial_row_height=BROWSER_VIEW_DEFAULTS.row_height,
            initial_show_empty_groups=(
                BROWSER_VIEW_DEFAULTS.show_empty_groups
            ),
            initial_featured_version_order=(
                BROWSER_VIEW_DEFAULTS.featured_version_order
            ),
            initial_latest_per_folder=(
                BROWSER_VIEW_DEFAULTS.latest_per_folder
            ),
            initial_include_children=(
                BROWSER_VIEW_DEFAULTS.include_children
            ),
        )
        self._add_column_btn = AddColumnButton(self._table.header())
        self._add_column_btn.set_columns(self._model.columns)
        self._add_column_btn.column_state_changed.connect(
            self._on_custom_column_state_changed
        )
        self._customize.columns_requested.connect(
            self._show_columns_menu
        )
        self._columns_menu_timer = QtCore.QTimer(self)
        self._columns_menu_timer.setSingleShot(True)
        self._columns_menu_timer.timeout.connect(
            self._open_columns_menu
        )
        self._table.column_state_changed.connect(
            self._on_table_column_state_changed
        )
        header = self._table.header()
        header.geometriesChanged.connect(self._position_add_column_button)
        header.sectionMoved.connect(self._position_add_column_button)
        header.sectionResized.connect(self._position_add_column_button)
        self._table.horizontalScrollBar().valueChanged.connect(
            self._position_add_column_button
        )
        QtCore.QTimer.singleShot(0, self._on_table_column_state_changed)
        self._customize.set_show_empty_groups(
            not self._controller.hide_empty_groups
        )
        self._customize.show_empty_groups_changed.connect(
            self._on_show_empty_groups_changed
        )
        self._customize.card_size_changed.connect(
            self._card_view.set_card_width
        )
        self._customize.row_height_changed.connect(
            self._table.set_row_height
        )
        self._customize.featured_version_order_changed.connect(
            self._on_featured_version_order_changed
        )
        self._customize.include_children_changed.connect(
            self._on_include_children_changed
        )
        self._customize.set_include_children(
            self._controller.include_folder_children,
            disabled=(
                self._controller.current_category
                != BrowserSlicerCategory.HIERARCHY.value
            ),
        )
        self._customize.set_latest_per_folder(
            self._controller.latest_per_folder,
            disabled=self._controller.group_by_key == GROUP_BY_PRODUCT_KEY,
        )
        self._customize.latest_per_folder_changed.connect(
            self._on_latest_per_folder_changed
        )

        self._view_manager = ServerViewManager(
            project_name=self._controller.current_project or "",
            parent=self,
        )
        self._controller.project_changed.connect(
            self._view_manager.set_project
        )

        self._view_bindings = ViewBindings(
            model=self._model,
            table_view=self._table,
            card_view=self._card_view,
            filter_bar=self._table_filter,
            default_settings=self._get_default_view_settings,
            on_extra_apply=self._apply_view_extras,
            on_extra_capture=self._capture_view_extras,
            on_error=self._on_view_binding_error,
        )

        self._view_selector = AYViewSelector(
            bindings=self._view_bindings,
            manager=self._view_manager,
            view_type=BROWSER_VIEW_TYPE,
            current_user=_get_current_user(),
            user_access_level=50,
            allow_studio_scope=False,
            parent=self,
        )
        self._table.column_state_changed.connect(
            self._view_selector.notify_view_modified
        )
        self._view_selector.setToolTip("Views")
        self._view_selector.view_applied.connect(self._on_view_applied)
        self._view_selector.view_deleted.connect(
            lambda _: self._table_filter.set_active_criteria([])
        )
        self._view_selector.binding_error.connect(
            self._on_view_selector_error
        )
        self._view_selector.default_view_message.connect(
            self.default_view_message
        )
        self._display_type.display_type_changed.connect(
            self._view_selector.notify_view_modified
        )
        self._group_by_menu.group_by_changed.connect(
            self._view_selector.notify_view_modified
        )
        self._customize.show_empty_groups_changed.connect(
            self._view_selector.notify_view_modified
        )
        self._customize.card_size_committed.connect(
            self._view_selector.notify_view_modified
        )
        self._customize.row_height_committed.connect(
            self._view_selector.notify_view_modified
        )
        self._customize.featured_version_order_changed.connect(
            self._view_selector.notify_view_modified
        )

        toolbar = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_margin=0,
            layout_spacing=4,
        )
        toolbar.add_widget(self._view_selector, stretch=0)
        toolbar.add_widget(self._table_filter, stretch=1)
        toolbar.add_widget(self._refresh_btn, stretch=0)
        toolbar.add_widget(self._group_by_menu, stretch=0)
        toolbar.add_widget(self._display_type, stretch=0)
        toolbar.add_widget(self._customize, stretch=0)
        toolbar_area = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_margin=0,
            layout_spacing=0,
        )
        toolbar_area.add_widget(toolbar, stretch=0)
        toolbar_gap = QtWidgets.QWidget()
        toolbar_gap.setFixedHeight(4)
        toolbar_area.add_widget(toolbar_gap, stretch=0)
        self.add_widget(toolbar_area, stretch=0)

        self._views_stack = QtWidgets.QStackedLayout()
        self._views_stack.addWidget(self._table)
        self._views_stack.addWidget(self._card_view)
        self._empty_overlay = QtWidgets.QWidget(self)
        self._empty_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self._empty_overlay.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self._empty_overlay.setFocusPolicy(
            QtCore.Qt.FocusPolicy.NoFocus
        )
        self._empty_overlay.setAutoFillBackground(False)
        empty_layout = QtWidgets.QVBoxLayout(self._empty_overlay)
        empty_layout.setContentsMargins(8, 8, 8, 8)
        empty_layout.setSpacing(16)
        empty_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        info_icon = AYLabel(
            icon="info",
            icon_size=48,
            icon_color="#d3e5f6",
        )
        info_icon.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(info_icon)

        self._empty_label = AYLabel("", dim=True)
        self._empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self._empty_label)

        self._views_stack.setCurrentWidget(self._table)
        views_container = QtWidgets.QWidget(self)
        views_layout = QtWidgets.QGridLayout(views_container)
        views_layout.setContentsMargins(0, 0, 0, 0)
        views_layout.addLayout(self._views_stack, 0, 0)
        views_layout.addWidget(self._empty_overlay, 0, 0)
        self.add_widget(views_container)
        self._update_empty_state()

        self._auto_expand: bool = False
        self._expanded_node_ids: set[str] = set()
        self._deferred_expand_queue: list[QtCore.QPersistentModelIndex] = []
        self._expansion_phase: _ExpansionPhase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys: set[str] = set()
        self._scroll_catch_up_timer: QtCore.QTimer | None = None
        self._resize_timer: QtCore.QTimer | None = None

        self._model.rowsInserted.connect(self._on_rows_inserted_expand)
        self._model.loading_changed.connect(
            self._on_loading_changed,
            QtCore.Qt.ConnectionType.QueuedConnection,
        )
        self._table.expanded.connect(self._on_table_row_expanded)
        self._table.collapsed.connect(self._on_table_row_collapsed)
        self._table.verticalScrollBar().valueChanged.connect(
            self._on_scroll_catch_up
        )
        self._table.verticalScrollBar().valueChanged.connect(
            self._maybe_fetch_more
        )
        self._model.page_fetched.connect(self._on_page_fetched)

        # Install event filter to catch viewport resize events
        self._table.viewport().installEventFilter(self)

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        """Handle viewport resize and Version-cell double-click events.

        Debounces resize events via a 100 ms timer to avoid flooding the
        thumbnail fetch queue during continuous resizing.

        Args:
            obj: The object receiving the event.
            event: The event to filter.

        Returns:
            ``False`` to allow the event to propagate.
        """
        if obj is self._table.viewport():
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                if self._version_combo is not None:
                    combo_rect = self._version_combo.geometry()
                    if not combo_rect.contains(event.pos()):
                        self._close_version_picker()
                return False
            if event.type() == QtCore.QEvent.Type.MouseButtonDblClick:
                index = self._table.indexAt(event.pos())
                if index.isValid() and self._is_version_index(index):
                    self._open_version_picker(index)
                    return True
            elif event.type() != QtCore.QEvent.Type.Resize:
                return False

            # Debounce resize events similar to scroll events
            if event.type() == QtCore.QEvent.Type.Resize:
                self._on_viewport_resize()
        elif obj is self._table.header():
            if event.type() == QtCore.QEvent.Type.Enter:
                self._add_column_btn.show()
            elif event.type() == QtCore.QEvent.Type.Leave:
                self._add_column_btn.hide()
        return False

    def _is_version_index(self, index: QtCore.QModelIndex) -> bool:
        """Return whether *index* is a replaceable Version cell."""
        if index.column() >= len(self._model.columns):
            return False
        if self._model.columns[index.column()].key != "version":
            return False
        source_index = self._source_index(index)
        row_data = source_index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        return (
            row_data.get("entityType") == "Version"
            and bool(row_data.get("productId"))
        )

    def _source_index(
        self,
        index: QtCore.QModelIndex,
    ) -> QtCore.QModelIndex:
        """Map a displayed index through any filter proxy to the source."""
        model = index.model()
        source_index = index
        while isinstance(model, QtCore.QAbstractProxyModel):
            source_index = model.mapToSource(source_index)
            model = model.sourceModel()
        return source_index

    def _open_version_picker(self, index: QtCore.QModelIndex) -> None:
        """Fetch and display versions for the double-clicked product."""
        source_index = self._source_index(index)
        row_data = source_index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        product_id = row_data.get("productId")
        if not product_id:
            return

        self._close_version_picker()

        combo = AYComboBox(self._table.viewport())
        self._version_combo = combo
        combo.setMinimumWidth(
            max(self._table.columnWidth(index.column()), 140)
        )
        combo.setGeometry(self._table.visualRect(index))
        combo.installEventFilter(self)

        def _on_versions_ready(
            versions: list[dict[str, Any]] | None,
        ) -> None:
            if combo is not self._version_combo:
                return
            if not versions:
                self._close_version_picker()
                return

            combo.clear()

            current_id = row_data.get("id")
            selected = 0
            for idx, version in enumerate(reversed(versions)):
                label = str(version.get("version", ""))
                if version.get("id") == current_id:
                    selected = idx
                combo.addItem(label, version)
            combo.setCurrentIndex(selected)
            combo.show()
            combo.showPopup()

        def _on_version_selected(position: int) -> None:
            version = combo.itemData(position)
            if not isinstance(version, dict):
                return
            replaced = self._model.replace_row(source_index, version)
            self._close_version_picker()
            if replaced:
                self.selection_refresh_requested.emit()

        combo.activated.connect(_on_version_selected)
        get_task_queue().enqueue(
            AsyncTask(
                name=f"browser_product_versions_{product_id}",
                function=lambda: self._controller.fetch_product_versions(
                    product_id
                ),
                callback=_on_versions_ready,
                priority=1,
                cancellable=True,
            )
        )

    def _close_version_picker(self) -> None:
        """Close and discard the transient Version picker."""
        combo = self._version_combo
        if combo is None:
            return
        self._version_combo = None
        combo.removeEventFilter(self)
        combo.hidePopup()
        combo.deleteLater()

    def _on_viewport_resize(self) -> None:
        """Debounced handler for viewport resize events.

        Uses a 100 ms single-shot timer to coalesce rapid resize events
        into a single thumbnail refresh pass. Only triggers if the table
        has been populated with data.
        """
        # Don't fetch thumbnails if the table hasn't been populated yet
        if self._model.rowCount() == 0:
            return

        if self._resize_timer is None:
            self._resize_timer = QtCore.QTimer(self)
            self._resize_timer.setSingleShot(True)
            self._resize_timer.setInterval(100)
            self._resize_timer.timeout.connect(
                self._on_viewport_resized
            )
        self._resize_timer.start()

    def _on_table_row_expanded(self, proxy_index: QtCore.QModelIndex) -> None:
        """Fetch children after Qt has committed a row expansion."""
        node_id = self._get_node_id(proxy_index)
        if node_id:
            self._expanded_node_ids.add(node_id)

        source_index = self._table_filter.filter_model.mapToSource(
            proxy_index
        )
        if source_index.isValid():
            # The model deliberately hides fetchability for collapsed rows
            # to stop Qt prefetching every visible group. At this point Qt
            # has just expanded the row, so explicitly request its first
            # child page.
            self._model.fetchMore(source_index)

    def _on_table_row_collapsed(
        self, proxy_index: QtCore.QModelIndex
    ) -> None:
        """Forget a row's expansion state after it is collapsed."""
        node_id = self._get_node_id(proxy_index)
        if node_id:
            self._expanded_node_ids.discard(node_id)

    def _get_node_id(self, proxy_index: QtCore.QModelIndex) -> str:
        """Return the stable identifier stored on a table row."""
        row_data = proxy_index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        node_id = row_data.get("id")
        return str(node_id) if node_id else ""

    def _restore_expanded_rows(
        self,
        parent: QtCore.QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Restore tracked expansions for newly inserted rows."""
        proxy_model = self._table_filter.filter_model
        for row in range(first, last + 1):
            source_index = self._model.index(row, 0, parent)
            node_id = self._get_node_id(
                proxy_model.mapFromSource(source_index)
            )
            if not node_id or node_id not in self._expanded_node_ids:
                continue

            proxy_index = proxy_model.mapFromSource(source_index)
            if proxy_index.isValid() and not self._table.isExpanded(
                proxy_index
            ):
                self._table.expand(proxy_index)

    def _on_viewport_resized(self) -> None:
        """Refresh visible thumbnails after the viewport has settled.

        Mirrors what ``_on_page_fetched`` does: first force-repaint the
        viewport so that ``LazyThumbnailWidget.paintEvent`` fires for
        rows whose thumbnails are already cached (they are skipped by
        ``_eagerly_enqueue_visible_thumbnails``), then enqueue fetches
        for any thumbnails not yet in the cache.
        """
        vp = self._table.viewport()
        if not shiboken.isValid(vp):
            return
        vp.update()
        self._eagerly_enqueue_visible_thumbnails()

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
        self._model.set_fetch_enabled(self._controller.has_selection)
        self._model.reset_data()
        self._update_empty_state()

    def clear_expansion_state(self) -> None:
        """Clear remembered row expansions without reloading the model."""
        self._reset_expansion_state()

    def refresh_filter(self) -> None:
        """Refresh data using the active query filter criteria."""
        self._controller.set_filter_criteria(
            self._table_filter.get_criteria()
        )
        self._model.set_fetch_enabled(self._controller.has_selection)
        self._model.reset_data()
        self._update_empty_state()

    def set_task_filter_names(self, names: list[str]) -> None:
        """Replace the Task criterion while preserving other filters."""
        criteria = [
            criterion
            for criterion in self._table_filter.get_criteria()
            if criterion.key != "task"
        ]
        if names:
            criteria.append(
                FilterCriterion(
                    key="task",
                    attribute_label="Task",
                    values=list(names),
                )
            )
        self._table_filter.set_active_criteria(criteria)

    def _on_filters_changed(
        self,
        criteria: list[FilterCriterion],
    ) -> None:
        """Refetch rows after changing the server-side filters."""
        self._controller.set_filter_criteria(criteria)
        self._model.reset_data()

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
        current_states = self._table.get_column_state()
        self._model.set_fetch_enabled(False)
        self._enqueued_thumb_keys.clear()
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._group_by_menu.set_options(
            self._controller.get_group_by_options(),
            self._controller.group_by_key,
        )
        by_name = self._controller.project_info.get("by_name", {})
        statuses = self._controller.project_info.get("statuses", [])
        status_values = {
            "status": [],
            "productStatus": [],
            "folderStatus": [],
            "taskStatus": [],
        }
        status_scopes = {
            "version": "status",
            "product": "productStatus",
            "folder": "folderStatus",
            "task": "taskStatus",
        }
        for status in statuses:
            for scope in status.get("scope", []) or []:
                key = status_scopes.get(scope)
                if key is not None:
                    status_values[key].append(status["name"])
        all_status_names = sorted(by_name.get("statuses", {}))
        for key, values in status_values.items():
            if not values:
                status_values[key] = all_status_names
        self._table_filter.set_column_filter_values({
            "productBaseType": sorted(
                by_name.get("productBaseTypes", {})
            ),
            **{
                key: sorted(values)
                for key, values in status_values.items()
            },
            "productType": sorted(by_name.get("productTypes", {})),
            "taskType": sorted(by_name.get("taskTypes", {})),
            "tags": sorted(by_name.get("tags", {})),
            "taskTags": sorted(by_name.get("tags", {})),
        })
        self._model.reset_data()
        self._model.set_columns(
            self._build_columns(self._controller.current_category)
        )
        self._controller.set_requested_columns({
            state.name for state in current_states if state.visible
        })
        self._table_filter.set_columns(self._model.columns)
        self._table_filter.set_filters(
            self._build_filters(),
            retain_unavailable_criteria=False,
        )
        self._table_filter.set_local_filter_keys(
            self._controller.get_extension_filter_keys()
        )
        self._add_column_btn.set_columns(self._model.columns)
        self._apply_preserved_column_state(current_states)
        self._update_empty_state()

    def on_category_changed(self, category: str) -> None:
        """Reset the table when the slicer category changes.

        Syncs the model's tree-mode flag with the controller — the
        controller has already normalised its own ``group_by_key`` and
        ``tree_mode`` for the new category in
        :meth:`ReviewController.set_category`.

        Args:
            category: New category value string.
        """
        current_states = self._table.get_column_state()
        self._reset_expansion_state()
        self._model.set_fetch_enabled(False)
        self._model.set_tree_mode(
            self._controller.tree_mode,
            reset_data=False,
        )
        self._group_by_menu.set_options(
            self._controller.get_group_by_options(),
            self._controller.group_by_key,
        )
        self._model.set_columns(
            self._build_columns(category),
            reset_data=False,
        )
        self._model.reset_data()
        self._controller.set_requested_columns({
            state.name for state in current_states if state.visible
        })
        self._table_filter.set_columns(self._model.columns)
        self._table_filter.set_filters(
            self._build_filters(),
            retain_unavailable_criteria=False,
        )
        self._table_filter.set_local_filter_keys(
            self._controller.get_extension_filter_keys()
        )
        self._add_column_btn.set_columns(self._model.columns)
        self._apply_preserved_column_state(current_states)
        self._group_by_menu.setVisible(
            category == BrowserSlicerCategory.HIERARCHY.value
        )
        self._customize.set_include_children(
            self._controller.include_folder_children,
            disabled=category != BrowserSlicerCategory.HIERARCHY.value,
        )
        self._view_selector.set_view_type(BROWSER_VIEW_TYPE)
        self._update_empty_state()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _reset_expansion_state(self) -> None:
        """Clear expansion state and queues."""
        self._auto_expand = False
        self._expanded_node_ids.clear()
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
        self._update_empty_state()
        if not shiboken.isValid(active.viewport()):
            return
        if self._views_stack.currentWidget() is not active:
            return

        active.viewport().update()

        if active is self._card_view:
            self._card_view.refresh_visible_editors()

        if active is self._table:
            self._eagerly_enqueue_visible_thumbnails()

        self.display_type_changed.emit(active)

    def _on_include_children_changed(self, enabled: bool) -> None:
        """Update descendant-folder querying for the hierarchy slicer."""
        self._controller.set_include_folder_children(enabled)
        self._model.reset_data()
        self._update_empty_state()
        self._view_selector.notify_view_modified()

    def _on_header_context_menu(self, position: QtCore.QPoint) -> None:
        """Offer hiding the clicked table column."""
        header = self._table.header()
        logical = header.logicalIndexAt(position)
        if logical < 0:
            return
        menu = QtWidgets.QMenu(self._table)
        hide_action = menu.addAction("Hide column")
        hide_action.setEnabled(
            sum(
                not header.isSectionHidden(index)
                for index in range(header.count())
            ) > 1
        )
        if menu.exec(header.mapToGlobal(position)) == hide_action:
            header.setSectionHidden(logical, True)
            self._on_table_column_state_changed()

    def _on_custom_column_state_changed(self, states: list) -> None:
        """Apply column customization changes to the table header."""
        from ayon_core.ui.components.views.data_models import ColumnState

        if states and not any(state["visible"] for state in states):
            states[0]["visible"] = True
        current_by_name = {
            state.name: state for state in self._table.get_column_state()
        }
        self._table.set_column_state(
            [
                ColumnState(
                    name=state["name"],
                    visible=state["visible"],
                    pinned=(
                        current_by_name[state["name"]].pinned
                        if state["name"] in current_by_name
                        else False
                    ),
                    width=(
                        current_by_name[state["name"]].width
                        if state["name"] in current_by_name
                        else None
                    ),
                )
                for state in states
            ]
        )

    def _show_columns_menu(self) -> None:
        """Open the shared frontend-style menu from Customize."""
        self._add_column_btn.show_menu(self._customize)

    def _open_columns_menu(self) -> None:
        self._add_column_btn.show_menu(self._customize)

    def _on_table_column_state_changed(self) -> None:
        """Synchronize visible columns with the version query selection."""
        states = self._table.get_column_state()
        self._add_column_btn.set_column_state(states)
        requested_columns_changed = self._controller.set_requested_columns({
            state.name for state in states if state.visible
        })
        if requested_columns_changed:
            self._model.set_fetch_enabled(self._controller.has_selection)
            self._model.reset_data()
        self._position_add_column_button()

    def _update_empty_state(self) -> None:
        """Show the shared empty state when no rows are available."""
        show_empty = not self._model.is_loading and not self._model.rowCount()
        self._empty_overlay.setVisible(show_empty)
        if show_empty:
            has_selection = self._controller.has_selection
            self._empty_label.setText(
                "No versions or products found"
                if has_selection
                else "Select a folder to show versions or products"
            )
            self._empty_overlay.raise_()

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
        self.set_auto_expand(
            self._controller.has_selection and group_by_key == "none"
        )
        self._customize.set_latest_per_folder(
            self._controller.latest_per_folder,
            disabled=group_by_key == GROUP_BY_PRODUCT_KEY,
        )
        self._model.set_tree_mode(tree_mode)
        self._reset_expansion_state()
        self._model.reset_data()
        # Keep bindings' grouping state in sync so capture() round-trips
        # the live value even when no view has been applied yet.
        self._view_bindings._last_grouping.group_by = (
            None if group_by_key == "none" else group_by_key
        )

    def _on_show_empty_groups_changed(self, show_empty: bool) -> None:
        self._controller.set_hide_empty_groups(not show_empty)
        self._reset_expansion_state()
        self._model.reset_data()
        # Mirror the live state into the bindings for accurate capture.
        self._view_bindings._last_grouping.show_empty_groups = show_empty

    # ------------------------------------------------------------------
    # View selector integration
    # ------------------------------------------------------------------

    def _apply_view_extras(self, extra: dict[str, Any]) -> None:
        """Apply loader-specific extras from ``ViewSettings.extra``.

        Handles only keys that are **not** first-class ``ViewSettings``
        fields (i.e. not in ``_KNOWN_SETTINGS_KEYS``).  ``showEmptyGroups``
        and ``groupBy`` are first-class fields and therefore never appear
        in ``extra`` after a server round-trip — they are applied from
        ``view.settings.grouping`` inside :meth:`_on_view_applied`.

        Supported loader-specific extras:
            ``gridHeight`` (card width),
            ``featuredVersionOrder`` (hero/latest version order),
            ``displayType`` (``"table"`` or ``"grid"``).

        Args:
            extra: The settings ``extra`` dict from the applied view.
        """
        if "gridHeight" in extra:
            try:
                self._card_view.card_width = int(extra["gridHeight"])
            except (TypeError, ValueError):
                log.debug(
                    "Invalid gridHeight in view extras: %r",
                    extra["gridHeight"],
                )
        if "featuredVersionOrder" in extra:
            order = extra["featuredVersionOrder"]
            if isinstance(order, list):
                normalized_order = [str(item) for item in order]
                self._customize.set_featured_version_order(
                    normalized_order
                )
                # Use the controller directly rather than the full
                # _on_featured_version_order_changed handler, which also
                # calls reset_data.  bindings.apply() already called
                # apply_settings → reset_data, so we only need the
                # controller state update here; the product-grouping path
                # will re-fetch correctly in the _on_view_applied phase.
                try:
                    self._controller.set_featured_version_order(
                        normalized_order
                    )
                except Exception:  # noqa: BLE001
                    log.debug(
                        "Failed to set featuredVersionOrder: %r", order
                    )
        if "displayType" in extra:
            display_type: Literal["table", "grid"] = extra["displayType"]
            self._display_type.set_display_type(display_type)
        if "latestPerFolder" in extra:
            latest_per_folder = bool(extra["latestPerFolder"])
            self._customize.set_latest_per_folder(
                latest_per_folder,
                disabled=(
                    self._controller.group_by_key == GROUP_BY_PRODUCT_KEY
                ),
            )
            self._controller.set_latest_per_folder(latest_per_folder)
            self._model.reset_data()
        if "includeChildren" in extra:
            include_children = bool(extra["includeChildren"])
            self._customize.set_include_children(
                include_children,
                disabled=(
                    self._controller.current_category
                    != BrowserSlicerCategory.HIERARCHY.value
                ),
            )
            self._controller.set_include_folder_children(include_children)
            self._model.reset_data()

    def _capture_view_extras(self) -> dict[str, Any]:
        """Capture loader-specific extras for inclusion in a saved view.

        Only truly loader-specific keys that are NOT first-class
        ``ViewSettings`` fields should be written here.
        ``showEmptyGroups`` and ``groupBy`` are first-class fields on
        ``ViewSettings.grouping`` — they are captured automatically by
        :class:`ViewBindings` via ``_last_grouping`` and must not be
        duplicated in ``extra`` (``ViewSettings.to_payload`` silently
        drops known keys from ``extra``).

        Captured loader-specific extras include card width, featured
        version order, and current display type (table or grid).

        Returns:
            A dict merged into :attr:`ViewSettings.extra`.
        """
        extra: dict[str, Any] = {
            "gridHeight": int(self._card_view.card_width),
            "displayType": self._display_type.display_type,
            "featuredVersionOrder": (
                self._controller.featured_version_order
            ),
            "latestPerFolder": self._controller.latest_per_folder,
            "includeChildren": self._controller.include_folder_children,
        }
        return extra

    def _on_view_applied(self, view: object) -> None:
        """Propagate first-class grouping settings to toolbar/controller.

        :class:`ViewBindings` handles columns, sort, filter, and row
        height.  Grouping (``groupBy`` + ``showEmptyGroups``) lives on
        ``view.settings.grouping`` and is applied here because no
        grouping widget is wired into the bindings yet.

        Args:
            view: The applied :class:`View` instance (typed as
                ``object`` because the signal is declared with ``object``
                for Qt compatibility).
        """
        if not isinstance(view, View):
            log.debug("Applied view: %r", view)
            return
        log.debug("Applied view: %s (%s)", view.label, view.id)
        grouping = view.settings.grouping
        row_height = (
            view.settings.row_height
            if view.settings.row_height > 0
            else BROWSER_VIEW_DEFAULTS.row_height
        )
        self._customize.set_row_height(row_height)

        # --- showEmptyGroups -----------------------------------------------
        show_empty = grouping.show_empty_groups
        # Update UI widget directly (no signal, so no reset_data loop).
        self._customize.set_show_empty_groups(show_empty)
        # Sync controller state; bindings.apply already reset the model.
        self._controller.set_hide_empty_groups(not show_empty)
        self._view_bindings._last_grouping.show_empty_groups = show_empty

        # --- groupBy -------------------------------------------------------
        group_by = grouping.group_by or "none"
        if group_by != self._controller.group_by_key:
            # Update the menu widget first (silent, no signal emission).
            self._group_by_menu.set_options(
                self._controller.get_group_by_options(),
                group_by,
            )
            # Update controller + model tree mode and trigger a fresh
            # fetch with the new grouping key.  This is a second
            # reset_data after bindings.apply's reset, but is necessary
            # so the pagination uses the correct group_by key.
            self._on_group_by_changed(group_by)
        else:
            # groupBy unchanged — still keep last_grouping current.
            self._view_bindings._last_grouping.group_by = (
                None if group_by == "none" else group_by
            )

    def _on_view_binding_error(
        self, stage: str, exc: BaseException
    ) -> None:
        """Forward ViewBindings errors to the log.

        Args:
            stage: Identifier of the failing binding stage.
            exc: The caught exception.
        """
        log.warning("View binding %s failed: %s", stage, exc)

    def _on_view_selector_error(self, stage: str, message: str) -> None:
        """Log selector-surfaced binding errors.

        Args:
            stage: Identifier of the failing stage.
            message: Human-readable message from the bindings.
        """
        log.warning("View selector %s error: %s", stage, message)

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

    def _on_latest_per_folder_changed(self, enabled: bool) -> None:
        """Refetch versions after changing latest-per-folder filtering."""
        self._controller.set_latest_per_folder(
            enabled and self._controller.group_by_key != GROUP_BY_PRODUCT_KEY
        )
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
        QtCore.QTimer.singleShot(0, self._maybe_fetch_more)

    def _maybe_fetch_more(self) -> None:
        """Fetch more data when the active view is near its bottom."""
        active = self._views_stack.currentWidget()
        if active is self._card_view:
            self._card_view.fetch_more_if_needed()
            return
        if active is not self._table or self._controller.tree_mode:
            return

        scrollbar = self._table.verticalScrollBar()
        if (
            scrollbar.value() + scrollbar.pageStep()
            < scrollbar.maximum()
        ):
            return

        root = QtCore.QModelIndex()
        if self._model.canFetchMore(root):
            self._model.fetchMore(root)

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

        # Skip if table hasn't rendered yet
        if self._model.rowCount() == 0:
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

        self._restore_expanded_rows(parent, first, last)

    def _on_loading_changed(self, is_loading: bool) -> None:
        """Transition to speculative phase when visible loads finish.

        Connected to ``PaginatedTableModel.loading_changed`` with a
        ``QueuedConnection`` to avoid re-entrant issues.

        Args:
            is_loading: ``True`` while fetch tasks are pending.
        """
        self._update_empty_state()
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

    def _apply_default_column_state(
        self, columns: list[TableColumn]
    ) -> None:
        """Apply the compact loader-like default column visibility."""
        self._table.set_column_state(
            self._get_default_column_state(columns)
        )

    def _apply_preserved_column_state(self, states: list) -> None:
        """Apply known states and defaults for newly introduced columns."""
        column_names = {column.key for column in self._model.columns}
        merged_states = [
            state for state in states if state.name in column_names
        ]
        known_names = {state.name for state in merged_states}
        merged_states.extend(
            state
            for state in self._get_default_column_state()
            if state.name not in known_names
        )
        self._table.set_column_state(merged_states)
        self._add_column_btn.set_column_state(merged_states)
        self._position_add_column_button()

    def _position_add_column_button(self, *_args) -> None:
        """Position the add-column control after the last visible section."""
        header = self._table.header()
        visible_right = 0
        for logical in range(header.count()):
            if header.isSectionHidden(logical):
                continue
            visible_right = max(
                visible_right,
                header.sectionViewportPosition(logical)
                + header.sectionSize(logical),
            )
        x_pos = min(
            visible_right + 2,
            max(0, header.width() - self._add_column_btn.width()),
        )
        y_pos = max(
            0,
            (header.height() - self._add_column_btn.height()) // 2,
        )
        self._add_column_btn.move(x_pos, y_pos)
        # self._add_column_btn.raise_()

    def _get_default_column_state(
        self, columns: list[TableColumn] | None = None
    ) -> list:
        """Return the compact loader-like default column visibility."""
        if columns is None:
            columns = self._model.columns
        return self._get_default_view_settings(
            columns
        ).columns

    def _get_default_view_settings(
        self,
        columns: list[TableColumn] | None = None,
    ) -> ViewSettings:
        """Return complete Browser Working View defaults."""
        if columns is None:
            columns = self._model.columns
        return BROWSER_VIEW_DEFAULTS.create_settings(
            [column.key for column in columns]
        )

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
                A :class:`PlaceholderThumbnail` with a 1 px inset around
                the ``(64, 30)`` thumbnail.
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
                    size=(64, 30),
                )

            return PlaceholderThumbnail(
                make_real=_make_real,
                parent=parent,
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
                filterable=False,
            ),
            TableColumn(
                "status",
                "Status",
                width=_w("Status", 120),
                icon="circle",
            ),
            TableColumn(
                "inScene",
                "In Scene",
                width=_w("In Scene", 80),
                sortable=False,
                icon="how_to_reg",
                delegate=LoadedInSceneDelegate(self._table),
            ),
        ]

        builtin_attribute_names = {
            "fps",
            "frameStart",
            "frameEnd",
            "handleStart",
            "handleEnd",
            "step",
        }
        attributes = []
        for scope, definitions in (
            self._controller.attributes_by_scope.items()
        ):
            entity = scope.capitalize()
            for name, data in definitions.items():
                if name in builtin_attribute_names:
                    continue
                key = f"attr:{scope}:{name}"
                label = data.get("title", name)
                if scope != "version":
                    label = f"{entity} {label}"
                attributes.append(TableColumn(
                    key,
                    label,
                    width=_w(label),
                    icon=get_attribute_icon(
                        name, data.get("type"), bool(data.get("enum"))
                    ),
                    entity=entity,
                ))

        hierarchy = [
            TableColumn(
                "productBaseType",
                "Product Base Type",
                width=_w("Product Base Type"),
                icon="category",
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
                filterable=False,
                icon="folder",
            ),
            TableColumn("author", "Author", width=_w("Author"), icon="person"),
            TableColumn(
                "createdAt", "Time", width=_w("Time"), icon="schedule"
            ),
            TableColumn(
                "version",
                "Version",
                width=_w("Version"),
                icon="history",
                filterable=False,
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
            TableColumn(
                "frameStart", "Frame Start", width=_w("Frame Start"),
                icon="first_page",
            ),
            TableColumn(
                "frameEnd", "Frame End", width=_w("Frame End"),
                icon="last_page",
            ),
            TableColumn(
                "handleStart", "Handle Start", width=_w("Handle Start"),
                icon="first_page",
            ),
            TableColumn(
                "handleEnd", "Handle End", width=_w("Handle End"),
                icon="last_page",
            ),
            TableColumn("step", "Step", width=_w("Step"), icon="more_horiz"),
        ]

        review_sessions = [
            TableColumn(
                "productBaseType",
                "Product Base Type",
                width=_w("Product Base Type"),
                icon="category",
            ),
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
                "createdAt", "Time", width=_w("Time"), icon="schedule"
            ),
            TableColumn(
                "frameStart", "Frame Start", width=_w("Frame Start"),
                icon="first_page",
            ),
            TableColumn(
                "frameEnd", "Frame End", width=_w("Frame End"),
                icon="last_page",
            ),
            TableColumn(
                "handleStart", "Handle Start", width=_w("Handle Start"),
                icon="first_page",
            ),
            TableColumn(
                "handleEnd", "Handle End", width=_w("Handle End"),
                icon="last_page",
            ),
            TableColumn("step", "Step", width=_w("Step"), icon="more_horiz"),
        ]

        core_columns = common + (
            hierarchy
            if category == BrowserSlicerCategory.HIERARCHY.value
            else review_sessions
        ) + attributes
        core_keys = {column.key for column in core_columns}
        extension_columns = [
            column
            for column in self._controller.get_extension_columns()
            if column.key not in core_keys
        ]
        return core_columns + extension_columns

    def _build_filters(self) -> list[FilterEntry]:
        """Build the complete filter schema independently of the view."""
        filters = [
            FilterEntry(
                "productName", "Name",
                icon="inventory_2", entity="Product", text_search=True,
            ),
            FilterEntry(
                "productType", "Type",
                icon="category", entity="Product",
            ),
            FilterEntry(
                "productBaseType", "Base Type",
                icon="category", entity="Product",
            ),
            FilterEntry(
                "productStatus", "Status",
                icon="arrow_circle_right", entity="Product",
            ),
            FilterEntry(
                "status", "Status",
                icon="arrow_circle_right", entity="Version",
            ),
            FilterEntry(
                "version", "Version",
                values=["Latest", "Latest Done", "Hero"],
                icon="history", entity="Version",
            ),
            FilterEntry(
                "author", "Author",
                icon="person", entity="Version",
            ),
            FilterEntry(
                "tags", "Tags",
                icon="local_offer", entity="Version",
            ),
            FilterEntry(
                "folderName", "Name",
                icon="folder", entity="Folder", text_search=True,
            ),
            FilterEntry(
                "folderStatus", "Status",
                icon="arrow_circle_right", entity="Folder",
            ),
            FilterEntry("task", "Task", icon="task", entity="Task"),
            FilterEntry(
                "taskType", "Type",
                icon="task_alt", entity="Task",
            ),
            FilterEntry(
                "taskStatus", "Status",
                icon="arrow_circle_right", entity="Task",
            ),
            FilterEntry(
                "taskTags", "Tags",
                icon="local_offer", entity="Task",
            ),

            # "Loaded in Scene" filter is a special case, not an attribute, so
            # it is added here as a built-in filter.
            FilterEntry(
                "inScene", "In Scene",
                values=["Yes", "No"],
                icon="how_to_reg", entity="Version",
            ),
        ]

        # Add all attribute filters per entity type
        for scope, definitions in (
            self._controller.attributes_by_scope.items()
        ):
            entity = scope.capitalize()
            for name, data in definitions.items():
                attribute_type = str(data.get("type", "")).lower()
                if attribute_type in {
                    "date",
                    "datetime",
                    "date_time",
                    "date-time",
                }:
                    continue
                enum = data.get("enum")
                values = []
                value_labels = {}
                if isinstance(enum, dict):
                    values = [str(value) for value in enum]
                    value_labels = {
                        str(value): str(label)
                        for value, label in enum.items()
                    }
                elif isinstance(enum, (list, tuple)):
                    for item in enum:
                        if isinstance(item, dict):
                            value = item.get("value", item.get("name"))
                            label = item.get("label", value)
                        else:
                            value, label = item, item
                        if value is not None:
                            values.append(str(value))
                            value_labels[str(value)] = str(label)
                key = f"attr:{scope}:{name}"
                filters.append(FilterEntry(
                    key,
                    data.get("title", name),
                    values=values,
                    icon=get_attribute_icon(
                        name, data.get("type"), bool(enum)
                    ),
                    entity=entity,
                    value_labels=value_labels,
                    text_search=(
                        str(data.get("type", "")).lower() == "string"
                        and not enum
                    ),
                ))
        core_keys = {item.key for item in filters}
        filters.extend(
            item
            for item in self._controller.get_extension_filters()
            if item.key not in core_keys
        )
        return filters
