"""Visual regression and behavioral tests for AYButton and AYButtonMenu."""

from __future__ import annotations

from ayon_core.ui.components.buttons import AYButton, AYButtonMenu
from ayon_core.ui.components.container import AYContainer
from qtpy import QtCore, QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QStyle, QStyleOptionButton, QWidget
from widget_test import WidgetTest

from utils.composite_widget import CompositeWidget


class _HoverButton(AYButton):
    """AYButton subclass that can force the hover appearance for snapshot tests."""

    def __init__(self, *args, **kwargs):
        self._force_hover: bool = (
            False  # must be set before super().__init__ calls setStyle
        )
        super().__init__(*args, **kwargs)

    def set_force_hover(self, value: bool) -> None:
        self._force_hover = value
        self.update()

    def initStyleOption(self, option: QStyleOptionButton) -> None:
        super().initStyleOption(option)
        if self._force_hover:
            option.state |= QStyle.StateFlag.State_MouseOver


class ButtonTest(WidgetTest):
    """Tests all AYButton variants: text-only, icon+text, icon-only, checkable."""

    size = (900, 400)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=12,
        )

        variants = list(AYButton.Variants)
        self._checkable_buttons: list[AYButton] = []
        self._row1_buttons: list[_HoverButton] = []

        # Row 1: text-only buttons (use _HoverButton so hover can be forced in steps)
        row1 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        for var in variants:
            btn = _HoverButton(var.value, variant=var)
            row1.add_widget(btn)
            self._row1_buttons.append(btn)
        row1.addStretch(1)
        root.add_widget(row1)

        # Row 2: icon + text buttons
        row2 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        for var in variants:
            btn = AYButton(var.value, variant=var, icon="add")
            row2.add_widget(btn)
        row2.addStretch(1)
        root.add_widget(row2)

        # Row 3: icon-only buttons
        row3 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        for var in variants:
            btn = AYButton(variant=var, icon="home")
            row3.add_widget(btn)
        row3.addStretch(1)
        root.add_widget(row3)

        # Row 4: checkable buttons (toggled in steps)
        row4 = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_margin=0,
            layout_spacing=8,
        )
        for var in variants:
            btn = AYButton(
                var.value,
                variant=var,
                icon="star",
                icon_on="star",
                checkable=True,
            )
            row4.add_widget(btn)
            self._checkable_buttons.append(btn)
        row4.addStretch(1)
        root.add_widget(row4)

        return root

    def check_all(self) -> None:
        for btn in self._checkable_buttons:
            btn.setChecked(True)

    def uncheck_all(self) -> None:
        for btn in self._checkable_buttons:
            btn.setChecked(False)

    def hover_row1(self) -> None:
        """Force the hover appearance on all text-only row-1 buttons."""
        for btn in self._row1_buttons:
            btn.set_force_hover(True)

    def unhover_row1(self) -> None:
        """Clear the forced hover state, restoring the normal appearance."""
        for btn in self._row1_buttons:
            btn.set_force_hover(False)

    def steps(self) -> list:
        return [
            self.check_all,
            self.uncheck_all,
            self.hover_row1,
            self.unhover_row1,
        ]


# =============================================================================
# AYButtonMenu — visual regression
# =============================================================================


class _CompositeMenuWidget(CompositeWidget):
    """A QWidget whose grab() composites the main container and its dropdown.

    This is a thin wrapper around `CompositeWidget` for backward compatibility.

    Args:
        dropdown: The ``_ButtonMenuDropdown`` managed by ``AYButtonMenu``.
        button: The ``AYButtonMenu`` button used to calculate the dropdown
            position relative to this composite widget.
    """

    def __init__(
        self,
        dropdown: QtWidgets.QFrame,
        button: AYButtonMenu,
        parent: QWidget | None = None,
    ) -> None:
        def dropdown_pos() -> QtCore.QPoint:
            btn_bottom_global = button.mapToGlobal(
                QtCore.QPoint(0, button.height())
            )
            return self.mapFromGlobal(btn_bottom_global)

        super().__init__(
            widgets=[(dropdown, dropdown_pos)],
            parent=parent,
        )


