"""Tests for getting thumbnail paths of entities."""

from __future__ import annotations

import pytest

from ayon_core.tools.common_models import thumbnails
from ayon_core.tools.common_models.thumbnails import ThumbnailsModel


def test_thumbnail_with_known_id_does_not_query_the_entity(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    def get_thumbnail_path(*args: str) -> str:
        calls.append(args)
        return "/cache/thumbnail.jpg"

    def get_versions(*args, **kwargs):
        raise AssertionError("Thumbnail id is known")

    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)
    monkeypatch.setattr(thumbnails.ayon_api, "get_versions", get_versions)
    model = ThumbnailsModel()

    for _ in range(2):
        path = model.get_thumbnail_path("demo", "version", "v1", "t1")
        assert path == "/cache/thumbnail.jpg"
    # The path is cached by the thumbnail id
    assert calls == [("demo", "version", "v1", "t1")]

    assert model.get_thumbnail_path("demo", "version", "v1", None) is None
    assert model.get_thumbnail_path(None, "version", "v1", "t1") is None
    assert len(calls) == 1
