"""Tests for publish library helpers."""

from unittest.mock import call, patch

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
