"""Excluding filter criteria in the Browser's server-side query."""

import json
from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.ui.components.table_filter import (
    FilterCriterion,
    NO_VALUE,
)


def _controller(attributes_by_scope=None) -> BrowserWidgetController:
    controller = BrowserWidgetController.__new__(BrowserWidgetController)
    controller._attributes_by_scope = attributes_by_scope or {}
    controller._column_manager = Mock()
    controller._column_manager.get_filter_keys.return_value = set()
    controller._get_column_context = Mock()
    controller._reset_pagination = Mock()
    return controller


def _conditions(encoded: str) -> list:
    return json.loads(encoded)["conditions"] if encoded else []


@pytest.mark.parametrize(
    ("condition", "expected"),
    [
        (
            {"key": "productType", "value": ["a"], "operator": "in"},
            {"key": "productType", "value": ["a"], "operator": "notin"},
        ),
        (
            {"key": "tags", "value": ["a"], "operator": "includesany"},
            {"key": "tags", "value": ["a"], "operator": "excludesany"},
        ),
        (
            {
                "operator": "or",
                "conditions": [
                    {"key": "attrib.comment", "operator": "isnull"},
                    {"key": "attrib.comment", "value": "", "operator": "eq"},
                ],
            },
            {
                "operator": "and",
                "conditions": [
                    {"key": "attrib.comment", "operator": "notnull"},
                    {
                        "operator": "or",
                        "conditions": [
                            {
                                "key": "attrib.comment",
                                "value": "",
                                "operator": "ne",
                            },
                            {"key": "attrib.comment", "operator": "isnull"},
                        ],
                    },
                ],
            },
        ),
        # An unset attribute is null, which 'in' never matches.
        (
            {"key": "attrib.intent", "value": ["wip"], "operator": "in"},
            {
                "operator": "or",
                "conditions": [
                    {
                        "key": "attrib.intent",
                        "value": ["wip"],
                        "operator": "notin",
                    },
                    {"key": "attrib.intent", "operator": "isnull"},
                ],
            },
        ),
        ({"key": "name", "value": "%a%", "operator": "like"}, None),
        (
            {
                "operator": "or",
                "conditions": [
                    {"key": "name", "value": ["a"], "operator": "in"},
                    {"key": "name", "value": "%b%", "operator": "like"},
                ],
            },
            None,
        ),
    ],
)
def test_negate_condition(condition, expected):
    assert BrowserWidgetController._negate_condition(condition) == expected


def test_excluded_product_type_uses_notin():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productType", "Product type", ["model", "rig"], exclude=True
        ),
        FilterCriterion("taskType", "Task type", ["Modeling"]),
    ])

    query_filters = controller._get_query_filters()

    assert _conditions(query_filters["product_filter"]) == [
        {"key": "productType", "value": ["model", "rig"], "operator": "notin"}
    ]
    assert _conditions(query_filters["task_filter"]) == [
        {"key": "taskType", "value": ["Modeling"], "operator": "in"}
    ]


def test_excluded_no_value_with_regular_value():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion("tags", "Tags", [NO_VALUE, "a"], exclude=True),
    ])

    conditions = _conditions(controller._get_query_filters()["version_filter"])

    # NOT (tags == [] OR tags includes a) -> tags != [] AND excludes a
    assert conditions == [{
        "operator": "and",
        "conditions": [
            {"key": "tags", "value": [], "operator": "ne"},
            {"key": "tags", "value": ["a"], "operator": "excludesany"},
        ],
    }]


def test_excluded_has_reviewables_is_inverted():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "hasReviewables", "Has Reviewables", ["Yes"], exclude=True
        ),
    ])

    assert controller._get_query_filters()["has_reviewables"] is False


def test_excluded_substring_is_left_to_local_filter():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", ["main"],
            use_substring=True, exclude=True,
        ),
    ])

    assert controller._get_query_filters()["product_filter"] == ""


def test_hero_filter_queries_hero_version_entities():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion("version", "Version", ["Hero"]),
    ])

    query_filters = controller._get_query_filters()

    # 'featuredOnly' would return the regular version the hero points to
    assert query_filters["featured_only"] is None
    assert _conditions(query_filters["version_filter"]) == [
        {"key": "version", "value": 0, "operator": "lt"}
    ]


def test_excluded_hero_filter_is_negated():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion("version", "Version", ["Hero"], exclude=True),
    ])

    query_filters = controller._get_query_filters()

    assert query_filters["featured_only"] is None
    assert _conditions(query_filters["version_filter"]) == [
        {"key": "version", "value": 0, "operator": "gte"}
    ]


def test_hero_with_other_featured_types_uses_featured_only():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion("version", "Version", ["Hero", "Latest"]),
    ])

    query_filters = controller._get_query_filters()

    assert query_filters["featured_only"] == ["hero", "latest"]
    assert query_filters["version_filter"] == ""
