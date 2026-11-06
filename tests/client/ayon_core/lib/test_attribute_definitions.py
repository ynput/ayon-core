"""Unit tests for visibility conditions of attribute definitions."""

from __future__ import annotations

import json

import pytest
from ayon_core.lib.attribute_conditions import (
    GroupCondition,
    ValueCondition,
    condition_from_data,
)
from ayon_core.lib.attribute_definitions import (
    BoolDef,
    EnumDef,
    NumberDef,
    TextDef,
    UILabelDef,
    deserialize_attr_def,
    get_attr_defs_visibility,
    serialize_attr_def,
)


def _visible_keys(attr_defs, values):
    visibility_by_id = get_attr_defs_visibility(attr_defs, values)
    return {
        attr_def.key
        for attr_def in attr_defs
        if visibility_by_id[attr_def.id]
    }


def _range_defs():
    return [
        BoolDef("use_range", default=False),
        NumberDef(
            "start",
            visibility_condition=ValueCondition("use_range", True),
        ),
        NumberDef("other"),
    ]


def test_value_condition_controls_visibility():
    attr_defs = _range_defs()

    assert _visible_keys(attr_defs, {"use_range": True}) == {
        "use_range", "start", "other"
    }
    assert _visible_keys(attr_defs, {"use_range": False}) == {
        "use_range", "other"
    }


def test_missing_value_uses_default():
    assert _visible_keys(_range_defs(), {}) == {"use_range", "other"}


@pytest.mark.parametrize(
    "operator, condition_value, value, expected",
    [
        ("eq", "a", "a", True),
        ("eq", "a", "b", False),
        ("neq", "a", "b", True),
        ("neq", "a", "a", False),
        ("in", ["a", "b"], "b", True),
        ("in", ["a", "b"], "c", False),
        ("not_in", ["a", "b"], "c", True),
        ("contains", "b", ["a", "b"], True),
        ("contains", "c", ["a", "b"], False),
        ("contains", "ell", "hello", True),
        ("not_contains", "c", ["a", "b"], True),
        ("gt", 5, 6, True),
        ("gt", 5, 5, False),
        ("gte", 5, 5, True),
        ("lt", 5, 4, True),
        ("lte", 5, 6, False),
        # Incomparable types do not raise
        ("gt", 5, "text", False),
        ("contains", "a", 10, False),
    ],
)
def test_value_condition_operators(operator, condition_value, value, expected):
    condition = ValueCondition("key", condition_value, operator)

    assert condition.evaluate({"key": value}) is expected


def test_unknown_operator_raises():
    with pytest.raises(ValueError):
        ValueCondition("key", 1, "between")


def test_missing_key_is_not_met():
    assert ValueCondition("key", 1, "neq").evaluate({}) is False


def test_and_or_conditions():
    condition = GroupCondition(
        [
            GroupCondition([
                ValueCondition("a", True),
                ValueCondition("b", True),
            ]),
            ValueCondition("c", 10, "gte"),
        ],
        operator="or",
    )

    assert condition.evaluate({"a": True, "b": True, "c": 0})
    assert not condition.evaluate({"a": True, "b": False, "c": 0})
    assert condition.evaluate({"a": False, "b": False, "c": 10})
    assert condition.get_keys() == {"a", "b", "c"}
    assert GroupCondition([]).evaluate({})
    assert not GroupCondition([], operator="or").evaluate({})


def test_unknown_group_operator_raises():
    with pytest.raises(ValueError):
        GroupCondition([], operator="xor")


def test_multiselection_enum_contains():
    attr_defs = [
        EnumDef("modes", items=["a", "b"], multiselection=True),
        NumberDef(
            "target",
            visibility_condition=ValueCondition("modes", "b", "contains"),
        ),
    ]

    assert "target" in _visible_keys(attr_defs, {"modes": ["a", "b"]})
    assert "target" not in _visible_keys(attr_defs, {"modes": ["a"]})


def test_hidden_attribute_value_is_not_available():
    attr_defs = [
        BoolDef("first", default=True),
        BoolDef(
            "second",
            default=True,
            visibility_condition=ValueCondition("first", True),
        ),
        NumberDef(
            "third",
            visibility_condition=ValueCondition("second", True),
        ),
        NumberDef(
            "fourth",
            visibility_condition=ValueCondition("second", True, "neq"),
        ),
    ]

    assert _visible_keys(
        attr_defs, {"first": False, "second": True}
    ) == {"first"}


def test_or_keeps_visible_when_other_branch_is_hidden():
    attr_defs = [
        BoolDef("first", default=False),
        BoolDef(
            "second",
            visibility_condition=ValueCondition("first", True),
        ),
        NumberDef(
            "target",
            visibility_condition=GroupCondition(
                [
                    ValueCondition("second", True),
                    ValueCondition("first", False),
                ],
                operator="or",
            ),
        ),
    ]

    assert "target" in _visible_keys(attr_defs, {"first": False})


def test_static_visible_has_priority():
    attr_defs = [
        BoolDef("toggle", default=True),
        NumberDef(
            "target",
            visible=False,
            visibility_condition=ValueCondition("toggle", True),
        ),
    ]

    assert _visible_keys(attr_defs, {"toggle": True}) == {"toggle"}


def test_cycle_is_hidden():
    attr_defs = [
        BoolDef(
            "a", default=True, visibility_condition=ValueCondition("b", True)
        ),
        BoolDef(
            "b", default=True, visibility_condition=ValueCondition("a", True)
        ),
        NumberDef("c"),
    ]

    assert _visible_keys(attr_defs, {}) == {"c"}


def test_ui_def_can_have_condition():
    attr_defs = [
        BoolDef("toggle"),
        UILabelDef(
            "Some note",
            visibility_condition=ValueCondition("toggle", True),
        ),
    ]
    visibility_by_id = get_attr_defs_visibility(attr_defs, {"toggle": False})

    assert visibility_by_id[attr_defs[1].id] is False


def test_condition_from_dict():
    attr_def = TextDef(
        "name",
        visibility_condition={
            "type": "group",
            "operator": "or",
            "conditions": [
                {"type": "value", "key": "a", "value": 1, "operator": "gt"},
                {"type": "value", "key": "b", "value": "x"},
            ],
        },
    )

    assert attr_def.visibility_condition == GroupCondition(
        [ValueCondition("a", 1, "gt"), ValueCondition("b", "x")],
        operator="or",
    )


def test_unknown_condition_type_raises():
    with pytest.raises(ValueError):
        condition_from_data({"type": "unknown", "conditions": []})


def test_serialization_roundtrip():
    attr_def = NumberDef(
        "start",
        visibility_condition=GroupCondition(
            [
                ValueCondition("use_range", True),
                ValueCondition("mode", ["a", "b"], "in"),
            ],
            operator="or",
        ),
    )

    data = json.loads(json.dumps(serialize_attr_def(attr_def)))
    new_attr_def = deserialize_attr_def(data)

    assert new_attr_def.visibility_condition == attr_def.visibility_condition
    assert new_attr_def == attr_def
    assert attr_def.clone() == attr_def
    assert serialize_attr_def(NumberDef("n"))["visibility_condition"] is None


def test_compare_respects_condition():
    attr_def = BoolDef("toggle")
    other = BoolDef(
        "toggle", visibility_condition=ValueCondition("x", True)
    )

    assert attr_def != other
    assert attr_def.compare_to_def(other, ignore_visible=True)
