"""Tests for 'TextDef' syntax argument."""
from __future__ import annotations

from ayon_core.lib.attribute_definitions import (
    TextDef,
    deserialize_attr_def,
)


def test_text_def_syntax_default_is_none():
    attr_def = TextDef("script", multiline=True)
    assert attr_def.syntax is None


def test_text_def_syntax_empty_string_is_none():
    attr_def = TextDef("script", multiline=True, syntax="")
    assert attr_def.syntax is None


def test_text_def_syntax_roundtrip():
    attr_def = TextDef("script", multiline=True, syntax="python")
    data = attr_def.serialize()
    assert data["syntax"] == "python"

    restored = deserialize_attr_def(data)
    assert isinstance(restored, TextDef)
    assert restored.syntax == "python"
    assert restored == attr_def


def test_text_def_without_syntax_does_not_serialize_key():
    """Older ayon-core versions fail on unknown 'syntax' argument."""
    data = TextDef("script", multiline=True).serialize()
    assert "syntax" not in data


def test_text_def_clone_keeps_syntax():
    attr_def = TextDef("script", multiline=True, syntax="python")
    assert attr_def.clone().syntax == "python"


def test_text_def_compare_syntax():
    python_def = TextDef("script", multiline=True, syntax="python")
    plain_def = TextDef("script", multiline=True)
    assert python_def != plain_def
    assert python_def == TextDef("script", multiline=True, syntax="python")
