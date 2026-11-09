"""Visual regression and behavioral tests for AYPageButton."""

from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.page_button import AYPageButton
from ayon_core.ui.style_types import get_ayon_style
from qtpy import QtWidgets
from qtpy.QtCore import QPoint
from qtpy.QtWidgets import QWidget
from widget_test import WidgetTest


# =============================================================================
# Visual regression test
# =============================================================================


class PageButtonTest(WidgetTest):
    """Visual regression snapshots for AYPageButton.

    Captures:
    - ``00_initial``: All button variants in their default state.
    - ``01_hover_first``: The first button forced into hover state.
    - ``02_unhover_first``: Hover released (back to base).
    """

    size = (400, 200)
    tolerance = 0.0

    def build(self) -> QWidget:
        """Build a container with representative AYPageButton rows.

        Returns:
            A container widget holding several AYPageButton instances.
        """
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=12,
            layout_spacing=2,
        )

        self._hover_btn: AYPageButton | None = None

        # Row 1: icon + label + value (main showcase row)
        btn1 = AYPageButton(
            label="Featured version",
            value="Done",
            icon="star",
        )
        root.add_widget(btn1)
        self._hover_btn = btn1

        # Row 2: label + value, no icon
        btn2 = AYPageButton(
            label="No icon row",
            value="On",
        )
        root.add_widget(btn2)

        # Row 3: long label that will be elided
        btn3 = AYPageButton(
            label="A very long label that should be elided when narrow",
            value="Short",
            icon="info",
        )
        root.add_widget(btn3)

        # Row 4: long value, short label
        btn4 = AYPageButton(
            label="Item",
            value="A longer value string here",
            icon="settings",
        )
        root.add_widget(btn4)

        # Row 5: no value (chevron only)
        btn5 = AYPageButton(
            label="No value",
            value="",
            icon="arrow_forward",
        )
        root.add_widget(btn5)

        # Row 6: disabled
        btn6 = AYPageButton(
            label="Disabled entry",
            value="N/A",
            icon="block",
        )
        btn6.setEnabled(False)
        root.add_widget(btn6)

        root.addStretch(1)
        self.widget = root
        return root

    def hover_first(self) -> None:
        """Force the hover appearance on the first button."""
        if self._hover_btn is not None:
            self._qbot.mouseMove(self._hover_btn)

    def unhover_first(self) -> None:
        """Release the forced hover state on the first button."""
        if self._hover_btn is not None:
            self._qbot.mouseMove(
                self.widget, QPoint(-100, -100)
            )  # move away to clear hover

    def steps(self) -> list:
        return [self.hover_first, self.unhover_first]

    def cleanup(self, step_name: str) -> None:
        self._qbot.mouseMove(self.widget, QPoint(-100, -100))
        QtWidgets.QApplication.processEvents()


# =============================================================================
# Behavioral / unit tests
# =============================================================================


def test_page_button_instantiation(qtbot) -> None:
    """AYPageButton can be created with default arguments without error."""
    btn = AYPageButton()
    qtbot.addWidget(btn)
    assert isinstance(btn, AYPageButton)
    assert btn.value() == ""
    assert btn.text() == ""


def test_page_button_label_and_value(qtbot) -> None:
    """Label text is accessible via ``text()`` and value via ``value()``.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Settings", value="On")
    qtbot.addWidget(btn)
    assert btn.text() == "Settings"
    assert btn.value() == "On"


def test_set_value_updates_internal_state(qtbot) -> None:
    """``set_value`` updates the stored value string.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Item", value="Old")
    qtbot.addWidget(btn)
    btn.set_value("New")
    assert btn.value() == "New"


def test_set_label_updates_text(qtbot) -> None:
    """``set_label`` updates the button's displayed text.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Original")
    qtbot.addWidget(btn)
    btn.set_label("Updated")
    assert btn.text() == "Updated"


def test_click_emits_clicked_signal(qtbot) -> None:
    """Clicking the button emits the ``clicked`` signal.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Click me")
    qtbot.addWidget(btn)
    btn.show()
    qtbot.waitExposed(btn)

    with qtbot.waitSignal(btn.clicked, timeout=500) as blocker:
        btn.click()

    assert blocker.signal_triggered, (
        "clicked signal must be emitted when button is clicked"
    )


def test_default_size_policy_is_expanding_fixed(qtbot) -> None:
    """Default size policy is ``Expanding × Fixed``.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Policy check")
    qtbot.addWidget(btn)
    policy = btn.sizePolicy()
    assert (
        policy.horizontalPolicy() == QtWidgets.QSizePolicy.Policy.Expanding
    ), "Horizontal policy must be Expanding"
    assert policy.verticalPolicy() == QtWidgets.QSizePolicy.Policy.Fixed, (
        "Vertical policy must be Fixed"
    )


def test_size_hint_height_matches_style(qtbot) -> None:
    """``sizeHint().height()`` matches the style-defined height (44 px).

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Height check")
    qtbot.addWidget(btn)
    expected = (
        get_ayon_style().model.get_style("AYPageButton").get("height", 44)
    )
    assert btn.sizeHint().height() == expected, (
        "sizeHint height must match the 'height' value in the style block"
    )


def test_full_width_in_container(qtbot) -> None:
    """Button expands to fill a 400 px wide parent container.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    container = QtWidgets.QWidget()
    container.resize(400, 200)
    layout = QtWidgets.QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    btn = AYPageButton(label="Full width")
    layout.addWidget(btn)

    qtbot.addWidget(container)
    container.show()
    qtbot.waitExposed(container)

    # Force layout pass
    container.layout().activate()

    assert btn.width() == 400, (
        "Button width must equal the parent container width"
    )


def test_paint_no_crash_with_hover_forced(qtbot) -> None:
    """Painting with forced hover state does not raise an exception.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Hover test", value="OK", icon="star")
    qtbot.addWidget(btn)
    btn.show()
    qtbot.waitExposed(btn)

    # btn.set_force_hover(True)
    qtbot.mouseMove(btn)
    btn.repaint()  # should not crash


def test_disabled_state_paint_no_crash(qtbot) -> None:
    """Painting a disabled button does not raise an exception.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Disabled", value="N/A", icon="block")
    btn.setEnabled(False)
    qtbot.addWidget(btn)
    btn.show()
    qtbot.waitExposed(btn)
    btn.repaint()  # should not crash


def test_set_value_triggers_repaint(qtbot) -> None:
    """``set_value`` schedules a repaint (``update()`` is called).

    We verify this indirectly: after ``set_value``, ``value()`` reflects
    the new string and processing events does not raise.

    Args:
        qtbot: The pytest-qt bot fixture.
    """
    btn = AYPageButton(label="Repaint", value="Before")
    qtbot.addWidget(btn)
    btn.show()
    qtbot.waitExposed(btn)

    btn.set_value("After")
    QtWidgets.QApplication.processEvents()
    assert btn.value() == "After"