class ButtonMenuTest(WidgetTest):
    """Visual regression snapshots for AYButtonMenu.

    Two states are captured:
    - ``00_initial``:   Button in its closed (default) state.
    - ``01_open_menu``: Button + dropdown fully visible, showing "Item A".
    """

    size = (300, 80)
    tolerance = 0.0

    def build(self) -> QWidget:
        """Build a minimal AYButtonMenu widget for snapshot comparison."""

        def _populate(container: QtWidgets.QFrame) -> None:
            for ll in ["Item A", "Item B", "Item C"]:
                label = AYButton(
                    ll,
                    icon="star",
                    icon_color="white",
                    icon_size=16,
                    parent=container,
                    variant=AYButton.Variants.Text,
                )
                _layout = container.layout()
                assert _layout is not None
                _layout.addWidget(label)

        self._menu_btn = AYButtonMenu(
            "Options",
            populate_callback=_populate,
            icon="menu",
        )

        root = _CompositeMenuWidget(
            dropdown=self._menu_btn._dropdown,
            button=self._menu_btn,
        )
        root_layout = QtWidgets.QHBoxLayout(root)
        root_layout.setContentsMargins(20, 20, 20, 20)
        root_layout.setSpacing(8)
        root_layout.addWidget(self._menu_btn)
        root_layout.addStretch(1)
        return root

    def open_menu(self) -> None:
        """Open the dropdown so the snapshot includes it."""
        self._menu_btn._on_button_clicked()

    def steps(self) -> list:
        return [self.open_menu]


# =============================================================================
# AYButtonMenu — behavioral / unit tests (pytest-qt)
# =============================================================================


def _make_menu_button(
    qtbot,
    label: str = "Menu",
) -> tuple[AYButtonMenu, list[QtWidgets.QFrame]]:
    """Create an AYButtonMenu wired to a spy that records populate calls.

    Args:
        qtbot: The pytest-qt bot fixture.
        label: Button label text.

    Returns:
        A tuple of (button, list-of-containers-passed-to-populate).
    """
    containers: list[QtWidgets.QFrame] = []

    def _populate(container: QtWidgets.QFrame) -> None:
        containers.append(container)
        btn = QtWidgets.QPushButton("Option A", container)
        _layout = container.layout()
        assert _layout is not None
        _layout.addWidget(btn)

    btn = AYButtonMenu(label, populate_callback=_populate)
    qtbot.addWidget(btn)
    return btn, containers


def test_aybuttonmenu_instantiation(qtbot) -> None:
    """AYButtonMenu can be created and exposes the expected public API.

    Verifies that:
    - The widget is a subclass of AYButton.
    - It has ``menu_opened`` and ``menu_closed`` signals.
    - The ``populate_callback`` is called exactly once during construction.
    - The dropdown is initially hidden.
    """
    btn, containers = _make_menu_button(qtbot)

    assert isinstance(btn, AYButton), (
        "AYButtonMenu should be a subclass of AYButton"
    )
    assert hasattr(btn, "menu_opened"), (
        "AYButtonMenu must expose a menu_opened signal"
    )
    assert hasattr(btn, "menu_closed"), (
        "AYButtonMenu must expose a menu_closed signal"
    )
    assert len(containers) == 1, (
        "populate_callback must be called exactly once during __init__"
    )
    # Dropdown should be created but not yet visible
    assert not btn._dropdown.isVisible(), (
        "Dropdown must be hidden immediately after construction"
    )


