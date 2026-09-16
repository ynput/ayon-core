"""Value-page behavior of the table filter dropdown.

Covers mutually exclusive (single-select) filters, their preselected
default, and the "No/Has {label}" options for fields that can be empty.
"""

from unittest.mock import Mock

import pytest

from ayon_core.ui.components.table_filter import (
    AYTableFilterProxyModel,
    FilterCriterion,
    _FilterDropdown,
    HAS_VALUE,
    NO_VALUE,
)
from ayon_core.ui.components.table_model import (
    FilterEntry,
    ValueOption,
)


def _dropdown(qtbot, entries: list[FilterEntry]) -> _FilterDropdown:
    model = Mock()
    model.get_distinct_values.return_value = []
    table_filter = Mock()
    table_filter.width.return_value = 300
    dropdown = _FilterDropdown(model, table_filter, entries)
    qtbot.addWidget(dropdown)
    return dropdown


def _checked(dropdown: _FilterDropdown) -> list[str]:
    return [
        value
        for value, button in dropdown._value_buttons.items()
        if button.isChecked()
    ]


@pytest.fixture
def boolean_entry() -> FilterEntry:
    return FilterEntry(
        "hasReviewables", "Has Reviewables",
        options=["Yes", "No"], single_select=True,
    )


def test_single_select_preselects_first_value(qtbot, boolean_entry):
    dropdown = _dropdown(qtbot, [boolean_entry])
    ready = []
    dropdown.criterion_ready.connect(lambda *args: ready.append(args))

    dropdown._on_attr_selected("hasReviewables", "Has Reviewables")

    assert _checked(dropdown) == ["Yes"]
    dropdown._on_apply()
    assert ready == [("hasReviewables", ["Yes"], False)]


def test_untouched_preselection_is_not_applied_on_dismiss(
    qtbot, boolean_entry,
):
    dropdown = _dropdown(qtbot, [boolean_entry])
    ready = []
    dropdown.criterion_ready.connect(lambda *args: ready.append(args))
    dropdown._on_attr_selected("hasReviewables", "Has Reviewables")
    dropdown._stack.setCurrentIndex(1)

    dropdown.close()

    assert ready == []


def test_single_select_values_are_exclusive(qtbot, boolean_entry):
    dropdown = _dropdown(qtbot, [boolean_entry])
    dropdown._on_attr_selected("hasReviewables", "Has Reviewables")

    dropdown._value_buttons["No"].click()
    assert _checked(dropdown) == ["No"]

    # Clicking the selected value keeps it selected, like a radio button.
    dropdown._value_buttons["No"].click()
    assert _checked(dropdown) == ["No"]


def test_empty_options_combine_with_other_values(qtbot):
    entry = FilterEntry(
        "tags", "Tags", options=["a", "b"], show_has_value_filters=True,
    )
    dropdown = _dropdown(qtbot, [entry])
    dropdown._on_attr_selected("tags", "Tags")

    assert list(dropdown._value_buttons) == [NO_VALUE, HAS_VALUE, "a", "b"]
    assert dropdown._value_buttons[NO_VALUE].text().strip() == "No Tags"
    assert _checked(dropdown) == []

    dropdown._value_buttons["a"].click()
    dropdown._value_buttons[NO_VALUE].click()
    assert _checked(dropdown) == [NO_VALUE, "a"]

    # "No" and "Has" together would match everything.
    dropdown._value_buttons[HAS_VALUE].click()
    assert _checked(dropdown) == [HAS_VALUE, "a"]

    dropdown._value_buttons["b"].click()
    assert _checked(dropdown) == [HAS_VALUE, "a", "b"]


def test_text_filter_combines_empty_option_with_typed_text(qtbot):
    entry = FilterEntry(
        "attr:version:comment", "Comment",
        text_search=True, show_has_value_filters=True,
    )
    dropdown = _dropdown(qtbot, [entry])
    dropdown._on_attr_selected("attr:version:comment", "Comment")
    dropdown._stack.setCurrentIndex(1)

    assert list(dropdown._value_buttons) == [NO_VALUE, HAS_VALUE]
    dropdown._value_buttons[NO_VALUE].click()
    assert dropdown._current_values() == ([NO_VALUE], False)

    dropdown._attr_search.setText("final")
    assert _checked(dropdown) == [NO_VALUE]
    assert dropdown._current_values() == ([NO_VALUE, "final"], True)


def test_editing_text_criterion_restores_text_and_empty_option(qtbot):
    entry = FilterEntry(
        "attr:version:comment", "Comment",
        text_search=True, show_has_value_filters=True,
    )
    dropdown = _dropdown(qtbot, [entry])
    dropdown._populate_value_page(
        "attr:version:comment", "Comment", [NO_VALUE, "final"]
    )

    assert _checked(dropdown) == [NO_VALUE]
    assert dropdown._attr_search.text() == "final"


def test_entries_without_flags_are_unchanged(qtbot):
    entry = FilterEntry("productType", "Type", options=["render", "model"])
    dropdown = _dropdown(qtbot, [entry])
    dropdown._on_attr_selected("productType", "Type")

    assert list(dropdown._value_buttons) == ["render", "model"]
    assert _checked(dropdown) == []
    dropdown._value_buttons["render"].click()
    dropdown._value_buttons["model"].click()
    assert _checked(dropdown) == ["render", "model"]


def test_value_options_accept_mixed_str_and_valueoption(qtbot):
    entry = FilterEntry(
        "status", "Status",
        options=[
            ValueOption("in_progress", "In Progress", icon="autorenew"),
            "done",
        ],
        single_select=True,
    )
    dropdown = _dropdown(qtbot, [entry])
    # The model reports the same raw values back (e.g. from loaded rows);
    # they must not duplicate the configured ValueOption entries.
    dropdown._model.get_distinct_values.return_value = ["in_progress", "done"]

    dropdown._on_attr_selected("status", "Status")

    assert list(dropdown._value_buttons) == ["in_progress", "done"]
    assert dropdown._value_buttons["in_progress"].text().strip() == (
        "In Progress"
    )
    # The configured ValueOption is preselected like a plain string would
    # be for a single-select filter.
    assert _checked(dropdown) == ["in_progress"]


@pytest.mark.parametrize(
    ("values", "cell", "expected"),
    [
        ([NO_VALUE], "", True),
        ([NO_VALUE], None, True),
        ([NO_VALUE], [], True),
        ([NO_VALUE], ["a"], False),
        # Text that merely looks like an empty list is a value.
        ([NO_VALUE], "[]", False),
        ([HAS_VALUE], "[]", True),
        ([NO_VALUE], "x", False),
        ([HAS_VALUE], "x", True),
        ([HAS_VALUE], None, False),
        ([NO_VALUE, "fin"], "", True),
        ([NO_VALUE, "fin"], "final", True),
        ([NO_VALUE, "fin"], "wip", False),
    ],
)
def test_proxy_matches_empty_options(qapp, values, cell, expected):
    proxy = AYTableFilterProxyModel()
    proxy.set_row_value_getter(lambda _index, _key: cell)
    source = Mock()
    proxy.sourceModel = lambda: source
    proxy.set_criteria(
        [FilterCriterion("comment", "Comment", values, use_substring=True)],
        [],
        [FilterEntry("comment", "Comment")],
    )

    assert proxy._direct_match(0, Mock()) is expected
