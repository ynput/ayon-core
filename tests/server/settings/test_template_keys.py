"""Tests for conversion of legacy template keys in server settings.

The conversion module does not depend on 'ayon_server', so it is loaded
by path and tested together with client template formatting.
"""
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from ayon_core.lib.path_templates import StringTemplate
from ayon_core.lib.plugin_tools import prepare_template_data

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "server" / "settings" / "template_keys.py"
)
_spec = importlib.util.spec_from_file_location(
    "_server_template_keys", _MODULE_PATH
)
template_keys = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(template_keys)
convert_legacy_template_keys = template_keys.convert_legacy_template_keys


def _get_data() -> dict:
    return {
        "family": "render",
        "variant": "main",
        "task": {"name": "animation", "type": "Animation", "short": "anim"},
        "product": {"type": "render", "basetype": "render"},
        "host": {"name": "maya"},
        "folder": {"name": "sh010", "type": "Shot"},
        "version": 3,
        "frame": 1001,
        "ext": "exr",
        "renderlayer": "beautyMain",
        "symbol": "_shot",
        "number": "01_shot",
        "unicode": "école",
        "empty": "",
        "nothing": None,
        "x": "single",
    }


@pytest.mark.parametrize(
    "template, expected",
    [
        # Not changed
        ("", ""),
        ("{product[type]}{variant}", "{product[type]}{variant}"),
        ("{task[name]:upper}", "{task[name]:upper}"),
        ("{camelKey}", "{camelKey}"),
        ("text without keys", "text without keys"),
        ("{{Escaped}}", "{{Escaped}}"),
        # Capitalized
        ("{Variant}", "{variant:upperfirst}"),
        ("{Task[name]}", "{task[name]:upperfirst}"),
        ("{Task}", "{task:upperfirst}"),
        ("{Renderlayer}", "{renderlayer:upperfirst}"),
        # Uppercase
        ("{VARIANT}", "{variant:upper}"),
        ("{TASK[NAME]}", "{task[name]:upper}"),
        ("{PRODUCT[TYPE]}", "{product[type]:upper}"),
        ("{RENDER_LAYER}", "{render_layer:upper}"),
        # Single character, capitalized has priority as it had in data
        ("{X}", "{x:upperfirst}"),
        # Optional parts
        (
            "{product[type]}{Task[name]}{Variant}<_{Aov}>",
            "{product[type]}{task[name]:upperfirst}{variant:upperfirst}"
            "<_{aov:upperfirst}>",
        ),
        (
            "{FOLDER[NAME]}<_{Variant}<_{OUTPUT}>>",
            "{folder[name]:upper}<_{variant:upperfirst}<_{output:upper}>>",
        ),
        # Combinations that never worked are not changed
        ("{TASK[name]}", "{TASK[name]}"),
        ("{TaSk}", "{TaSk}"),
        ("{tASK}", "{tASK}"),
        # Format spec or conversion cannot be combined with named spec
        ("{Variant:>8}", "{Variant:>8}"),
        ("{VARIANT!r}", "{VARIANT!r}"),
        ("{Version:0>3}", "{Version:0>3}"),
    ],
)
def test_convert(template: str, expected: str):
    assert convert_legacy_template_keys(template) == expected
    # Conversion of converted template does not change it
    assert convert_legacy_template_keys(expected) == expected


@pytest.mark.parametrize("value", [None, 1, ["{Task}"]])
def test_convert_invalid_value(value):
    assert convert_legacy_template_keys(value) == value


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize(
    "template",
    [
        "{Task[name]}",
        "{TASK[NAME]}",
        "{Task}",
        "{TASK}",
        "{family}{Task[name]}{Variant}",
        "{FAMILY}_{Family}_{family}",
        "{product[type]}{Task[short]}<_{Output}>{Variant}",
        "{PRODUCT[TYPE]}_{Product[type]}_{HOST[NAME]}",
        "{Folder[name]}_{FOLDER[NAME]}_{Folder[type]}",
        "{product[type]}{Task[name]}_{Renderlayer}_{RENDERLAYER}",
        # Not string values are not changed
        "v{Version}_{VERSION}_{Frame}",
        # First ascii letter or digit is uppercased, the rest is kept
        "{Symbol}_{SYMBOL}",
        "{Number}_{NUMBER}",
        "{Unicode}_{UNICODE}",
        "{Empty}_{EMPTY}",
        "{X}",
        # Optional parts
        "{ext}<_{Output}>",
        "{ext}<_{OUTPUT}>",
        "{ext}<_{Variant}>",
        "{ext}<_{VARIANT}>",
        "{ext}<_{VARIANT}_{Output}>",
        "{ext}<_{Output}_{VARIANT}>",
        "{ext}<_{Variant}<_{OUTPUT}>>",
        "{ext}<_{Output}<_{Variant}>>",
        "{ext}<_{Task[name]}<_{TASK[NAME]}<_{Output}>>>",
        "<{Nothing}_>{ext}",
        "<{Task[short]}_>{ext}",
        "<{Missing}>{variant}",
        # Missing keys
        "{Missing}_{MISSING}",
        "{Nothing}",
    ],
)
def test_converted_template_result(template: str):
    """Converted template with source data gives the same result.

    Reference is the legacy template filled with data prepared by
    'prepare_template_data'.
    """
    data = _get_data()
    src_data = copy.deepcopy(data)
    expected = StringTemplate(template).format(prepare_template_data(data))

    converted = convert_legacy_template_keys(template)
    result = StringTemplate(converted).format(data)

    assert str(result) == str(expected).replace(template, converted)
    assert result.solved == expected.solved
    assert data == src_data


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_converted_placeholder_in_value():
    """Creators that fill product name in 2 steps get the same result.

    They pass '{key}' as a value and fill the placeholder in the result
    later with python formatting and data from 'prepare_template_data'.
    """
    template = "{product[type]}{Composition}{LAYER}"
    data = {
        "product": {"type": "render"},
        "composition": "{composition}",
        "layer": "{layer}",
    }
    fill_data = prepare_template_data(
        {"composition": "mainComp", "layer": "bg"}
    )

    legacy = StringTemplate(template).format_strict(
        prepare_template_data(data)
    )
    result = StringTemplate(
        convert_legacy_template_keys(template)
    ).format_strict(data)

    assert str(legacy) == "render{Composition}{LAYER}"
    assert str(result) == "render{composition:upperfirst}{layer:upper}"
    assert (
        str(result).format(**fill_data)
        == str(legacy).format(**fill_data)
        == "renderMainCompBG"
    )
