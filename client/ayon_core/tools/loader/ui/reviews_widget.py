from __future__ import annotations

import json
import tempfile
from enum import Enum
from typing import Any, Callable, Iterator

import ayon_api
from ayon_ui_qt.components.buttons import (
    AYButton,
    AYButtonMenu,
    ButtonMenuDropdown,
)
from ayon_ui_qt.components.card_view import AYCardView
from ayon_ui_qt.components.check_box import AYCheckBox
from ayon_ui_qt.components.combo_box import AYComboBox
from ayon_ui_qt.components.container import (
    AYContainer,
    AYHBoxLayout,
    AYVBoxLayout,
)
from ayon_ui_qt.components.dropdown import AYDropdownPopup
from ayon_ui_qt.components.entity_thumbnail import AYEntityThumbnail
from ayon_ui_qt.components.filter import AYFilter, FilterItem
from ayon_ui_qt.components.filterable_list import FilterableList
from ayon_ui_qt.components.label import AYLabel  # noqa: F401
from ayon_ui_qt.components.order import AYOrder
from ayon_ui_qt.components.page_button import AYPageButton
from ayon_ui_qt.components.slicer import AYSlicer
from ayon_ui_qt.components.slider import AYSlider
from ayon_ui_qt.components.table_filter import AYTableFilter
from ayon_ui_qt.components.table_model import PaginatedTableModel, TableColumn
from ayon_ui_qt.components.table_view import AYTableView
from ayon_ui_qt.components.task_queue import AsyncTask, get_task_queue
from ayon_ui_qt.components.task_queue_monitor import AsyncTaskQueueMonitor
from ayon_ui_qt.components.tree_model import LazyTreeModel
from ayon_ui_qt.components.tree_view import AYTreeView, QItemSelection
from ayon_ui_qt.image_cache import ImageCache
from ayon_ui_qt.style import get_ayon_style_data
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger, log_timing
from ayon_core.tools.loader.ui.actions_utils import show_actions_menu
from ayon_core.tools.loader.ui.review_controller import (
    GROUP_BY_PRODUCT_KEY,
    GroupByOption,
    ReviewController,
    get_attribute_icon,
)
from ayon_core.tools.loader.ui.review_types import ReviewCategory
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.user_prefs import UserPreferences

log = Logger.get_logger(__name__)


def _review_card_mapper(row_data: dict) -> dict:
    # print(f"row_data: {json.dumps(row_data, indent=4)}")
    key: str = (
        f"{row_data.get('project_name', '')}/"
        f"{row_data.get('id', '')}/"
        f"{row_data.get('thumbnailId', '')}"
    )
    return {
        "header": row_data.get("folderName", ""),
        "title": row_data.get("productName", ""),
        "title_icon": row_data.get("productType__icon", ""),
        "title_color": row_data.get("productType__color", ""),
        "status": (
            {
                "name": "",
                "color": row_data.get("status__color", ""),
                "icon": row_data.get("status__icon", ""),
            }
            if row_data.get("status")
            else None
        ),
        "version": row_data.get("version", "")
        + ("★" if row_data.get("heroVersionId") else ""),
        "image_src": key,
        "placeholder_icon": row_data.get("productType__icon", "image"),
    }


def _thumbnail_loader(key: str) -> str:
    """Fetch a version thumbnail from AYON and persist it to a temp file.

    Args:
        key: Cache key in the form:
          ``"<project_name>/<version_id>/<thumbnail_id>"``.

    Returns:
        Absolute path to the saved image file, or empty string when the
        version has no thumbnail (which will be caught by the factory).
    """
    with log_timing(f"Fetching thumbnail for key {key}"):
        if not key:
            log.debug("  |_ No thumbnail key provided; skipping fetch")
            return ""

        ic = ImageCache.get_instance()

        def _fetch() -> str:
            log.debug("  |_ Cache miss; fetching from ayon API: %r", key)
            project_name, version_id, thumbnail_id = key.split("/", 2)
            content = ayon_api.get_version_thumbnail(
                project_name, version_id, thumbnail_id
            )
            if not content.is_valid:
                return ""
            ext = (
                ".jpg"
                if content.content_type and "jpeg" in content.content_type
                else ".png"
            )
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
                fh.write(content.content)
                return fh.name

        try:
            return ic.get(key, _fetch)
        except Exception:
            log.debug(
                "Failed to fetch thumbnail for key %r", key, exc_info=True
            )
            return ""


def _make_card_async_fetcher(
    model: "VisibilityAwarePaginatedTableModel",
) -> "Callable[[str, Callable[[str], None]], None]":
    """Return an async thumbnail fetcher for use with ``AYEntityCard``.

    The returned callable matches the ``async_file_cacher`` signature
    expected by
    :class:`ayon_ui_qt.components.entity_thumbnail.AYEntityThumbnail`:
    ``(key: str, on_loaded: Callable[[str], None]) -> None``.

    On each call it enqueues an :class:`AsyncTask` on the shared task
    queue at priority 2.  If the key is already in ``ImageCache`` it
    calls ``on_loaded`` synchronously with the cached path so the card
    updates without waiting for the task queue.

    The ``context_id`` is read from *model*'s ``request_id`` property
    at enqueue time — not at closure creation — so tasks automatically
    belong to the right request context even after model resets.

    Args:
        model: The paginated table model; provides the current request
            context ID via :attr:`request_id`.

    Returns:
        A non-blocking fetcher callable suitable for
        ``AYEntityCard(async_file_cacher=...)``.

    Note:
        The ``on_loaded`` callback is invoked by
        :class:`AYEntityThumbnail` which already wraps it with a
        ``weakref`` guard, so no additional widget-validity check is
        required here.
    """

    def _fetcher(key: str, on_loaded: "Callable[[str], None]") -> None:
        # Validate: key must have the form "project/version_id/thumbnail_id"
        # with all three parts non-empty.
        parts = key.split("/", 2) if key else []
        if len(parts) != 3 or not all(parts):
            return

        ic = ImageCache.get_instance()
        if ic.has(key):
            # Fast path: cache hit — no task needed.
            cached = ic.get_path(key)
            if cached:
                on_loaded(cached)
            return

        get_task_queue().enqueue(
            AsyncTask(
                name=f"card_thumb_{key}",
                function=lambda k=key: _thumbnail_loader(k),
                callback=on_loaded,
                priority=2,
                context_id=model.request_id,
                cancellable=True,
            )
        )

    return _fetcher


