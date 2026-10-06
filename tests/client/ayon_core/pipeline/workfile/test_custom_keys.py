"""Tests for custom keys in workfile file template."""
from __future__ import annotations

import pytest

from ayon_core.lib import StringTemplate
from ayon_core.pipeline.workfile.path_resolving import (
    WorkfileDataParser,
    get_last_workfile_with_version_from_paths,
    get_workfile_custom_keys,
    resolve_workfile_custom_data,
)

TEMPLATE = (
    "{folder[name]}_{task[name]}_r{revision:0>2}_v{version:0>3}"
    "<_{comment}>.{ext}"
)
OPTIONAL_TEMPLATE = (
    "{folder[name]}_{task[name]}<_r{revision:0>2}>_v{version:0>3}"
    "<_{comment}>.{ext}"
)
TEMPLATE_DATA = {
    "project": {"name": "demo", "code": "demo"},
    "folder": {"name": "sh010"},
    "task": {"name": "anim", "type": "Animation"},
}


def test_no_custom_keys():
    template = "{folder[name]}_{task[name]}_v{version:0>3}<_{comment}>.{ext}"
    assert get_workfile_custom_keys(template, TEMPLATE_DATA) == []


@pytest.mark.parametrize(
    "template, is_number",
    [
        ("{revision:0>2}", True),
        ("{revision:03}", True),
        ("{revision:03d}", True),
        ("{revision:d}", True),
        ("{revision}", False),
        ("{revision:>3}", False),
    ],
)
def test_custom_key_type(template, is_number):
    custom_keys = get_workfile_custom_keys(template, TEMPLATE_DATA)
    assert len(custom_keys) == 1
    assert custom_keys[0].key == "revision"
    assert custom_keys[0].is_number is is_number


def test_custom_key_info():
    template = (
        "{folder[name]}_r{revision:0>2}_v{version:0>3}<_{variant}>.{ext}"
    )
    revision, variant = get_workfile_custom_keys(template, TEMPLATE_DATA)
    assert revision.key == "revision"
    assert revision.label == "Revision"
    assert revision.optional is False
    assert revision.before_version is True
    assert revision.default == 1

    assert variant.key == "variant"
    assert variant.is_number is False
    assert variant.optional is True
    assert variant.before_version is False
    assert variant.default is None


def test_resolve_custom_data_priority():
    custom_keys = get_workfile_custom_keys(TEMPLATE, TEMPLATE_DATA)
    # Default value for the very first workfile
    assert resolve_workfile_custom_data(custom_keys) == {"revision": 1}
    assert resolve_workfile_custom_data(custom_keys, None, {}) == {
        "revision": 1
    }
    # First source with a value wins
    assert resolve_workfile_custom_data(
        custom_keys, None, {"revision": 3}, {"revision": 2}
    ) == {"revision": 3}
    # Invalid values are skipped
    assert resolve_workfile_custom_data(
        custom_keys, {"revision": "abc"}, {"revision": "4"}
    ) == {"revision": 4}


def test_parse_custom_data():
    parser = WorkfileDataParser(TEMPLATE, TEMPLATE_DATA)
    assert parser.has_custom_keys

    parsed = parser.parse_data("sh010_anim_r02_v013.ma")
    assert parsed.version == 13
    assert parsed.comment is None
    assert parsed.ext == ".ma"
    assert parsed.custom_data == {"revision": 2}

    parsed = parser.parse_data("sh010_anim_r02_v013_blocking.ma")
    assert parsed.version == 13
    assert parsed.comment == "blocking"
    assert parsed.custom_data == {"revision": 2}

    # File that does not match the template
    parsed = parser.parse_data("sh010_anim_v013.ma")
    assert parsed.version is None
    assert parsed.custom_data == {}


def test_parse_optional_custom_data():
    parser = WorkfileDataParser(OPTIONAL_TEMPLATE, TEMPLATE_DATA)

    parsed = parser.parse_data("sh010_anim_r02_v013.ma")
    assert parsed.version == 13
    assert parsed.custom_data == {"revision": 2}

    # Files saved without the optional key are still parsed
    parsed = parser.parse_data("sh010_anim_v013_blocking.ma")
    assert parsed.version == 13
    assert parsed.comment == "blocking"
    assert parsed.custom_data == {}


def test_parse_without_custom_keys():
    template = "{folder[name]}_{task[name]}_v{version:0>3}<_{comment}>.{ext}"
    parser = WorkfileDataParser(template, TEMPLATE_DATA)
    assert not parser.has_custom_keys

    parsed = parser.parse_data("sh010_anim_v013_blocking.ma")
    assert parsed.version == 13
    assert parsed.comment == "blocking"
    assert parsed.ext == ".ma"
    assert parsed.custom_data == {}


def test_last_workfile_version_ignores_custom_keys():
    filepaths = [
        "sh010_anim_r01_v001.ma",
        "sh010_anim_r01_v002.ma",
        # Higher revision with lower version must not win
        "sh010_anim_r09_v001.ma",
        "sh010_anim_r02_v003_blocking.ma",
        "unrelated_v010.ma",
    ]
    filepath, version = get_last_workfile_with_version_from_paths(
        filepaths, TEMPLATE, TEMPLATE_DATA, {".ma"}
    )
    assert version == 3
    assert filepath == "sh010_anim_r02_v003_blocking.ma"


def test_format_with_custom_data():
    data = dict(TEMPLATE_DATA)
    data.update({"version": 4, "ext": "ma"})
    data.update(
        resolve_workfile_custom_data(
            get_workfile_custom_keys(TEMPLATE, data)
        )
    )
    filename = StringTemplate.format_strict_template(TEMPLATE, data)
    assert filename == "sh010_anim_r01_v004.ma"
