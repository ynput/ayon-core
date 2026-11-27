"""Tests for farm publish file collection."""

from __future__ import annotations

import pytest

from ayon_core.pipeline.farm.pyblish_functions import (
    _collect_expected_files_for_aov,
)


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (["renderMain.1001.exr"], ["renderMain.1001.exr"]),
        (["renderMain_1001.exr"], ["renderMain_1001.exr"]),
        (["sh010.exr"], "sh010.exr"),
        (["1.exr"], "1.exr"),
        (["renderMain.exr"], "renderMain.exr"),
        (
            ["renderMain.1002.exr", "renderMain.1001.exr"],
            ["renderMain.1001.exr", "renderMain.1002.exr"],
        ),
    ],
)
def test_collect_expected_files_for_aov(
    files: list[str],
    expected: list[str] | str,
) -> None:
    """Keep frame sequences as lists and non-sequence files as strings."""
    assert _collect_expected_files_for_aov(files) == expected


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ([], "Only one image sequence type is expected"),
        (
            ["beauty.exr", "depth.exr"],
            "Found multiple non related files",
        ),
        (
            [
                "beauty.1001.exr",
                "beauty.1002.exr",
                "depth.1001.exr",
                "depth.1002.exr",
            ],
            "Only one image sequence type is expected",
        ),
    ],
)
def test_collect_expected_files_for_aov_rejects_invalid_files(
    files: list[str],
    message: str,
) -> None:
    """Reject unrelated files and multiple sequences as before."""
    with pytest.raises(ValueError, match=message):
        _collect_expected_files_for_aov(files)