def test_aybuttonmenu_dropdown_opens_on_click(qtbot) -> None:
    """Clicking AYButtonMenu shows the dropdown and emits menu_opened.

    Verifies that after a simulated click:
    - The internal ``_menu_open`` flag is True.
    - The ``menu_opened`` signal is emitted exactly once.
    """
    btn, _ = _make_menu_button(qtbot)
    btn.show()
    qtbot.waitExposed(btn)

    with qtbot.waitSignal(btn.menu_opened, timeout=500) as blocker:
        btn.click()

    assert blocker.signal_triggered, (
        "menu_opened signal must be emitted when dropdown opens"
    )
    assert btn._menu_open is True, "_menu_open flag must be True after opening"


def test_aybuttonmenu_populate_callback_widgets_in_dropdown(qtbot) -> None:
    """Widgets added by populate_callback appear in the dropdown layout.

    Verifies that:
    - The dropdown's layout contains the widget added by the callback.
    - That widget is a QPushButton with the expected text.
    """
    btn, containers = _make_menu_button(qtbot)

    dropdown = btn._dropdown
    layout = dropdown.layout()
    assert layout is not None, "Dropdown must have a layout"

    # Collect all QPushButton children from the dropdown
    child_buttons = dropdown.findChildren(QtWidgets.QPushButton)
    assert len(child_buttons) == 1, (
        "Dropdown must contain exactly one QPushButton (added by populate_callback)"
    )
    assert child_buttons[0].text() == "Option A", (
        "The QPushButton text must match what the populate_callback set"
    )


def test_aybuttonmenu_toggle_closes_dropdown(qtbot) -> None:
    """Clicking AYButtonMenu twice closes the dropdown.

    Verifies that a second click while the menu is open:
    - Sets ``_menu_open`` to False.
    - Emits ``menu_closed`` exactly once.
    """
    btn, _ = _make_menu_button(qtbot)
    btn.show()
    qtbot.waitExposed(btn)

    # Open the dropdown first
    with qtbot.waitSignal(btn.menu_opened, timeout=500):
        btn.click()

    assert btn._menu_open is True, "_menu_open must be True after first click"

    # A second click should close the dropdown
    with qtbot.waitSignal(btn.menu_closed, timeout=500) as blocker:
        btn.click()

    assert blocker.signal_triggered, (
        "menu_closed signal must fire when clicking the button again"
    )
    assert btn._menu_open is False, (
        "_menu_open must be False after second (closing) click"
    )


def test_aybuttonmenu_escape_closes_dropdown(qtbot) -> None:
    """Pressing Escape while the dropdown is open closes it.

    Verifies that after the dropdown is shown:
    - A Key_Escape keypress closes the popup.
    - ``menu_closed`` is emitted.
    - ``_menu_open`` is reset to False.
    """
    btn, _ = _make_menu_button(qtbot)
    btn.show()
    qtbot.waitExposed(btn)

    # Open the dropdown
    with qtbot.waitSignal(btn.menu_opened, timeout=500):
        btn.click()

    dropdown = btn._dropdown

    # Send Escape to the dropdown to close it
    with qtbot.waitSignal(btn.menu_closed, timeout=500) as blocker:
        qtbot.keyPress(dropdown, Qt.Key.Key_Escape)

    assert blocker.signal_triggered, (
        "menu_closed must be emitted after pressing Escape"
    )
    assert btn._menu_open is False, (
        "_menu_open must be False after Escape closes the dropdown"
    )


def test_aybuttonmenu_menu_closed_signal_emitted(qtbot) -> None:
    """menu_closed signal is emitted when the dropdown closes.

    This test uses a signal spy to confirm the signal fires exactly once
    per open/close cycle and carries no unexpected payload.
    """
    btn, _ = _make_menu_button(qtbot)
    btn.show()
    qtbot.waitExposed(btn)

    closed_count: int = 0

    def _on_closed() -> None:
        nonlocal closed_count
        closed_count += 1

    btn.menu_closed.connect(_on_closed)

    # Open then close via second click
    with qtbot.waitSignal(btn.menu_opened, timeout=500):
        btn.click()

    with qtbot.waitSignal(btn.menu_closed, timeout=500):
        btn.click()

    assert closed_count == 1, (
        "menu_closed must be emitted exactly once for one open/close cycle"
    )
