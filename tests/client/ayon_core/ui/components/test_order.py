"""Visual regression and unit tests for AYOrder."""

from __future__ import annotations

import pytest
from qtpy.QtCore import QPoint
from qtpy.QtWidgets import QApplication, QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.order import AYOrder
from ayon_core.ui.components.container import AYContainer


_OPTIONS = ["Alpha", "Beta", "Gamma", "Delta"]
_ICONS = ["layers", "light_mode", "account_tree", "deployed_code"]


# ---------------------------------------------------------------------------
# Visual regression test
# ---------------------------------------------------------------------------


class OrderTest(WidgetTest):
    """Snapshot AYOrder in its default and High variants."""

    size = (400, 300)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
            layout_spacing=12,
        )

        self._order_default = AYOrder(
            options=_OPTIONS,
            variant=AYOrder.Variant.Default,
        )
        root.add_widget(self._order_default)

        self._order_high = AYOrder(
            options=["Compositing", "Lighting", "Rigging"],
            icons=["layers", "light_mode", "account_tree"],
            variant=AYOrder.Variant.High,
        )
        root.add_widget(self._order_high)

        return root

    def disable(self) -> None:
        """Disable both widgets."""
        self._order_default.setEnabled(False)
        self._order_high.setEnabled(False)

    def steps(self):
        return [self.disable]


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def order(qtbot) -> AYOrder:
    """Return an AYOrder with four named options."""
    w = AYOrder(options=list(_OPTIONS))
    qtbot.addWidget(w)
    w.show()
    return w


@pytest.fixture()
def order_with_icons(qtbot) -> AYOrder:
    """Return an AYOrder with four named options and custom icons."""
    w = AYOrder(options=list(_OPTIONS), icons=list(_ICONS))
    qtbot.addWidget(w)
    w.show()
    return w


class TestAYOrderConstruction:
    """Tests for constructor validation and initial state."""

    def test_initial_order(self, order: AYOrder) -> None:
        """current_order() returns the original option list."""
        assert order.current_order() == _OPTIONS

    def test_option_count(self, order: AYOrder) -> None:
        """The container holds exactly as many option widgets as options."""
        assert len(order._options) == len(_OPTIONS)

    def test_default_icon_is_drag_indicator(self, order: AYOrder) -> None:
        """Each option uses the drag_indicator icon by default."""
        for opt in order._options:
            assert opt._icon == "drag_indicator"

    def test_custom_icons(self, order_with_icons: AYOrder) -> None:
        """Custom icons are applied to each option in order."""
        for opt, expected_icon in zip(order_with_icons._options, _ICONS):
            assert opt._icon == expected_icon

    def test_icons_length_mismatch_raises(self, qtbot) -> None:
        """ValueError is raised when icons length != options length."""
        with pytest.raises(ValueError, match="icons length"):
            w = AYOrder(
                options=["A", "B", "C"],
                icons=["icon_a", "icon_b"],
            )
            qtbot.addWidget(w)

    def test_variant_propagates(self, qtbot) -> None:
        """The requested frame variant is stored on the widget."""
        w = AYOrder(
            options=["X"],
            variant=AYOrder.Variant.High,
        )
        qtbot.addWidget(w)
        assert w._variant_str == AYOrder.Variant.High.value

    def test_hand_cursor_on_options(self, order: AYOrder) -> None:
        """Each option widget shows the open-hand cursor."""
        from qtpy.QtCore import Qt as QtCore

        for opt in order._options:
            assert opt.cursor().shape() == QtCore.CursorShape.OpenHandCursor


class TestAYOrderReorder:
    """Tests for the internal _reorder method."""

    def test_reorder_moves_item_forward(self, order: AYOrder) -> None:
        """Moving the first item to position 3 shifts it correctly."""
        order._reorder(0, 3)
        assert order.current_order() == ["Beta", "Gamma", "Alpha", "Delta"]

    def test_reorder_moves_item_backward(self, order: AYOrder) -> None:
        """Moving the last item to position 0 shifts it correctly."""
        order._reorder(3, 0)
        assert order.current_order() == ["Delta", "Alpha", "Beta", "Gamma"]

    def test_reorder_same_position_is_noop(self, order: AYOrder) -> None:
        """Dropping an item on its own slot leaves the order unchanged."""
        original = order.current_order()
        order._reorder(1, 1)
        assert order.current_order() == original

    def test_reorder_adjacent_below_is_noop(self, order: AYOrder) -> None:
        """Dropping an item just below itself leaves the order unchanged."""
        original = order.current_order()
        order._reorder(1, 2)
        assert order.current_order() == original

    def test_reorder_emits_order_changed(self, order: AYOrder, qtbot) -> None:
        """order_changed is emitted with the updated order."""
        received: list[list[str]] = []
        order.order_changed.connect(received.append)
        order._reorder(0, 4)
        assert len(received) == 1
        assert received[0] == order.current_order()

    def test_reorder_noop_does_not_emit(self, order: AYOrder, qtbot) -> None:
        """order_changed is NOT emitted for a no-op reorder."""
        received: list[list[str]] = []
        order.order_changed.connect(received.append)
        order._reorder(2, 2)
        assert received == []

    def test_reorder_layout_count_unchanged(
        self, order: AYOrder, qtbot
    ) -> None:
        """The layout item count stays the same after a reorder.

        Widgets are temporarily detached during the slide animation and
        re-added once it completes (180 ms); allow enough headroom.
        """
        before = order._layout.count()
        order._reorder(0, 3)
        qtbot.wait(400)
        assert order._layout.count() == before


class TestAYOrderInsertionIndex:
    """Tests for _insertion_index geometry calculations."""

    def test_insertion_index_above_first(self, order: AYOrder) -> None:
        """A point above the first option yields index 0."""
        QApplication.processEvents()
        # Force layout to compute geometry
        order.resize(300, 200)
        QApplication.processEvents()

        first_top = order._options[0].geometry().top()
        idx = order._insertion_index(QPoint(10, max(0, first_top - 5)))
        assert idx == 0

    def test_insertion_index_below_last(self, order: AYOrder) -> None:
        """A point below the last option yields len(options)."""
        order.resize(300, 200)
        QApplication.processEvents()

        last_bottom = order._options[-1].geometry().bottom()
        idx = order._insertion_index(QPoint(10, last_bottom + 10))
        assert idx == len(_OPTIONS)
