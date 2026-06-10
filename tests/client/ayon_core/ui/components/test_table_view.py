"""Visual regression tests for AYTableView."""

from __future__ import annotations

from pathlib import Path

from qtpy.QtCore import QModelIndex
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.entity_thumbnail import AYEntityThumbnail
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
    HIERARCHICAL_TEST_DATA,
    make_hierarchical_test_fetch,
)
from ayon_core.ui.components.container import AYContainer


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------


def _thumbnail_file_cacher(key: str) -> Path | str:
    rsrc_dir = Path(__file__).parent.parent / "test_data"
    for ext in ("jpg", "png"):
        p = rsrc_dir / f"{key}.{ext}"
        if p.exists():
            return p
    return ""


def _thumbnail_factory(
    index: QModelIndex, parent: QWidget
) -> AYEntityThumbnail:
    return AYEntityThumbnail(
        src="SMPTE_Color_Bars",
        file_cacher=_thumbnail_file_cacher,
        size=(66, 32),
        parent=parent,
    )


_COLUMNS = [
    TableColumn(
        key="thumb",
        label="Thumbnail",
        width=90,
        sortable=False,
        widget_factory=_thumbnail_factory,
    ),
    TableColumn(key="name", label="Name", width=160, sortable=True),
    TableColumn(key="task", label="Task", width=120, sortable=True),
    TableColumn(key="status", label="Status", width=100, sortable=True),
    TableColumn(key="assignee", label="Assignee", width=120, sortable=False),
]

_ROWS = [
    {
        "name": "hero_model_v003",
        "task": "Modeling",
        "status": "Approved",
        "assignee": "Alice",
    },
    {
        "name": "hero_rig_v001",
        "task": "Rigging",
        "status": "In progress",
        "assignee": "Bob",
    },
    {
        "name": "hero_lookdev_v002",
        "task": "Lookdev",
        "status": "Pending review",
        "assignee": "Carol",
    },
    {
        "name": "bg_arch_v005",
        "task": "Modeling",
        "status": "Approved",
        "assignee": "Dave",
    },
    {
        "name": "bg_lookdev_v001",
        "task": "Lookdev",
        "status": "Not ready",
        "assignee": "Alice",
    },
    {
        "name": "camera_anim_v010",
        "task": "Animation",
        "status": "In progress",
        "assignee": "Eve",
    },
    {
        "name": "crowd_anim_v002",
        "task": "Animation",
        "status": "On hold",
        "assignee": "Bob",
    },
    {
        "name": "vfx_smoke_v004",
        "task": "FX",
        "status": "Approved",
        "assignee": "Frank",
    },
]


def _make_fetch(rows):
    def fetch_page(
        page_number,
        page_size,
        sort_key=None,
        descending=False,
        parent_id=None,  # noqa: ARG001
    ):
        start = page_number * page_size
        end = start + page_size
        return rows[start:end]

    return fetch_page


class TableViewTest(WidgetTest):
    """Tests AYTableView with paginated data and sorting."""

    size = (700, 320)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=0,
        )

        model = PaginatedTableModel(
            fetch_page=_make_fetch(_ROWS),
            columns=_COLUMNS,
            page_size=50,
            no_async=True,
        )
        self._view = AYTableView(variant=AYTableView.Variants.Default)
        self._view.setModel(model)
        model.setParent(self._view)
        self._model = model
        self._view.setMinimumHeight(240)

        root.add_widget(self._view, stretch=1)
        return root

    def select_first_row(self) -> None:
        """Select the first row to show the selection highlight."""
        idx = self._view.model().index(0, 0)
        self._view.setCurrentIndex(idx)

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events; data was loaded synchronously."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.select_first_row]


_TREE_COLUMNS = [
    TableColumn(
        key="thumb",
        label="Thumbnail",
        width=90,
        sortable=False,
        widget_factory=_thumbnail_factory,
    ),
    TableColumn(
        key="name", label="Name", width=160, sortable=True, tree_position=True
    ),
    TableColumn(key="status", label="Status", width=100, sortable=True),
    TableColumn(key="type", label="Type", width=100, sortable=True),
    TableColumn(key="author", label="Author", width=100, sortable=False),
    TableColumn(key="version", label="Version", width=70, sortable=True),
]


class TableViewTreeTest(WidgetTest):
    """Tests AYTableView in tree mode with hierarchical data."""

    size = (700, 360)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=0,
        )

        fetch = make_hierarchical_test_fetch(HIERARCHICAL_TEST_DATA)
        model = PaginatedTableModel(
            fetch_page=fetch,
            columns=_TREE_COLUMNS,
            page_size=50,
            no_async=True,
        )
        model.set_tree_mode(True)

        self._view = AYTableView(variant=AYTableView.Variants.Default)
        self._view.setModel(model)
        model.setParent(self._view)
        self._model = model
        self._view.setMinimumHeight(280)

        root.add_widget(self._view, stretch=1)
        return root

    def expand_assets(self) -> None:
        """Expand the first root folder (Assets)."""
        idx = self._model.index(0, 0)
        self._view.expand(idx)

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events; data was loaded synchronously."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.expand_assets]
