"""Layout tests for the view selector's dropdown."""

from ayon_core.ui.components.table_filter import AYTableFilter
from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    TableColumn,
)
from ayon_core.ui.components.table_view import AYTableView
from ayon_core.ui.components.views.data_models import View, Visibility
from ayon_core.ui.components.views.view_bindings import ViewBindings
from ayon_core.ui.components.views.view_manager import InMemoryViewManager
from ayon_core.ui.components.views.view_selector import AYViewSelector


VIEW_TYPE = "versions"
USER = "me"


def _make_selector(views: list[View]) -> AYViewSelector:
    model = PaginatedTableModel(
        fetch_page=lambda *args, **kwargs: [],
        columns=[TableColumn("name", "Name")],
        page_size=50,
    )
    filter_bar = AYTableFilter(model=model)
    table = AYTableView()
    table.setModel(filter_bar.filter_model)
    selector = AYViewSelector(
        bindings=ViewBindings(
            model=model, table_view=table, filter_bar=filter_bar
        ),
        manager=InMemoryViewManager(views=views),
        view_type=VIEW_TYPE,
        current_user=USER,
        allow_studio_scope=False,
    )
    selector._views = views
    return selector


def test_views_list_is_not_clipped_by_its_scrollbar(qapp):
    views = [
        View(
            label=f"View {idx}",
            view_type=VIEW_TYPE,
            owner=USER,
            visibility=Visibility.PRIVATE,
        )
        for idx in range(20)
    ]
    views.append(
        View(
            label="A view with a label longer than any other one" * 2,
            view_type=VIEW_TYPE,
            owner=USER,
            visibility=Visibility.PRIVATE,
        )
    )
    selector = _make_selector(views)

    scroll_area = selector._make_views_list_scroll_area()
    scroll_area.adjustSize()
    scroll_area.show()
    qapp.processEvents()

    assert scroll_area.verticalScrollBar().isVisible()
    content_width = scroll_area.widget().minimumSizeHint().width()
    assert scroll_area.viewport().width() >= content_width
