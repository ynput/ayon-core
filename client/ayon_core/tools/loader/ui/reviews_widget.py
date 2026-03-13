from __future__ import annotations

import json
import logging
from typing import Any

from ayon_ui_qt import get_ayon_style_data
from ayon_ui_qt.components.buttons import AYButton  # noqa: F401
from ayon_ui_qt.components.combo_box import AYComboBox
from ayon_ui_qt.components.container import AYContainer, AYHBoxLayout
from ayon_ui_qt.components.label import AYLabel  # noqa: F401
from ayon_ui_qt.components.check_box import AYCheckBox
from ayon_ui_qt.components.slicer import AYSlicer
from ayon_ui_qt.components.table_filter import AYTableFilter
from ayon_ui_qt.components.table_model import PaginatedTableModel, TableColumn
from ayon_ui_qt.components.table_view import AYTableView
from ayon_ui_qt.components.tree_model import LazyTreeModel
from ayon_ui_qt.components.tree_view import AYTreeView, QItemSelection
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.tools.loader.ui.review_controller import ReviewController
from ayon_core.tools.utils import get_qt_icon

log = logging.getLogger(__name__)


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
        self, controller: ReviewController, *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(
            *args,
            inverted=False,
            variant=AYComboBox.Variants.Low,
            **kwargs,
        )
        self.setModel(ProjectModel(controller, self))

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
        self._selector = ProjectSelector(controller)
        self.add_widget(self._selector, stretch=0)

        self._slicer = AYSlicer(item_list=self.CATEGORIES)
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

        common = [
            TableColumn(
                "thumb", "Thumbnail", width=_w("Thumbnail"), sortable=False
            ),
            TableColumn(
                "product/version",
                "Product/Version",
                width=_w("Product/Version", 200),
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
        self._controller = ReviewController(parent=self)
        self._slicer = ReviewSlicer(self._controller, self)
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
