"""Visual regression tests for AYTableFilter."""

from __future__ import annotations

from qtpy import QtCore, QtGui
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPainter
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.table_filter import (
    AYTableFilter,
    FilterCriterion,
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.container import AYContainer


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

_COLUMNS = [
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


# ---------------------------------------------------------------------------
# Composite widget to capture the floating dropdown in grab()
# ---------------------------------------------------------------------------


class _CompositeFilterWidget(QWidget):
    """A QWidget whose grab() composites the filter bar and its dropdown.

    When the filter dropdown is visible, the pixmap is assembled by
    stacking the main widget and the dropdown, similar to the approach
    used in test_buttons.py for AYButtonMenu.
    """

    def __init__(
        self,
        table_filter: AYTableFilter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._table_filter = table_filter

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(event.rect(), QColor("#272d35"))
        return super().paintEvent(event)

    def grab(  # type: ignore[override]
        self,
        rectangle: QtCore.QRect = QtCore.QRect(
            QtCore.QPoint(0, 0), QtCore.QSize(-1, -1)
        ),
    ) -> QtGui.QPixmap:
        """Return a pixmap composited with the open dropdown if visible."""
        base_pixmap = super().grab(rectangle)

        dropdown = self._table_filter._dropdown
        if dropdown is None or not dropdown.isVisible():
            return base_pixmap

        drop_pixmap = dropdown.grab()

        # Compute dropdown position relative to this widget
        drop_global = dropdown.mapToGlobal(QtCore.QPoint(0, 0))
        drop_local = self.mapFromGlobal(drop_global)

        total_height = max(
            base_pixmap.height(),
            drop_local.y() + drop_pixmap.height(),
        )
        total_width = max(
            base_pixmap.width(),
            drop_local.x() + drop_pixmap.width(),
        )
        canvas = QtGui.QPixmap(total_width, total_height)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(0, 0, base_pixmap)
        painter.drawPixmap(drop_local.x(), drop_local.y(), drop_pixmap)
        painter.end()

        return canvas


# ---------------------------------------------------------------------------
# Visual regression tests
# ---------------------------------------------------------------------------


class TableFilterTest(WidgetTest):
    """Tests AYTableFilter: empty state, with criteria badges, and
    dropdown open."""

    size = (500, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
            layout_spacing=8,
        )

        # Create model and filter bar
        model = PaginatedTableModel(
            fetch_page=_make_fetch(_ROWS),
            columns=_COLUMNS,
            page_size=50,
            no_async=True,
        )

        self._filter = AYTableFilter(model=model)

        # Wrap in composite widget for dropdown capture
        self._composite = _CompositeFilterWidget(self._filter)
        from qtpy.QtWidgets import QVBoxLayout

        comp_lyt = QVBoxLayout(self._composite)
        comp_lyt.setContentsMargins(0, 0, 0, 0)
        comp_lyt.setSpacing(0)
        comp_lyt.addWidget(self._filter)

        root.add_widget(self._composite)

        # Table below to show filtering effect
        self._table = AYTableView(variant=AYTableView.Variants.Default)
        self._table.setModel(self._filter.filter_model)
        self._table.setMinimumHeight(60)
        root.add_widget(self._table, stretch=1)

        return root

    def open_dropdown(self) -> None:
        """Open the attribute selection dropdown."""
        self._filter._dropdown.open_for_new(self._filter)

    def add_status_criterion(self) -> None:
        """Add a filter criterion for the Status column via API."""
        criterion = FilterCriterion(
            key="status",
            attribute_label="Status",
            values=["Approved"],
            use_substring=False,
        )
        self._filter._criteria.append(criterion)
        self._filter._rebuild_bar()
        self._filter._update_proxy()

    def add_multiple_criteria(self) -> None:
        """Add a second criterion to show 'and' separator."""
        criterion = FilterCriterion(
            key="task",
            attribute_label="Task",
            values=["Lookdev"],
            use_substring=False,
        )
        self._filter._criteria.append(criterion)
        self._filter._rebuild_bar()
        self._filter._update_proxy()

    def remove_first_criterion(self) -> None:
        """Remove the first criterion to leave only one."""
        self._filter._criteria = self._filter._criteria[1:]
        self._filter._rebuild_bar()
        self._filter._update_proxy()

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [
            self.open_dropdown,
            self.add_status_criterion,
            self.add_multiple_criteria,
            self.remove_first_criterion,
        ]