class LazyThumbnailWidget(AYEntityThumbnail):
    """Thumbnail widget that defers loading until the first paint event.

    Persistent-editor widgets only receive ``paintEvent`` when they are
    within the viewport's visible area.  By deferring the async thumbnail
    fetch to the first paint, we avoid issuing network requests for
    off-screen rows.

    Thumbnail tasks are enqueued on the shared
    :class:`AsyncTaskQueue` at priority 2 so they can start promptly
    once visible page data has arrived, while off-screen page fetches
    remain deprioritized.

    Args:
        key: ImageCache key in the form
            ``"<project>/<version_id>/<thumbnail_id>"``.
        context_id: Model request-ID used to scope the task-queue
            entry so stale tasks can be cancelled on model reset.
        size: ``(width, height)`` dimensions for the thumbnail.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        key: str,
        context_id: str,
        size: tuple[int, int] = (66, 32),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(size=size, parent=parent, fade_duration=500)
        self._thumb_key: str = key
        self._context_id: str = context_id
        self._load_requested: bool = False

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        """Load the thumbnail on the first paint, using the cache when hot.

        On the first paint event:

        1. Check ``ImageCache`` — if the image is already cached (e.g.
           because an eager pre-fetch fired in :meth:`_on_page_fetched`),
           call :meth:`set_thumbnail` synchronously and skip the async
           enqueue.
        2. Otherwise, enqueue an async fetch at priority 2.  The callback
           calls :meth:`set_thumbnail` once the worker thread completes.

        Args:
            event: The paint event forwarded to the parent class.
        """
        if not self._load_requested:
            self._load_requested = True
            ic = ImageCache.get_instance()
            cached_path = (
                ic.get_path(self._thumb_key) if self._thumb_key else None
            )
            if cached_path:
                # Cache hit — load synchronously, no async task needed.
                with log_timing(
                    "Thumbnail sync-load for key %r" % self._thumb_key
                ):
                    self.set_thumbnail(cached_path)
            else:
                w = self

                def _on_thumb_loaded(_w, _fpath) -> None:
                    if not shiboken.isValid(_w):
                        return
                    _w.set_thumbnail(_fpath)

                get_task_queue().enqueue(
                    AsyncTask(
                        name=f"thumbnail_loader_{self._thumb_key}",
                        function=lambda: _thumbnail_loader(self._thumb_key),
                        callback=lambda fpath: (_on_thumb_loaded(w, fpath)),
                        priority=2,
                        context_id=self._context_id,
                    )
                )
        super().paintEvent(event)


class PlaceholderThumbnail(QtWidgets.QWidget):
    """Lightweight placeholder widget that creates the real thumbnail lazily.

    The widget returned by a ``widget_factory`` is instantiated by Qt as
    soon as ``openPersistentEditor`` is called, whether or not the row is
    visible.  This class acts as a near-zero-cost stand-in: construction
    costs a single ``QWidget`` allocation plus ``setFixedSize``.  The
    real :class:`LazyThumbnailWidget` is only created on the first
    ``paintEvent``, i.e. when the row actually scrolls into view.

    This pairs with the viewport-aware editor management in
    ``AYTableView`` (Strategy 1).  Even if an editor is opened for an
    off-screen row, the real thumbnail widget (and its async network
    fetch) will not be triggered until that row becomes visible.

    Args:
        make_real: Callable with no arguments that returns the real
            :class:`LazyThumbnailWidget` when invoked.
        alignment: Alignment flag for the widget.
        parent: Optional parent widget (viewport).
    """

    def __init__(
        self,
        make_real: Callable | None,
        alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._make_real: Callable | None = make_real
        self._real: QtWidgets.QWidget | None = None
        self._lyt = None
        self._alignment = alignment

    def _create_layout(self) -> None:
        self._lyt = QtWidgets.QHBoxLayout()
        self._lyt.setContentsMargins(0, 0, 0, 0)
        self._lyt.setAlignment(self._alignment)
        self.setLayout(self._lyt)

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        """Materialise the real thumbnail widget on the first paint.

        Because ``paintEvent`` is only called when the widget is within
        the visible viewport, the real widget (and its expensive
        constructor) is never created for off-screen rows.

        Args:
            event: The paint event forwarded to the real widget.
        """
        if self._make_real and self._real is None:
            self._real = self._make_real()
            if self._real:
                self._create_layout()
                assert self._lyt is not None
                self._lyt.addWidget(self._real, stretch=1)
        super().paintEvent(event)


class VisibilityAwarePaginatedTableModel(PaginatedTableModel):
    """Paginated table model that deprioritize off-screen page fetches.

    Overrides :meth:`_get_fetch_priority` so that page-fetch tasks for a
    parent node that is **not** currently visible in the table's viewport
    are enqueued at priority **20** (very low / background prefetch)
    instead of the default 0 (Critical) or 1 (High).  This keeps the task
    queue fully responsive for visible rows and thumbnail fetches (priority
    2) when many nodes are expanded simultaneously (e.g. via auto-expand).

    Priority scale used by this widget:

    - ``0`` – Visible first-page fetches
    - ``1`` – Visible subsequent-page fetches
    - ``2`` – Thumbnail fetches
    - ``20`` – Off-screen page fetches

    Call :meth:`set_view` after construction to attach the view whose
    viewport is used for visibility checks.  When no view is attached the
    class falls back to the default behaviour (high priority for all
    fetches).
    """

    _OFF_SCREEN_PRIORITY: int = 20

    def __init__(self, *args, **kwargs) -> None:
        self._view: AYTableView | None = None
        self._priority_cache: dict[tuple[int, int], int] = {}
        self._priority_cache_clear_scheduled: bool = False
        super().__init__(*args, **kwargs)

    def set_view(self, view: AYTableView) -> None:
        """Attach the view whose viewport is used for visibility checks.

        Args:
            view: The :class:`AYTableView` that displays this model.
                Its viewport geometry and visual rects are used to
                determine whether a parent row is currently on-screen.
        """
        self._view = view

    @property
    def request_id(self) -> str:
        """Return the current request context ID.

        Exposes the base-class ``_request_id`` as a public read-only
        property so that external thumbnail fetchers can scope their
        :class:`AsyncTask` entries correctly.  The ID is regenerated on
        every :meth:`reset_data` call, so stale tasks are automatically
        cancelled by the task queue.

        Returns:
            UUID string identifying the current fetch context.
        """
        return self._request_id

    def _is_parent_visible(self, node: object) -> bool:
        """Return True when *node*'s row is within the viewport.

        Fails open (returns ``True``) in all ambiguous situations so
        that a fetch is never permanently starved:

        - Root nodes (invisible root that owns all top-level rows).
        - No view attached yet.
        - Source model index is invalid.
        - Proxy model has filtered the row out (not on screen anyway).

        Args:
            node: A :class:`_TableNode` instance from the base model.

        Returns:
            ``True`` if the parent row is visible or if the check
            cannot be performed conclusively; ``False`` only when a
            valid visual rect lies entirely outside the viewport.
        """
        if getattr(node, "is_root", True) or self._view is None:
            return True

        src_idx = self._index_for_node(node)  # type: ignore[attr-defined]
        if not src_idx.isValid():
            return True

        proxy_model = self._view.model()
        if proxy_model is None:
            return True

        if isinstance(proxy_model, QtCore.QAbstractProxyModel):
            proxy_idx = proxy_model.mapFromSource(src_idx)
        else:
            proxy_idx = src_idx

        if not proxy_idx.isValid():
            # Row is filtered out — not on screen.
            return False

        vp_rect = self._view.viewport().rect()
        visual = self._view.visualRect(proxy_idx)
        return vp_rect.intersects(visual)

    def _get_fetch_priority(self, node: object, page: int) -> int:
        """Return priority for off-screen or visible parents.

        Results are cached per event-loop tick to avoid redundant
        ``visualRect()`` calls when the same ``(node, page)`` pair is
        evaluated multiple times (e.g. by ``canFetchMore``,
        ``fetchMore``, and ``_dispatch_batch``).

        Args:
            node: The parent :class:`_TableNode` whose children are
                being fetched.
            page: Zero-based page number being requested.

        Returns:
            ``20`` when the parent row is not visible in the viewport;
            ``0`` for the first page of a visible parent; ``1`` for
            subsequent pages of a visible parent.
        """
        cache_key = (id(node), page)
        if cache_key in self._priority_cache:
            return self._priority_cache[cache_key]

        parent_is_visible = self._is_parent_visible(node)
        priority = (
            self._OFF_SCREEN_PRIORITY
            if not parent_is_visible
            else (0 if page == 0 else 1)
        )
        self._priority_cache[cache_key] = priority

        if not self._priority_cache_clear_scheduled:
            self._priority_cache_clear_scheduled = True
            QtCore.QTimer.singleShot(0, self._clear_priority_cache)

        return priority

    def _clear_priority_cache(self) -> None:
        """Clear the per-tick priority cache.

        Scheduled via ``QTimer.singleShot(0)`` after the first cache
        write so it fires at the next event-loop iteration.
        """
        self._priority_cache.clear()
        self._priority_cache_clear_scheduled = False


class ProjectModel(QtGui.QStandardItemModel):
    """Model that lists all active AYON projects."""

    ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
    IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2

    def __init__(
        self, controller: ReviewController, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._style_data = get_ayon_style_data("QComboBox", "low")
        log.debug("Style data: %s", json.dumps(self._style_data))
        projects = controller.fetch_projects()

        fg_color = self._style_data.get("color", "#ee5555")
        bg_color = self._style_data.get("background-color", "#550000")
        log.debug("FG: %s, BG: %s", fg_color, bg_color)
        fgc = QtGui.QColor(fg_color)
        bgc = QtGui.QColor(bg_color)

        project_icon = {
            "type": "material-symbols",
            "name": "map",
            "color": fg_color,
        }

        for project in projects:
            if not project.get("active", True):
                continue
            item = QtGui.QStandardItem(project["name"])
            icon = get_qt_icon(project_icon)
            if icon:
                item.setIcon(icon)
            item.setData(
                QtGui.QBrush(fgc),
                QtCore.Qt.ItemDataRole.ForegroundRole,
            )
            item.setData(
                QtGui.QBrush(bgc),
                QtCore.Qt.ItemDataRole.BackgroundRole,
            )
            item.setData("map", self.IconNameRole)
            item.setData(project["name"], self.ShortTextRole)
            self.appendRow(item)


class ProjectSelector(AYComboBox):
    """Combo box that lets the user select an AYON project."""

    def __init__(
        self,
        controller: ReviewController,
        *args: Any,
        initial_project="",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            inverted=False,
            variant=AYComboBox.Variants.Low,
            **kwargs,
        )
        self.setModel(ProjectModel(controller, self))
        if initial_project:
            self.setCurrentText(initial_project)

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self.currentText()


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
            variant=AYContainer.Variants.Low,
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


class Customize(AYButtonMenu):
    """Customize button for the reviews widget."""

    show_empty_groups_changed = QtCore.Signal(bool)  # type: ignore
    card_size_changed = QtCore.Signal(int)  # type: ignore
    featured_version_order_changed = QtCore.Signal(list)  # type: ignore

    # Maps UI display labels to GraphQL featuredVersion order keys.
    _FEATURED_VERSION_LABEL_TO_KEY: dict[str, str] = {
        "Latest Done": "latestDone",
        "Latest": "latest",
        "Hero": "hero",
    }

    _CARD_WIDTH_MIN = 150
    _CARD_WIDTH_MAX = 300

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_card_width: int = 200,
    ) -> None:
        self._show_empty_groups: bool = False
        self._initial_card_width: int = max(
            self._CARD_WIDTH_MIN,
            min(self._CARD_WIDTH_MAX, initial_card_width),
        )
        super().__init__(
            "Customize",
            populate_callback=self._populate,
            parent=parent,
            icon="settings",
            variant=AYButton.Variants.Surface,
            icon_size=16,
        )
        self._stack = None

    def _populate(self, container: ButtonMenuDropdown) -> None:
        self._container = container
        container.setMinimumWidth(300)
        # get the layout of page 1
        layout = container.layout()
        if not isinstance(layout, AYVBoxLayout):
            log.warning(
                "Customize menu layout is not an AYVBoxLayout: %r", layout
            )
            return

        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        # featured version button
        self.featured_version_btn = AYPageButton(
            label="Featured Version", icon="layers", value="Latest Done"
        )
        layout.addWidget(self.featured_version_btn, stretch=1)

        # card size slider
        self.card_size_slider = AYSlider(
            label="Card size",
            variant=AYSlider.Variants.Low,
            value=self._initial_card_width,
            minimum=self._CARD_WIDTH_MIN,
            maximum=self._CARD_WIDTH_MAX,
            step=10,
        )
        layout.addWidget(self.card_size_slider, stretch=1)
        self.card_size_slider.value_changed.connect(self.card_size_changed)

        # show empty groups checkbox
        self.show_empty_grps_ui = AYCheckBox(
            "Show empty groups",
            checked=self._show_empty_groups,
            variant=AYCheckBox.Variants.Menu,
            parent=self,
        )
        self.show_empty_grps_ui.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.show_empty_grps_ui, stretch=0)
        self.show_empty_grps_ui.toggled.connect(self.show_empty_groups_changed)

        # page 2: featured version settings
        page_2 = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=15,
        )
        container.add_page(page_2)
        page2_nav_lyt = AYHBoxLayout(margin=0, spacing=10)
        page2_back_btn = AYButton(
            icon="arrow_back", variant=AYButton.Variants.Nav
        )
        page2_back_btn.clicked.connect(lambda: container.set_current_page(0))
        page2_nav_lyt.addWidget(page2_back_btn)
        page2_nav_lyt.addWidget(
            AYLabel("Featured Version", variant=AYLabel.Variants.Default)
        )
        page2_nav_lyt.addStretch(1)
        page2_exit_btn = AYButton(icon="close", variant=AYButton.Variants.Nav)
        page2_exit_btn.clicked.connect(self._container.close)
        page2_nav_lyt.addWidget(page2_exit_btn)
        page_2.layout().addLayout(page2_nav_lyt)

        # open page 2 when the button is clicked
        self.featured_version_btn.clicked.connect(
            lambda: container.set_current_page(1)
        )

        self_featured_order = AYOrder(
            ["Latest Done", "Latest", "Hero"],
            variant=AYOrder.Variants.Low,
        )
        self_featured_order.order_changed.connect(
            self.on_featured_version_changed
        )

        page_2.layout().addWidget(self_featured_order)

        self._container.popup_closed.connect(self._on_container_closed)

    def _on_container_closed(self) -> None:
        if self._container:
            self._container.close()  # close() is idempotent
            self._container.set_current_page(0)

    def on_featured_version_changed(self, order: list) -> None:
        """Convert UI labels to GraphQL keys and notify listeners.

        Args:
            order: Ordered list of display labels as returned by the
                :class:`AYOrder` widget (e.g.
                ``["Latest Done", "Latest", "Hero"]``).
        """
        gql_order = [
            self._FEATURED_VERSION_LABEL_TO_KEY.get(label, label)
            for label in order
        ]
        self.featured_version_order_changed.emit(gql_order)

    def set_show_empty_groups(self, enabled: bool) -> None:
        """Update checkbox state without re-emitting change signal."""
        self._show_empty_groups = enabled
        if not hasattr(self, "show_empty_grps_ui"):
            return
        self.show_empty_grps_ui.blockSignals(True)
        self.show_empty_grps_ui.setChecked(enabled)
        self.show_empty_grps_ui.blockSignals(False)

    def set_card_width(self, width: int) -> None:
        """Update slider value without re-emitting change signal."""
        self._initial_card_width = max(
            self._CARD_WIDTH_MIN, min(self._CARD_WIDTH_MAX, width)
        )
        if not hasattr(self, "card_size_slider"):
            return
        self.card_size_slider.blockSignals(True)
        self.card_size_slider.setValue(self._initial_card_width)
        self.card_size_slider.blockSignals(False)


class DisplayType(AYContainer):
    """Widget that lets the user choose between different display types."""

    display_type_changed = QtCore.Signal(str)  # type: ignore

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_display_type: str = "list",
    ) -> None:
        super().__init__(
            parent=parent,
            variant=AYContainer.Variants.Surface,
            layout_margin=1,
            layout_spacing=1,
        )
        self._display_type = initial_display_type
        self._display_type_changed = False
        self._build()

    def _build(self) -> None:
        self._button_grp = QtWidgets.QButtonGroup(parent=self, exclusive=True)

        self._table_btn = AYButton(
            parent=self,
            icon="table_rows",
            variant=AYButton.Variants.Surface,
            icon_size=16,
            checkable=True,
        )
        self._table_btn.setObjectName("table")
        self._button_grp.addButton(self._table_btn)
        self.add_widget(self._table_btn, stretch=0)

        self._grid_btn = AYButton(
            parent=self,
            icon="grid_view",
            variant=AYButton.Variants.Surface,
            icon_size=16,
            checkable=True,
        )
        self._grid_btn.setObjectName("grid")
        self._button_grp.addButton(self._grid_btn)
        self.add_widget(self._grid_btn, stretch=0)

        self._button_grp.buttonClicked.connect(self._on_button_clicked)

        if self._display_type == "table":
            self._table_btn.setChecked(True)
        else:
            self._grid_btn.setChecked(True)

    @property
    def display_type(self) -> str:
        return self._display_type

    def _on_button_clicked(self, button: QtWidgets.QAbstractButton) -> None:
        self.display_type_changed.emit(button.objectName())
        self._display_type = button.objectName()


class GroupByMenu(AYFilter):
    group_by_changed = QtCore.Signal(str)  # type: ignore

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        options: list[GroupByOption] | None = None,
        default_key: str = "product",
    ) -> None:
        self._options_by_key: dict[str, GroupByOption] = {
            option.key: option for option in (options or [])
        }
        self._filters: dict[str, FilterItem] = {
            option.key: FilterItem(key=option.key, label=option.label)
            for option in self._options_by_key.values()
        }
        if default_key in self._filters:
            self._filters[default_key].selected = True
        elif "none" in self._filters:
            self._filters["none"].selected = True

        super().__init__(
            parent=parent,
            label="Group By  ",
        )
        self._sync_tags()

    def _create_dropdown_popup(self) -> AYDropdownPopup | None:
        self._dropdown = AYDropdownPopup(
            parent=self,
            variant=AYDropdownPopup.Variants.Low_Framed_Thin,
            translucent_bg=True,
        )
        lyt = AYVBoxLayout(self._dropdown, margin=2, spacing=0)
        self._filterable_list = FilterableList(
            placeholder="",
            parent=self._dropdown,
        )
        lyt.addWidget(self._filterable_list, stretch=10)
        search = self._filterable_list.search_field()
        search.textChanged.connect(self._on_search_changed)

        self._populate_list()

        return self._dropdown

    def _populate_list(self) -> None:
        self._filterable_list.clear_items()

        kw = {
            "variant": AYButton.Variants.Text,
            "checkable": True,
            "label_alignment": QtCore.Qt.AlignmentFlag.AlignLeft,
            "fixed_width": False,
        }

        self._menu_grp = QtWidgets.QButtonGroup(self._dropdown)
        self._menu_grp.setExclusive(True)
        self._menu_grp.buttonClicked.connect(self._on_dropdown_closed)

        for option in self._options_by_key.values():
            wdgt_name = f"grp_by_{option.key.replace(':', '_')}"
            w = AYButton(option.label, icon=option.icon, **kw)
            w.setProperty("group_by_key", option.key)
            setattr(self, wdgt_name, w)
            if self._filters[option.key].selected:
                w.setChecked(True)
            self._filterable_list.add_item(
                w,
                match_fn=lambda text, n=option.label: (
                    not text.lower().strip()
                    or text.lower().strip() in n.lower()
                ),
            )
            self._menu_grp.addButton(w)

        self._menu_grp.buttonClicked.connect(self._on_group_by_changed)

    def _on_dropdown_closed(self) -> None:
        """Close the dropdown and clear the search field so it's fresh
        next time."""
        self._dropdown.close()
        self._filterable_list.search_field().clear()

    def _on_search_changed(self, text: str) -> None:
        self._filterable_list.adjustSize()

    def _set_filter_state(self, key: str, selected: bool) -> None:
        if key not in self._filters:
            return
        self._filters[key].selected = selected

    def _sync_tags(self) -> None:
        self._sync_tags_from_items(list(self._filters.values()))
        if self._filters["none"].selected:
            self._remove_tag("none")

    def _on_group_by_changed(self, button: AYButton) -> None:
        grp_key = button.property("group_by_key")
        if not isinstance(grp_key, str):
            return
        log.debug("Group By: %s", grp_key)
        for k, v in self._filters.items():
            v.selected = k == grp_key
        self._sync_tags()
        self.group_by_changed.emit(grp_key)

    def _handle_tag_removed(self, key: str) -> None:
        """React to a tag dismissal.

        Called when the user clicks the X on a tag. Subclasses override
        this to update their data model (e.g. call
        ``set_filter_selected(key, False)``).

        Args:
            key: Key of the dismissed tag.
        """
        for v in self._filters.values():
            v.selected = False
        self._filters["none"].selected = True
        self._sync_tags()
        self.group_by_changed.emit("none")

    def set_options(
        self,
        options: list[GroupByOption],
        selected_key: str,
    ) -> None:
        """Replace group-by options and keep the current selection."""
        self._options_by_key = {option.key: option for option in options}
        self._filters = {
            option.key: FilterItem(
                key=option.key,
                label=option.label,
                selected=(option.key == selected_key),
            )
            for option in options
        }
        if selected_key not in self._filters and "none" in self._filters:
            self._filters["none"].selected = True
        self._sync_tags()
        self._populate_list()

    def get_selected_keys(self) -> list[str]:
        """Return the list of selected filter keys.

        Returns:
            List of selected keys.
        """
        return [v.key for v in self._filters.values() if v.selected]


class _ExpansionPhase(Enum):
    IDLE = "idle"
    VISIBLE = "visible"
    SPECULATIVE = "speculative"


class ReviewTable(AYContainer):
    """Right-hand panel that shows a paginated table of versions."""

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
        # Build a card data mapper that injects an async thumbnail fetcher
        # into every card so it can self-fetch on a cache miss without
        # relying on external orchestration.
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
        # set the initial sorting column to 1 (version name) ascending
        self._table.header().setSortIndicator(
            1, QtCore.Qt.SortOrder.AscendingOrder
        )

        # group by
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
        # display type
        self._display_type = DisplayType(self, initial_display_type="table")
        self._display_type.display_type_changed.connect(
            self._on_display_type_changed
        )
        # customize
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
        # "visible" -> "speculative" -> "idle" state machine.
        # See _on_loading_changed and _expand_deferred_batch.
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

    @property
    def table(self) -> AYTableView:
        return self._table

    @property
    def card_view(self) -> AYCardView:
        return self._card_view

    @property
    def active_view(self) -> AYTableView | AYCardView:
        return self._views_stack.currentWidget()

    def _on_display_type_changed(self, display_type: str) -> None:
        log.debug("Display type changed: %s", display_type)
        if display_type == "grid":
            self._views_stack.setCurrentWidget(self._card_view)
        else:
            self._views_stack.setCurrentWidget(self._table)

        active = self._views_stack.currentWidget()
        if not shiboken.isValid(active.viewport()):
            return

        # 1. Force a repaint so LazyThumbnailWidget.paintEvent fires for
        #    rows that just became visible in the new view.
        active.viewport().update()

        # 2. Re-run setEditorData for persistent editors (card view) so
        #    AYEntityCard.async_file_cacher gets a chance to fire for any
        #    cards that were opened while the view was hidden.
        if active is self._card_view:
            self._card_view.refresh_visible_editors()

        # 3. Kick the eager thumbnail pre-fetch for the table view.
        #    Card-view thumbnails are self-fetching via async_file_cacher.
        if active is self._table:
            self._eagerly_enqueue_visible_thumbnails()

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
        self._auto_expand = False
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys.clear()
        self._model.reset_data()

    def _on_show_empty_groups_changed(self, show_empty: bool) -> None:
        self._controller.set_hide_empty_groups(not show_empty)
        self._auto_expand = False
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys.clear()
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
            self._auto_expand = False
            self._deferred_expand_queue.clear()
            self._expansion_phase = _ExpansionPhase.IDLE
            self._enqueued_thumb_keys.clear()
            self._model.reset_data()

    def _on_page_fetched(self, page: int, total_pages: int) -> None:
        """Repaint the viewport and eagerly pre-fetch visible thumbnails.

        After repainting, iterate over all rows visible in the table
        viewport and enqueue thumbnail fetch tasks (at priority 2) for
        those that have not yet been requested.  The fetched image is
        stored in ``ImageCache``; when
        ``LazyThumbnailWidget.paintEvent`` accesses the cache it finds
        a hit and renders synchronously — eliminating the usual
        2-paint-cycle delay for initially visible rows.

        Card-view thumbnails are handled by each card's own
        ``async_file_cacher`` (set via the card data mapper) so no
        extra orchestration is needed here for the card view.
        """
        active = self._views_stack.currentWidget()
        if not shiboken.isValid(active.viewport()):
            return
        active.viewport().update()
        if active is self._table:
            self._eagerly_enqueue_visible_thumbnails()

    def _table_row_height(self) -> int:
        first_row_index = self._table.indexAt(QtCore.QPoint(0, 0))
        return (
            self._table.rowHeight(first_row_index)
            if self._table.children()
            else 32
        )

    def _iter_visible_proxy_indices(self) -> Iterator[QtCore.QModelIndex]:
        """Yield unique proxy indices that intersect the viewport.

        The walk uses ``indexAt`` by vertical pixel position so nested
        tree rows are included. Duplicate indices are suppressed to avoid
        repeated work when row heights are small.
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

        Iterates visible indices via :meth:`_iter_visible_proxy_indices`
        so nested tree rows at any depth are visited.

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

    def set_auto_expand(self, enabled: bool) -> None:
        """Enable or disable automatic expansion of folder rows.

        When *enabled*, every folder row inserted into the model is
        immediately expanded so that its children are fetched and
        displayed.  Cascades recursively until version-leaf rows
        (which have no children) are reached.

        Disabling also discards any pending deferred-expansion work so
        that stale rows from the previous selection are never expanded.

        Args:
            enabled: ``True`` to auto-expand, ``False`` to disable.
        """
        self._auto_expand = enabled
        if enabled:
            self._expansion_phase = _ExpansionPhase.VISIBLE
        else:
            self._deferred_expand_queue.clear()
            self._expansion_phase = _ExpansionPhase.IDLE

    def _on_rows_inserted_expand(
        self,
        parent: QtCore.QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Expand newly inserted folder rows when auto-expand is active.

        Connected to ``PaginatedTableModel.rowsInserted``.  Expansion is
        split into two phases:

        1. **Visible phase** — rows whose proxy rect intersects the
           viewport are expanded straight away (high-priority fetches at
           priority 0/1).  ``_expansion_phase`` remains ``"visible"``
           until ``loading_changed(False)`` fires.
        2. **Speculative phase** — off-screen rows are collected into
           ``_deferred_expand_queue`` and expanded in batches of 20 via
           recurring ``QTimer.singleShot(0)`` calls once the visible
           phase completes.  These use priority 20 (background).

        No row is ever skipped — GroupBy mode and Hierarchy mode are
        treated identically here.  The ``_on_loading_changed`` handler
        drives the phase transition.

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
                # Visible row — expand immediately (priority 0/1 fetch).
                self._table.expand(proxy_idx)
            else:
                # Off-screen — collect for speculative Phase 2.
                # QPersistentModelIndex survives sibling insertions
                # that would shift a plain integer row number.
                self._deferred_expand_queue.append(
                    QtCore.QPersistentModelIndex(src_idx)
                )

    def _on_loading_changed(self, is_loading: bool) -> None:
        """Transition to speculative phase when visible loads finish.

        Connected to ``PaginatedTableModel.loading_changed`` with a
        ``QueuedConnection`` to avoid re-entrant issues when the signal
        fires during ``endInsertRows()`` processing.

        When ``is_loading`` transitions to ``False`` during the
        ``"visible"`` phase and there are deferred rows waiting, the
        phase advances to ``"speculative"`` and the first batch of
        off-screen expansions is scheduled.

        Args:
            is_loading: ``True`` while fetch tasks are pending,
                ``False`` when all pending tasks have completed.
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
            # Async results from earlier speculative batches may have
            # added new expandable rows to the queue after the batch
            # chain stopped.  Re-kick the batch processor.
            if self._deferred_expand_queue:
                QtCore.QTimer.singleShot(0, self._expand_deferred_batch)
            else:
                self._expansion_phase = _ExpansionPhase.IDLE

    def _expand_deferred_batch(self) -> None:
        """Expand the next chunk of off-screen deferred rows.

        Pops up to 20 items from ``_deferred_expand_queue`` and expands
        them.  If more rows remain, re-schedules itself via
        ``QTimer.singleShot(0)`` so that at least one paint event can
        fire between batches, keeping the UI responsive.

        Only runs during the ``"speculative"`` phase; exits immediately
        otherwise.
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
        # When the queue empties here the phase stays "speculative".
        # _on_loading_changed will re-kick the chain if async results
        # from these expansions add new items, or transition to IDLE
        # once all in-flight fetches complete.

    def _on_scroll_catch_up(self) -> None:
        """Expand visible unexpanded groups the user scrolled to.

        Connected to the vertical scrollbar's ``valueChanged`` signal.
        Speculative Phase 2 expansion is **not** interrupted — it runs
        to completion in the background.  This handler is a pure
        catch-up mechanism: if the user scrolls to a group that Phase 2
        hasn't expanded yet, the group is expanded immediately so the
        user never sees a collapsed row.

        The actual expansion is debounced via a 100 ms single-shot timer
        so that rapid scroll events are coalesced into a single pass.
        """
        if not self._auto_expand:
            return

        if self._scroll_catch_up_timer is None:
            self._scroll_catch_up_timer = QtCore.QTimer(self)
            self._scroll_catch_up_timer.setSingleShot(True)
            self._scroll_catch_up_timer.setInterval(100)  # 100 ms
            self._scroll_catch_up_timer.timeout.connect(
                self._expand_visible_unexpanded
            )
        self._scroll_catch_up_timer.start()  # (re)start on each event

    def _expand_visible_unexpanded(self) -> None:
        """Expand any collapsed expandable rows currently in the viewport.

        Iterates visible indices via :meth:`_iter_visible_proxy_indices`
        so nested tree rows are found correctly at any depth.

        Acts as a catch-up for rows that speculative Phase 2 hasn't
        reached yet.  Does **not** cancel speculative work — Phase 2
        continues expanding the remaining off-screen rows in the
        background.
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

            Constructing a :class:`PlaceholderThumbnail` is near-free (~a
            single QWidget + setFixedSize).  The real
            :class:`LazyThumbnailWidget` is only created when the row
            scrolls into view (first ``paintEvent``), deferring both the
            expensive widget construction and the async network fetch.

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
                    # No thumbnail available
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
                "status", "Status", width=_w("Status", 120), icon="circle"
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
                "version", "Version", width=_w("Version"), icon="history"
            ),
            TableColumn(
                "productName",
                "Product Name",
                width=_w("Product Name", 150),
                icon="inventory_2",
            ),
            TableColumn(
                "taskType", "Task Type", width=_w("Task Type"), icon="task_alt"
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
                "taskType", "Task Type", width=_w("Task Type"), icon="task_alt"
            ),
            TableColumn(
                "entityType",
                "Entity Type",
                width=_w("Entity Type"),
                icon="layers",
            ),
            TableColumn("author", "Author", width=_w("Author"), icon="person"),
            TableColumn(
                "version", "Version", width=_w("Version"), icon="history"
            ),
            TableColumn(
                "productName",
                "Product Name",
                width=_w("Product Name", 150),
                icon="inventory_2",
            ),
        ]

        cols = (
            common + hierarchy + attributes
            if category == ReviewCategory.HIERARCHY.value
            else common + review_sessions + attributes
        )

        return cols

    def on_category_changed(self, category: str) -> None:
        """Reset the table when the slicer category changes."""
        self._auto_expand = False
        self._deferred_expand_queue.clear()
        self._expansion_phase = _ExpansionPhase.IDLE
        self._enqueued_thumb_keys.clear()
        self._model.reset_data()
        self._model.set_columns(self._build_columns(category))
        self._group_by_menu.setVisible(
            category == ReviewCategory.HIERARCHY.value
        )


class ReviewsWidget(AYContainer):
    """Top-level widget combining the slicer panel and version table."""

    def __init__(
        self,
        *args: Any,
        loader_controller: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            **kwargs,
        )
        prefs = UserPreferences()
        saved_project = prefs.get("loader.review.last_project", "")
        saved_category = prefs.get(
            "loader.review.last_category", ReviewCategory.HIERARCHY.value
        )

        self._controller = ReviewController(
            parent=self, loader_controller=loader_controller
        )
        self._slicer = ReviewSlicer(
            self._controller,
            self,
            initial_project=saved_project,
            initial_category=saved_category,
        )
        self._model = LazyTreeModel(
            fetch_children=self._controller.fetch_children
        )
        self._slicer.set_model(self._model)
        self._table = ReviewTable(self._controller, self)
        self._table.table.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.table.customContextMenuRequested.connect(
            self._on_context_menu
        )
        self._table.card_view.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._table.card_view.customContextMenuRequested.connect(
            self._on_context_menu
        )
        self._build()

        # Connect signals
        self._slicer._selector.currentTextChanged.connect(
            self._controller.set_project
        )
        self._controller.tree_reset_requested.connect(self._on_tree_reset)
        self._controller.project_changed.connect(self._on_project_changed)
        self._controller.selection_changed.connect(self._on_folder_selected)
        # Ensure the table updates when the category changes
        self._controller.category_changed.connect(
            self._table.on_category_changed
        )
        self._controller.project_info_changed.connect(
            self._table.on_project_info_changed
        )

        # Set initial project
        initial_project = self._slicer.current_project()
        if initial_project:
            self._controller.set_project(initial_project)
        initial_category = self._slicer.current_category()
        if initial_category:
            self._controller.set_category(initial_category)

    def _build(self) -> None:
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_splitter.addWidget(self._slicer)
        main_splitter.addWidget(self._table)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 6)
        self.add_widget(main_splitter)

    def _on_tree_reset(self) -> None:
        """Reset the tree model and re-attach it to the slicer."""
        self._model.reset()
        self._slicer.set_model(self._model)

    def _on_project_changed(self, project_name: str) -> None:
        """Clear selection state and refresh table on project change.

        Args:
            project_name: Newly selected project name.
        """
        self._table.set_auto_expand(False)
        self._table._model.reset_data()

    def _on_folder_selected(self, ids: list[str], names: list[str]) -> None:
        """Refresh the version table when folders are selected or cleared.

        In tree mode, selecting one or more folders makes those folders
        the root rows of the table and enables auto-expansion so that
        the full sub-tree is shown immediately.  Deselecting reverts to
        the collapsed root-folders view.

        Args:
            ids: IDs of the selected folders, or empty list when
                deselected.
            names: Names of the selected folders (parallel to *ids*).
        """
        auto_expand = bool(ids) and self._controller.tree_mode
        self._table.set_auto_expand(auto_expand)
        self._table._model.reset_data()
        # Re-apply active filter criteria to the freshly loaded data.
        self._table._table_filter.filter_model.refresh_filter()

    def _on_context_menu(self, pos: QtCore.QPoint) -> None:
        """Show a contextual actions menu for the selected rows.

        Collects the version IDs from the current table selection,
        queries the loader controller for applicable action items and
        presents them via :func:`show_actions_menu`.  Falls back to a
        plain refresh-only menu when no loader controller is available
        or no version rows are selected.
        """
        project_name = self._controller.current_project
        selection_model = self._table.active_view.selectionModel()

        version_ids: set[str] = set()
        for proxy_idx in selection_model.selectedIndexes():
            if proxy_idx.column() != 0:
                continue
            row_dict = proxy_idx.data(QtCore.Qt.ItemDataRole.UserRole) or {}
            entity_type = row_dict.get("entityType", "")
            if entity_type == "Folder":
                continue
            # headers store the featured version id in the _version_id key
            # rows store the version id in the id key
            version_id = row_dict.get("_version_id", row_dict.get("id", ""))
            if version_id:
                version_ids.add(version_id)

        global_point = self._table.active_view.viewport().mapToGlobal(pos)

        if not version_ids or not project_name:
            log.warning("No version ids or project name")
            return

        action_items = self._controller.get_action_items(
            project_name, version_ids, "version"
        )

        if not action_items:
            log.warning("No action items available")
            return

        result = show_actions_menu(
            action_items,
            global_point,
            len(version_ids) == 1,
            self,
        )
        action_item, options = result
        if action_item is None or options is None:
            return

        self._controller.trigger_action_item(
            identifier=action_item.identifier,
            project_name=project_name,
            selected_ids=version_ids,
            selected_entity_type="version",
            data=action_item.data,
            options=options,
            form_values={},
        )
