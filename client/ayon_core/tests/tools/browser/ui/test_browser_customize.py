"""Tests for the Browser's Customize menu."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.abstract import LoadersGrouping
from ayon_core.tools.browser.ui._browser_toolbar import Customize
from ayon_core.tools.browser.view_defaults import BROWSER_VIEW_DEFAULTS


def _customize(
    qtbot,
    loaders_grouping: LoadersGrouping = LoadersGrouping.UNGROUPED,
) -> Customize:
    defaults = BROWSER_VIEW_DEFAULTS
    customize = Customize(
        initial_card_width=defaults.card_width,
        initial_row_height=defaults.row_height,
        initial_show_empty_groups=defaults.show_empty_groups,
        initial_ungroup_empty_values=defaults.ungroup_empty_values,
        initial_display_type=defaults.display_type,
        initial_featured_version_order=defaults.featured_version_order,
        initial_latest_per_folder=defaults.latest_per_folder,
        initial_include_children=defaults.include_children,
        initial_loaders_grouping=loaders_grouping,
    )
    qtbot.addWidget(customize)
    return customize


def test_loaders_grouping_lists_every_option(qtbot):
    customize = _customize(qtbot)
    combo = customize.loaders_grouping_ui

    assert [combo.itemText(idx) for idx in range(combo.count())] == [
        "Ungrouped",
        "Grouped",
        "Group if multiple",
    ]
    assert {
        grouping for grouping, _ in Customize._LOADERS_GROUPINGS
    } == set(LoadersGrouping)


@pytest.mark.parametrize("loaders_grouping", list(LoadersGrouping))
def test_loaders_grouping_shows_initial_option(qtbot, loaders_grouping):
    customize = _customize(qtbot, loaders_grouping)
    combo = customize.loaders_grouping_ui

    index = combo.currentIndex()

    assert Customize._LOADERS_GROUPINGS[index][0] is loaders_grouping


def test_picking_loaders_grouping_emits_the_option(qtbot):
    customize = _customize(qtbot)
    changed = Mock()
    customize.loaders_grouping_changed.connect(changed)

    customize.loaders_grouping_ui.setCurrentIndex(2)

    changed.assert_called_once_with(LoadersGrouping.GROUPED_IF_MULTIPLE)


def test_set_loaders_grouping_does_not_emit(qtbot):
    """Applying a view must not mark it as modified."""
    customize = _customize(qtbot)
    changed = Mock()
    customize.loaders_grouping_changed.connect(changed)

    customize.set_loaders_grouping(LoadersGrouping.GROUPED)

    assert customize.loaders_grouping_ui.currentText() == "Grouped"
    changed.assert_not_called()
