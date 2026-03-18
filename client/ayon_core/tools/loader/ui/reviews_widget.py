from __future__ import annotations

import json
import tempfile
from typing import Any, Callable

import ayon_api
from ayon_ui_qt import get_ayon_style_data
from ayon_ui_qt.components.buttons import AYButton  # noqa: F401
from ayon_ui_qt.components.check_box import AYCheckBox
from ayon_ui_qt.components.combo_box import AYComboBox
from ayon_ui_qt.components.container import AYContainer, AYHBoxLayout
from ayon_ui_qt.components.entity_thumbnail import AYEntityThumbnail
from ayon_ui_qt.components.label import AYLabel  # noqa: F401
from ayon_ui_qt.components.slicer import AYSlicer
from ayon_ui_qt.components.table_filter import AYTableFilter
from ayon_ui_qt.components.table_model import PaginatedTableModel, TableColumn
from ayon_ui_qt.components.table_view import AYTableView
from ayon_ui_qt.components.task_queue import AsyncTask, get_task_queue
from ayon_ui_qt.components.tree_model import LazyTreeModel
from ayon_ui_qt.components.tree_view import AYTreeView, QItemSelection
from ayon_ui_qt.image_cache import ImageCache
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.user_prefs import UserPreferences
from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


def _thumbnail_loader(key: str) -> str:
    """Fetch a version thumbnail from AYON and persist it to a temp file.

    Args:
        key: Cache key in the form:
          ``"<project_name>/<version_id>/<thumbnail_id>"``.

    Returns:
        Absolute path to the saved image file, or empty string when the
        version has no thumbnail (which will be caught by the factory).
    """
    log.debug("Fetching thumbnail for key %r", key)
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
        log.debug("Failed to fetch thumbnail for key %r", key, exc_info=True)
        return ""


