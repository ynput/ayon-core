"""Visual regression tests for AYCardView."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.card_view import AYCardView
from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.preview.table_model import (
    HIERARCHICAL_TEST_DATA,
    make_hierarchical_test_fetch,
)


def _make_card_mapper(row_data: dict) -> dict:
    """Convert row data to AYEntityCard keyword arguments."""
    status_dict = None
    if row_data.get("status"):
        status_dict = {
            "name": row_data["status"],
            "icon": row_data.get("status__icon", ""),
            "color": row_data.get("status__color", ""),
        }
    return {
        "header": row_data.get("name", ""),
        "title": row_data.get("type", ""),
        "title_icon": row_data.get("name__icon", ""),
        "image_icon": row_data.get("thumb__icon", "image"),
        "status": status_dict,
        "version": row_data.get("version", ""),
    }


_TREE_COLUMNS = [
    TableColumn(key="thumb", label="Thumbnail", width=90, sortable=False),
    TableColumn(
        key="name",
        label="Name",
        width=160,
        sortable=True,
        tree_position=True,
    ),
    TableColumn(key="status", label="Status", width=100, sortable=True),
    TableColumn(key="type", label="Type", width=100, sortable=True),
    TableColumn(key="version", label="Version", width=70, sortable=True),
]


def _make_fetch(rows: list[dict]):
    """Create a fetch_page function for the given rows."""

    def fetch_page(
        page_number: int,
        page_size: int,
        sort_key: str | None = None,
        descending: bool = False,
        parent_id: str | None = None,
    ) -> list[dict]:
        data = list(rows)
        if sort_key:
            data = sorted(
                data,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page_number * page_size
        end = start + page_size
        return data[start:end]

    return fetch_page


_FLAT_ROWS = [
    {
        "name": "hero_model_v003",
        "type": "Model",
        "status": "Approved",
        "status__icon": "task_alt",
        "status__color": "#00f0b4",
        "version": "v003",
        "thumb__icon": "image",
    },
    {
        "name": "hero_rig_v001",
        "type": "Rig",
        "status": "In progress",
        "status__icon": "play_arrow",
        "status__color": "#3498db",
        "version": "v001",
        "thumb__icon": "person",
    },
    {
        "name": "hero_lookdev_v002",
        "type": "Lookdev",
        "status": "Pending review",
        "status__icon": "visibility",
        "status__color": "#ff9b0a",
        "version": "v002",
        "thumb__icon": "palette",
    },
    {
        "name": "bg_arch_v005",
        "type": "Model",
        "status": "Approved",
        "status__icon": "task_alt",
        "status__color": "#00f0b4",
        "version": "v005",
        "thumb__icon": "architecture",
    },
    {
        "name": "camera_anim_v010",
        "type": "Animation",
        "status": "In progress",
        "status__icon": "play_arrow",
        "status__color": "#3498db",
        "version": "v010",
        "thumb__icon": "videocam",
    },
]


class CardViewFlatTest(WidgetTest):
    """Tests AYCardView in flat mode with card data."""

    size = (700, 400)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
            layout_spacing=0,
        )

        model = PaginatedTableModel(
            fetch_page=_make_fetch(_FLAT_ROWS),
            columns=_TREE_COLUMNS,
            page_size=50,
            no_async=True,
        )

        self._view = AYCardView(
            variant=AYCardView.Variants.Default,
            card_width=180,
            card_spacing=8,
            card_data_mapper=_make_card_mapper,
        )
        self._view.setModel(model)
        self._view.setMinimumHeight(320)
        self._model = model

        root.add_widget(self._view, stretch=1)
        return root

    def select_first_card(self) -> None:
        """Select the first card to show the active highlight."""
        idx = self._view.model().index(0, 0)
        self._view.setCurrentIndex(idx)

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events; data was loaded synchronously."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.select_first_card]


class CardViewTreeTest(WidgetTest):
    """Tests AYCardView in tree mode with hierarchical data and collapsible
    groups."""

    size = (700, 400)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
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

        self._view = AYCardView(
            variant=AYCardView.Variants.Default,
            card_width=180,
            card_spacing=8,
            card_data_mapper=_make_card_mapper,
        )
        self._view.setModel(model)
        self._view.setMinimumHeight(320)
        self._model = model

        root.add_widget(self._view, stretch=1)
        return root

    def collapse_first_group(self) -> None:
        """Collapse the first group to show collapsed header state."""
        # Get the node_id from the first group's parent index
        model = self._model
        idx = model.index(0, 0)
        node = idx.internalPointer()
        if node is not None:
            self._view._toggle_group(node.node_id)

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events; data was loaded synchronously."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.collapse_first_group]
