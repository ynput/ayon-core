"""Unit tests for visibility rules of attribute definitions."""

from __future__ import annotations

from ayon_core.lib.attribute_definitions import (
    BoolDef,
    EnumDef,
    NumberDef,
    UILabelDef,
    VisibilityRule,
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


def _bool_controlled_defs():
    return [
        BoolDef(
            "use_range",
            default=False,
            visibility_rules=[
                VisibilityRule(values=[True], keys=["start", "end"]),
            ],
        ),
        NumberDef("start"),
        NumberDef("end"),
        NumberDef("other"),
    ]


def test_bool_controls_visibility():
    attr_defs = _bool_controlled_defs()

    assert _visible_keys(attr_defs, {"use_range": True}) == {
        "use_range", "start", "end", "other"
    }
    assert _visible_keys(attr_defs, {"use_range": False}) == {
        "use_range", "other"
    }


def test_missing_value_uses_default():
    attr_defs = _bool_controlled_defs()

    assert _visible_keys(attr_defs, {}) == {"use_range", "other"}


def test_rules_from_dict():
    attr_def = BoolDef(
        "toggle",
        visibility_rules=[{"values": [True], "keys": "target"}],
    )

    assert attr_def.visibility_rules == [
        VisibilityRule(values=[True], keys=["target"])
    ]


def test_enum_values_select_keys():
    attr_defs = [
        EnumDef(
            "mode",
            items=["a", "b", "c"],
            visibility_rules=[
                {"values": ["a"], "keys": ["only_a"]},
                {"values": ["a", "b"], "keys": ["a_or_b"]},
            ],
        ),
        NumberDef("only_a"),
        NumberDef("a_or_b"),
    ]

    assert _visible_keys(attr_defs, {"mode": "a"}) == {
        "mode", "only_a", "a_or_b"
    }
    assert _visible_keys(attr_defs, {"mode": "b"}) == {"mode", "a_or_b"}
    assert _visible_keys(attr_defs, {"mode": "c"}) == {"mode"}


def test_enum_multiselection_matches_any_selected():
    attr_defs = [
        EnumDef(
            "modes",
            items=["a", "b"],
            multiselection=True,
            visibility_rules=[{"values": ["b"], "keys": ["target"]}],
        ),
        NumberDef("target"),
    ]

    assert _visible_keys(attr_defs, {"modes": ["a", "b"]}) == {
        "modes", "target"
    }
    assert _visible_keys(attr_defs, {"modes": ["a"]}) == {"modes"}


def test_hidden_controller_hides_controlled():
    attr_defs = [
        BoolDef(
            "first",
            default=True,
            visibility_rules=[{"values": [True], "keys": ["second"]}],
        ),
        BoolDef(
            "second",
            default=True,
            visibility_rules=[{"values": [True], "keys": ["third"]}],
        ),
        NumberDef("third"),
    ]

    assert _visible_keys(
        attr_defs, {"first": False, "second": True}
    ) == {"first"}


def test_static_visible_has_priority():
    attr_defs = [
        BoolDef(
            "toggle",
            default=True,
            visibility_rules=[{"values": [True], "keys": ["target"]}],
        ),
        NumberDef("target", visible=False),
    ]

    assert _visible_keys(attr_defs, {"toggle": True}) == {"toggle"}


def test_multiple_controllers_must_all_match():
    attr_defs = [
        BoolDef("a", visibility_rules=[{"values": [True], "keys": ["t"]}]),
        BoolDef("b", visibility_rules=[{"values": [True], "keys": ["t"]}]),
        NumberDef("t"),
    ]

    assert "t" in _visible_keys(attr_defs, {"a": True, "b": True})
    assert "t" not in _visible_keys(attr_defs, {"a": True, "b": False})


def test_cycle_does_not_recurse_forever():
    attr_defs = [
        BoolDef(
            "a",
            default=True,
            visibility_rules=[{"values": [True], "keys": ["b"]}],
        ),
        BoolDef(
            "b",
            default=True,
            visibility_rules=[{"values": [True], "keys": ["a"]}],
        ),
    ]

    assert _visible_keys(attr_defs, {"a": True, "b": False}) == {"b"}


def test_ui_def_can_be_controlled():
    attr_defs = [
        BoolDef(
            "toggle",
            visibility_rules=[{"values": [True], "keys": ["note"]}],
        ),
        UILabelDef("Some note", key="note"),
    ]
    visibility_by_id = get_attr_defs_visibility(attr_defs, {"toggle": False})

    assert visibility_by_id[attr_defs[1].id] is False


def test_serialization_roundtrip():
    attr_def = _bool_controlled_defs()[0]

    data = serialize_attr_def(attr_def)
    assert data["visibility_rules"] == [
        {"values": [True], "keys": ["start", "end"]}
    ]

    new_attr_def = deserialize_attr_def(data)
    assert new_attr_def.visibility_rules == attr_def.visibility_rules
    assert new_attr_def == attr_def
    assert attr_def.clone().visibility_rules == attr_def.visibility_rules


def test_compare_respects_rules():
    attr_def = BoolDef("toggle")
    other = BoolDef(
        "toggle", visibility_rules=[{"values": [True], "keys": ["x"]}]
    )

    assert attr_def != other
    assert attr_def.compare_to_def(other, ignore_visible=True)
