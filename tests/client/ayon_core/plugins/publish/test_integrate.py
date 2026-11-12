"""Tests for representation filtering of the IntegrateAsset plugin."""
from __future__ import annotations

import pyblish.api
import pytest

from ayon_core.plugins.publish.integrate import IntegrateAsset


def _create_instance(representations) -> pyblish.api.Instance:
    context = pyblish.api.Context()
    instance = context.create_instance("test")
    instance.data["representations"] = representations
    return instance


@pytest.mark.parametrize("representations", [None, []])
def test_filter_representations_empty(representations) -> None:
    """Missing or empty representations return an empty list."""
    instance = _create_instance(representations)
    assert IntegrateAsset().filter_representations(instance) == []


def test_filter_representations_skips_delete_tag() -> None:
    """Representations tagged 'delete' are filtered out."""
    keep = {"name": "abc", "tags": []}
    instance = _create_instance([keep, {"name": "mov", "tags": ["delete"]}])
    assert IntegrateAsset().filter_representations(instance) == [keep]


@pytest.mark.parametrize(
    "representations",
    [{"name": "abc"}, "abc"],
)
def test_filter_representations_invalid_type(representations) -> None:
    """Non list representations raise a TypeError."""
    instance = _create_instance(representations)
    with pytest.raises(TypeError):
        IntegrateAsset().filter_representations(instance)
