"""Tests for workfile Subversion validation."""

import pytest

from ayon_core.pipeline.workfile.subversion_validation import (
    WorkfileSubversionError,
    build_invalid_product_name_error,
    find_first_invalid_product_name_for_publish,
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


def test_build_invalid_product_name_error():
    message, formatting_data = build_invalid_product_name_error(
        "Main_Smoke B - long_Fx_workfile",
        "Smoke B - long",
    )
    assert "Main_Smoke B - long_Fx_workfile" in message
    assert "Smoke B - long" in message
    assert formatting_data["sanitized"] == "Smoke_B_-_long"
    assert formatting_data["subversion"] == "Smoke B - long"


def test_find_first_invalid_product_name_for_publish():
    class FakeInstance:
        def __init__(self, data):
            self.data = data

    class FakeContext(list):
        pass

    context = FakeContext(
        [
            FakeInstance(
                {
                    "folderEntity": {"id": "folder-1"},
                    "productType": "workfile",
                    "productName": "Main_Smoke B - long_Fx_workfile",
                    "workfileSubversion": "Smoke B - long",
                }
            ),
        ]
    )
    result = find_first_invalid_product_name_for_publish(context)
    assert result is not None
    instance, product_name, subversion = result
    assert product_name == "Main_Smoke B - long_Fx_workfile"
    assert subversion == "Smoke B - long"
