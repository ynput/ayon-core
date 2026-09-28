"""Tests for the Browser's Group By dropdown."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.ui._browser_toolbar import GroupByMenu
from ayon_core.tools.browser.ui.browser_group_by import BUILTIN_GROUPS


def _menu(qtbot) -> GroupByMenu:
    menu = GroupByMenu(options=BUILTIN_GROUPS, default_key="product")
    qtbot.addWidget(menu)
    return menu


def _checked_keys(menu: GroupByMenu) -> list[str]:
    return [
        button.property("group_by_key")
        for button in menu._menu_grp.buttons()
        if button.isChecked()
    ]


def test_clicking_active_group_deselects_it(qtbot):
    menu = _menu(qtbot)
    changed = Mock()
    menu.group_by_changed.connect(changed)

    menu.grp_by_product.click()

    changed.assert_called_once_with("none")
    assert menu.get_selected_keys() == ["none"]
    assert _checked_keys(menu) == ["none"]


def test_clicking_other_group_selects_it(qtbot):
    menu = _menu(qtbot)
    changed = Mock()
    menu.group_by_changed.connect(changed)

    menu.grp_by_status.click()

    changed.assert_called_once_with("status")
    assert menu.get_selected_keys() == ["status"]
    assert _checked_keys(menu) == ["status"]


def test_removing_tag_clears_dropdown_highlight(qtbot):
    menu = _menu(qtbot)

    menu._handle_tag_removed("product")

    assert menu.get_selected_keys() == ["none"]
    assert _checked_keys(menu) == ["none"]
