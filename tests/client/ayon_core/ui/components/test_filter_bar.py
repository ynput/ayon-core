"""Tests for the filter bar that is not bound to a table."""

from __future__ import annotations

from ayon_core.ui.components.table_filter import (
    AYFilterBar,
    FilterCriterion,
    criterion_text,
)
from ayon_core.ui.components.table_model import FLAG_VALUE, FilterEntry


def _create_bar(qtbot) -> tuple[AYFilterBar, list]:
    bar = AYFilterBar(
        [
            FilterEntry("comments", "Comments", icon="chat", flag=True),
            FilterEntry("author", "User", icon="person"),
            FilterEntry("text", "Text", icon="search", text_search=True),
        ],
        values_getter=lambda key: ["roy"] if key == "author" else [],
        placeholder="Search and filter",
        search_key="text",
    )
    qtbot.addWidget(bar)
    reported = []
    bar.filters_changed.connect(reported.append)
    return bar, reported


def test_flag_is_applied_when_picked(qtbot):
    bar, reported = _create_bar(qtbot)

    bar._dropdown._on_attr_selected("comments", "Comments")

    assert reported == [
        [FilterCriterion("comments", "Comments", [FLAG_VALUE])]
    ]
    assert criterion_text(reported[0][0]) == "Comments"
    excluded = FilterCriterion(
        "comments", "Comments", [FLAG_VALUE], exclude=True
    )
    assert criterion_text(excluded) == "Not comments"


def test_values_come_from_the_values_getter(qtbot):
    bar, _reported = _create_bar(qtbot)

    bar._dropdown._on_attr_selected("author", "User")

    assert list(bar._dropdown._value_buttons) == ["roy"]


def test_typed_text_is_offered_as_search(qtbot):
    bar, reported = _create_bar(qtbot)
    dropdown = bar._dropdown
    dropdown.open_for_new(bar)

    dropdown._attr_search.setText("shoulder")
    search_button = next(iter(dropdown._attr_buttons.values()))
    assert search_button.text().strip() == 'Search "shoulder"'
    search_button.click()

    assert reported == [
        [FilterCriterion("text", "Text", ["shoulder"], use_substring=True)]
    ]


def test_quick_action_toggles_its_flag(qtbot):
    bar, reported = _create_bar(qtbot)
    button = bar.create_quick_action("comments", "chat", "Comments")
    # Not part of the bar, the owner places it
    assert button.parent() is None

    button.click()
    assert button.isChecked()
    assert [c.key for c in bar.get_criteria()] == ["comments"]

    # Removing the filter from the bar unchecks the button
    bar.set_active_criteria([])
    assert not button.isChecked()
    button.click()
    button.click()
    assert bar.get_criteria() == []
    assert len(reported) == 4
