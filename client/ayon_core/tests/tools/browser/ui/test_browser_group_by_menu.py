"""Tests for the Browser's Group By menu."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.ui._browser_toolbar import GroupByMenu
from ayon_core.tools.browser.ui.browser_group_by import (
    BUILTIN_GROUPS,
    GroupByOption,
)


def _menu(qtbot, options=BUILTIN_GROUPS, key="product") -> GroupByMenu:
    menu = GroupByMenu(options=options, default_key=key)
    qtbot.addWidget(menu)
    return menu


def _listed_actions(qmenu) -> dict:
    """Return the listed option actions by key, including submenus."""
    actions = {}
    for action in qmenu.actions():
        if action.menu() is not None:
            if action.isVisible():
                actions.update(_listed_actions(action.menu()))
        elif action.isVisible() and action.property("group_by_key"):
            actions[action.property("group_by_key")] = action
    return actions


def _close(menu: GroupByMenu) -> None:
    if menu._menu is not None:
        menu._menu.close()
    # Closing right before reopening is what a click on the toggle
    # button does, which the menu ignores for a moment.
    menu._menu_hidden_at = 0.0


def _open(menu: GroupByMenu) -> dict:
    """Open the menu and return its listed option actions by key."""
    _close(menu)
    menu._on_toggle_dropdown()
    return _listed_actions(menu._menu)


def _checked_keys(menu: GroupByMenu) -> list[str]:
    checked = [
        key for key, action in _open(menu).items() if action.isChecked()
    ]
    _close(menu)
    return checked


def test_clicking_active_group_deselects_it(qtbot):
    menu = _menu(qtbot)
    changed = Mock()
    menu.group_by_changed.connect(changed)

    _open(menu)["product"].trigger()

    changed.assert_called_once_with("none")
    assert menu.get_selected_keys() == ["none"]
    assert _checked_keys(menu) == ["none"]


def test_clicking_other_group_selects_it(qtbot):
    menu = _menu(qtbot)
    changed = Mock()
    menu.group_by_changed.connect(changed)

    _open(menu)["status"].trigger()

    changed.assert_called_once_with("status")
    assert menu.get_selected_keys() == ["status"]
    assert _checked_keys(menu) == ["status"]


def test_removing_tag_clears_menu_check(qtbot):
    menu = _menu(qtbot)

    menu._handle_tag_removed("product")

    assert menu.get_selected_keys() == ["none"]
    assert _checked_keys(menu) == ["none"]


def test_set_options_lists_new_options_when_menu_opens(qtbot):
    menu = _menu(qtbot)
    options = [*BUILTIN_GROUPS, GroupByOption("attrib:fps", "FPS")]

    menu.set_options(options, "attrib:fps")
    menu._handle_tag_removed("attrib:fps")

    assert menu.get_selected_keys() == ["none"]
    assert list(_open(menu)) == [option.key for option in options]
    assert _checked_keys(menu) == ["none"]


def test_toggling_open_menu_closes_it(qtbot):
    menu = _menu(qtbot)
    _open(menu)
    opened = menu._menu

    menu._on_toggle_dropdown()

    assert not opened.isVisible()
    assert menu._menu is None
    assert menu._dropdown_visible is False


def test_set_options_closes_open_menu(qtbot):
    menu = _menu(qtbot)
    _open(menu)

    menu.set_options(BUILTIN_GROUPS[:2], "none")

    assert menu._menu is None
    assert list(_open(menu)) == ["none", "product"]
    _close(menu)


def test_grouped_options_are_listed_in_submenus(qtbot):
    options = [
        *BUILTIN_GROUPS,
        GroupByOption("attr:fps", "FPS", menu_group="Version"),
        GroupByOption(
            "product_attr:productGroup", "Product Group", menu_group="Product"
        ),
    ]
    menu = _menu(qtbot, options, "attr:fps")

    _open(menu)
    top_level = [
        action.menu().title() if action.menu() else action.text()
        for action in menu._menu.actions()
        if action.isVisible() and not action.isSeparator() and action.text()
    ]
    submenus = {
        action.menu().title(): [a.text() for a in action.menu().actions()]
        for action in menu._menu.actions()
        if action.menu()
    }

    assert top_level == [
        *(option.label for option in BUILTIN_GROUPS), "Version", "Product"
    ]
    assert submenus == {"Version": ["FPS"], "Product": ["Product Group"]}
    # The box shows the short label of the selected option.
    assert menu._filters["attr:fps"].label == "FPS"


def test_search_lists_matches_without_submenus(qtbot):
    options = [
        *BUILTIN_GROUPS,
        GroupByOption("attr:fps", "FPS", menu_group="Version"),
        GroupByOption(
            "product_attr:productGroup", "Product Group", menu_group="Product"
        ),
    ]
    menu = _menu(qtbot, options, "none")
    changed = Mock()
    menu.group_by_changed.connect(changed)
    _open(menu)

    menu._on_search_changed("product")

    assert [
        action.text()
        for action in menu._menu.actions()
        if action.isVisible() and action.text()
    ] == ["Product", "Product type", "Product > Product Group"]

    menu._on_search_changed("product g")
    menu._trigger_first_match()

    changed.assert_called_once_with("product_attr:productGroup")