class LazyThumbnailWidget(AYEntityThumbnail):
    """Thumbnail widget that defers loading until the first paint event.

    Persistent-editor widgets only receive ``paintEvent`` when they are
    within the viewport's visible area.  By deferring the async thumbnail
    fetch to the first paint, we avoid issuing network requests for
    off-screen rows.

    Args:
        key: ImageCache key in the form
            ``"<project>/<version_id>/<thumbnail_id>"``.
        context_id: Model request-ID used to scope the task-queue entry
            so stale tasks can be cancelled on model reset.
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
        super().__init__(size=size, parent=parent)
        self._thumb_key: str = key
        self._context_id: str = context_id
        self._load_requested: bool = False

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        """Enqueue the thumbnail fetch on the first paint, then paint.

        Args:
            event: The paint event forwarded to the parent class.
        """
        if not self._load_requested:
            self._load_requested = True
            w = self
            get_task_queue().enqueue(
                AsyncTask(
                    name=f"thumbnail_loader_{self._thumb_key}",
                    function=lambda: _thumbnail_loader(self._thumb_key),
                    callback=lambda fpath: w.set_thumbnail(fpath)
                    if shiboken.isValid(w)
                    else None,
                    priority=5,
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
            "text": "Hierarchy",
            "short_text": "HIE",
            "icon": "table_rows",
            "color": "#f4f5f5",
        },
        {
            "text": "Reviews",
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
        initial_category: str = "Hierarchy",
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
        indexes = selected.indexes()
        if indexes:
            index = indexes[0]
            data = index.data(QtCore.Qt.ItemDataRole.UserRole)
            if data:
                log.debug(json.dumps(data, indent=4))
                self._controller.on_tree_selection_changed(
                    data.get("id", ""), data.get("name", "")
                )
        elif deselected.indexes():
            # User clicked an already-selected item to deselect it;
            # clear the folder filter so all versions are shown.
            self._controller.on_tree_selection_changed("", "")

    def current_category(self) -> str:
        """Return the currently selected category name."""
        return self._slicer.current_category()

    def current_project(self) -> str:
        """Return the currently selected project name."""
        return self._selector.current_project()


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
        self._model = PaginatedTableModel(
            fetch_page=self._controller.fetch_versions_page,
            fetch_page_batch=self._controller.fetch_versions_page_batch,
            columns=self._build_columns(self._controller.current_category),
            page_size=250,
        )
        self._table_filter = AYTableFilter(model=self._model, parent=self)
        self._table.setModel(self._table_filter.filter_model)
        self._tree_toggle = AYCheckBox(
            "Show Hierarchy",
            variant=AYCheckBox.Variants.Button,
            parent=self,
        )
        self._tree_toggle.toggled.connect(self._on_tree_mode_toggle)

        toolbar_lyt = AYHBoxLayout(self, margin=0, spacing=4)
        toolbar_lyt.addWidget(self._table_filter, stretch=1)
        toolbar_lyt.addWidget(self._tree_toggle, stretch=0)
        self.add_layout(toolbar_lyt, stretch=0)
        self.add_widget(self._table)

        self._auto_expand: bool = False
        self._model.rowsInserted.connect(self._on_rows_inserted_expand)

    def on_project_info_changed(self) -> None:
        """Rebuild columns now that version attributes are available."""
        self._model.reset_data()
        self._model.set_columns(
            self._build_columns(self._controller.current_category)
        )

    def _on_tree_mode_toggle(self, enabled: bool) -> None:
        # Update the controller state first so that the fetch triggered
        # by model.set_tree_mode() sees the correct mode.
        self._controller.set_tree_mode(enabled)
        # Set auto-expand before the model reset so that the very first
        # batch of inserted rows is expanded immediately.
        has_selection = bool(self._controller.selected_folder_id)
        self._auto_expand = enabled and has_selection
        self._model.set_tree_mode(enabled)

    def set_auto_expand(self, enabled: bool) -> None:
        """Enable or disable automatic expansion of folder rows.

        When *enabled*, every folder row inserted into the model is
        immediately expanded so that its children are fetched and
        displayed.  Cascades recursively until version-leaf rows
        (which have no children) are reached.

        Args:
            enabled: ``True`` to auto-expand, ``False`` to disable.
        """
        self._auto_expand = enabled

    def _on_rows_inserted_expand(
        self,
        parent: QtCore.QModelIndex,
        first: int,
        last: int,
    ) -> None:
        """Expand newly inserted folder rows when auto-expand is active.

        Connected to ``PaginatedTableModel.rowsInserted``.  For each
        inserted row, if the source model reports that it can fetch
        more children (i.e. it is a folder node), the corresponding
        proxy index is expanded.  Expanding triggers Qt's
        ``fetchMore`` cycle, which inserts more rows, which fires this
        handler again — the recursion terminates naturally when version
        leaf rows (``canFetchMore == False``) are reached.

        Args:
            parent: Source model parent index of the inserted rows.
            first: First inserted row (0-based).
            last: Last inserted row (0-based, inclusive).
        """
        if not self._auto_expand:
            return
        for row in range(first, last + 1):
            src_idx = self._model.index(row, 0, parent)
            if self._model.canFetchMore(src_idx):
                proxy_idx = self._table_filter.filter_model.mapFromSource(
                    src_idx
                )
                if proxy_idx.isValid():
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
            version_id = row_dict.get("id", "")
            project = controller.current_project
            request_id = self._model._request_id

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
            if category == "Hierarchy"
            else common + review_sessions + attributes
        )

        return cols

    def on_category_changed(self, category: str) -> None:
        """Reset the table when the slicer category changes."""
        is_hierarchy = category == "Hierarchy"
        self._tree_toggle.setEnabled(is_hierarchy)
        if not is_hierarchy and self._tree_toggle.isChecked():
            # Suppress tree mode when leaving Hierarchy; block signals to
            # avoid a redundant reset_data from the toggle signal.
            self._tree_toggle.blockSignals(True)
            self._tree_toggle.setChecked(False)
            self._tree_toggle.blockSignals(False)
            self._controller.set_tree_mode(False)
            self._model.set_tree_mode(False)
        self._auto_expand = False
        self._model.reset_data()
        self._model.set_columns(self._build_columns(category))


class ReviewsWidget(AYContainer):
    """Top-level widget combining the slicer panel and version table."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            **kwargs,
        )
        prefs = UserPreferences()
        saved_project = prefs.get("loader.review.last_project", "")
        saved_category = prefs.get("loader.review.last_category", "Hierarchy")

        self._controller = ReviewController(parent=self)
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
        self._selected_folder_id: str = ""
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
        # auto-expand on mode toggle is handled inside ReviewTable

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
        self._selected_folder_id = ""
        self._table.set_auto_expand(False)
        self._table._model.reset_data()

    def _on_folder_selected(self, id: str, name: str) -> None:
        """Refresh the version table when a folder is selected or cleared.

        In tree mode, selecting a folder makes that folder the single
        root row of the table and enables auto-expansion so that the
        full sub-tree is shown immediately.  Deselecting reverts to the
        collapsed root-folders view.

        Args:
            id: ID of the selected folder, or empty string when
                deselected.
            name: Name of the selected folder.
        """
        self._selected_folder_id = id
        auto_expand = bool(id) and self._controller.tree_mode
        self._table.set_auto_expand(auto_expand)
        self._table._model.reset_data()
        # Re-apply active filter criteria to the freshly loaded data.
        self._table._table_filter.filter_model.refresh_filter()
