"""Tests for publish library helpers."""

from unittest.mock import call, patch
import pytest

from ayon_core.pipeline.publish.lib import get_file_collections


def test_get_file_collections_assembles_sequence() -> None:
    """Sequence files are returned as one collection."""
    files = ["render.0001.exr", "render.0002.exr"]

    collections, remainders = get_file_collections(files)

    assert len(collections) == 1
    assert list(collections[0].indexes) == [1, 2]
    assert not remainders


def test_get_file_collections_assembles_single_file() -> None:
    """A single file is assembled with a minimum collection size of one."""
    files = ["render.0001.exr"]

    collections, remainders = get_file_collections(files)

    assert len(collections) == 1
    assert list(collections[0].indexes) == [1]
    assert not remainders


def test_get_file_collections_retries_default_pattern() -> None:
    """Default clique parsing is used when the custom pattern finds nothing."""
    files = ["render.0001.exr", "render.0002.exr"]
    custom_result = ([], files)
    default_result = ([object()], [])

    with patch(
        "ayon_core.pipeline.publish.lib.clique.assemble",
        side_effect=[custom_result, default_result],
    ) as assemble:
        collections, remainders = get_file_collections(files)

    assert (collections, remainders) == default_result
    assert assemble.call_args_list == [
        call(
            files,
            minimum_items=2,
            assume_padded_when_ambiguous=True,
            patterns=["(?P<index>(?P<padding>0*)\\d+)\\.\\D+\\d?$"],
        ),
        call(
            files,
            minimum_items=2,
            assume_padded_when_ambiguous=True,
        ),
    ]


@pytest.mark.parametrize(
    ("files", "expected_indexes", "expected_remainders"),
    [
        pytest.param(
            ["sh010.exr"],
            [],
            ["sh010.exr"],
            id="single-shot-number-is-not-a-frame",
        ),
        pytest.param(
            ["sh010.exr", "sh011.exr"],
            [[10, 11]],
            [],
            id="shot-numbers-form-a-sequence",
        ),
        pytest.param(
            ["frame1001.exr", "frame1002.exr"],
            [[1001, 1002]],
            [],
            id="frame-prefix-without-separator",
        ),
        pytest.param(
            ["frame_1001.exr", "frame_1002.exr"],
            [[1001, 1002]],
            [],
            id="frame-prefix-with-underscore",
        ),
        pytest.param(
            ["frame.1001.exr", "frame.1002.exr"],
            [[1001, 1002]],
            [],
            id="frame-prefix-with-dot",
        ),
        pytest.param(
            ["1000.exr", "1002.exr"],
            [[1000, 1002]],
            [],
            id="frame-numbers-only",
        ),
        pytest.param(
            ["1.exr"],
            [[1]],
            [],
            id="single-digit-frame",
        ),
        pytest.param(
            ["1.exr", "10.exr"],
            [[1, 10]],
            [],
            id="unpadded-frames-form-a-sequence",
        ),
    ],
)
def test_get_file_collections_specific_patterns(
    files: list[str],
    expected_indexes: list[list[int]],
    expected_remainders: list[str],
) -> None:
    """Test for specific patterns.

    Data::
        sh010.exr (should be disallowed)
        sh010.exr + sh011.exr (should be allowed)
        frame1001.exr + frame1002.exr
        frame_1001.exr + frame_1002.exr
        frame.1001.exr + frame.1002.exr
        1000.exr + 1002.exr (frames only)
        1.exr (single frame; digit only)
        1.exr + 10.exr (no padding)
    """
    collections, remainders = get_file_collections(files)

    assert [list(collection.indexes) for collection in collections] == (
        expected_indexes
    )
    assert remainders == expected_remainders
