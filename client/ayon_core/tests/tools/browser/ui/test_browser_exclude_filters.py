"""Excluding filter criteria in the Browser's server-side query."""

import json
import logging
from unittest.mock import Mock

import pytest

from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.ui.components.table_filter import (
    FilterCriterion,
    NO_VALUE,
    filter_values_match,
)


@pytest.fixture(autouse=True)
def _mock_contains_operator(monkeypatch):
    # Match typed text with 'like', as servers older than 1.17.5 do.
    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller"
        ".server_supports_contains_operator",
        lambda: False,
    )


def _controller(attributes_by_scope=None) -> BrowserWidgetController:
    controller = BrowserWidgetController.__new__(BrowserWidgetController)
    controller.log = logging.getLogger(__name__)
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
    # The product headers still show the featured hero
    assert query_filters["featured_types"] == ["hero"]
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
    assert query_filters["featured_types"] is None
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
    assert query_filters["featured_types"] == ["hero", "latest"]
    assert query_filters["version_filter"] == ""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("main", "%main%"),
        ("render main", "%render main%"),
        (r"render_a\b", r"%render\_a\\b%"),
        ("50%", r"%50\%%"),
    ],
)
def test_like_pattern_escapes_wildcards(text, expected):
    assert BrowserWidgetController._like_pattern(text) == expected


@pytest.mark.parametrize(
    ("use_contains", "expected"),
    [
        (
            True,
            [{"key": "name", "value": "50%_a", "operator": "contains"}],
        ),
        (
            False,
            [{"key": "name", "value": r"%50\%\_a%", "operator": "like"}],
        ),
    ],
)
def test_text_match_follows_server_support(
    monkeypatch, use_contains, expected
):
    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller"
        ".server_supports_contains_operator",
        lambda: use_contains,
    )
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", ["50%_a"], use_substring=True,
        ),
    ])

    assert _conditions(
        controller._get_query_filters()["product_filter"]
    ) == expected


def test_contains_check_failure_falls_back_to_like(monkeypatch):
    def _raise():
        raise RuntimeError("No server connection")

    monkeypatch.setattr(
        "ayon_core.tools.browser.ui.browser_controller"
        ".server_supports_contains_operator",
        _raise,
    )
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", ["main"], use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["product_filter"]) == [
        {"key": "name", "value": "%main%", "operator": "like"}
    ]


def test_comma_separated_text_matches_any_part():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", ["main,lighting"],
            use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["product_filter"]) == [
        {
            "operator": "or",
            "conditions": [
                {"key": "name", "value": "%main%", "operator": "like"},
                {"key": "name", "value": "%lighting%", "operator": "like"},
            ],
        }
    ]


def test_comma_separated_text_with_no_value_option():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "author", "Author", [NO_VALUE, "jo,ann"], use_substring=True,
        ),
    ])

    conditions = _conditions(controller._get_query_filters()["version_filter"])
    assert len(conditions) == 1
    assert conditions[0]["operator"] == "or"
    assert conditions[0]["conditions"][1] == {
        "operator": "or",
        "conditions": [
            {"key": "author", "value": "%jo%", "operator": "like"},
            {"key": "author", "value": "%ann%", "operator": "like"},
        ],
    }


def test_text_of_only_commas_does_not_filter():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", [","], use_substring=True,
        ),
    ])

    assert controller._get_query_filters()["product_filter"] == ""


@pytest.mark.parametrize(
    ("cell", "text", "expected"),
    [
        ("renderCompositingMain", "main", True),
        ("renderCompositingMain", "light, MAIN", True),
        ("workfileLighting", "main,light", True),
        ("modelHero", "main, light", False),
        ("modelHero", ",", True),
    ],
)
def test_local_filter_matches_any_comma_part(cell, text, expected):
    assert filter_values_match(cell, [text], use_substring=True) is expected


def test_product_name_substring_is_partial_match():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "productName", "Product name", ["Main"], use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["product_filter"]) == [
        {"key": "name", "value": "%Main%", "operator": "like"}
    ]


def test_text_attribute_substring_is_partial_match():
    controller = _controller({"version": {"comment": {"type": "string"}}})
    controller.set_filter_criteria([
        FilterCriterion(
            "attr:version:comment", "Comment", ["fix"], use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["version_filter"]) == [
        {"key": "attrib.comment", "value": "%fix%", "operator": "like"}
    ]


def test_each_typed_value_matches_as_substring():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "taskType", "Type", ["anim", "comp"], use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["task_filter"]) == [
        {
            "operator": "or",
            "conditions": [
                {"key": "taskType", "value": "%anim%", "operator": "like"},
                {"key": "taskType", "value": "%comp%", "operator": "like"},
            ],
        }
    ]


def test_task_name_substring_with_no_value():
    controller = _controller()
    controller.set_filter_criteria([
        FilterCriterion(
            "task", "Task", [NO_VALUE, "an, li"], use_substring=True,
        ),
    ])

    assert _conditions(controller._get_query_filters()["task_filter"]) == [
        {
            "operator": "or",
            "conditions": [
                {"key": "id", "operator": "isnull"},
                {
                    "operator": "or",
                    "conditions": [
                        {"key": "name", "value": "%an%", "operator": "like"},
                        {"key": "name", "value": "%li%", "operator": "like"},
                    ],
                },
            ],
        }
    ]
