"""Tests for workfile Subversion validation."""

import pytest

from ayon_core.pipeline.workfile.subversion_validation import (
    WorkfileSubversionError,
    is_valid_ayon_product_name,
    is_valid_workfile_subversion,
    require_valid_workfile_subversion,
    sanitize_workfile_subversion,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Smoke B - long", False),
        ("v2.1-beta", True),
        ("", True),
        ("Main_v2", True),
        ("bad!chars", False),
    ],
)
def test_is_valid_workfile_subversion(value, expected):
    assert is_valid_workfile_subversion(value) is expected


def test_sanitize_workfile_subversion():
    assert sanitize_workfile_subversion("Smoke B - long") == "Smoke_B_-_long"
    assert sanitize_workfile_subversion("v2.1-beta") == "v2.1-beta"
    assert sanitize_workfile_subversion("") == ""
    assert sanitize_workfile_subversion("bad!chars") == "bad_chars"


def test_require_valid_workfile_subversion_allows_empty():
    require_valid_workfile_subversion(None)
    require_valid_workfile_subversion("")
    require_valid_workfile_subversion("   ")


def test_require_valid_workfile_subversion_raises():
    with pytest.raises(WorkfileSubversionError):
        require_valid_workfile_subversion("Smoke B - long")


def test_is_valid_ayon_product_name():
    assert is_valid_ayon_product_name("Main_Smoke_B_-_long_Fx_workfile") is True
    assert is_valid_ayon_product_name("Main_Smoke B - long_Fx_workfile") is False
