"""Tests for server fallback of thumbnails in thumbnails model."""

from __future__ import annotations

from unittest.mock import Mock

from ayon_core.tools.common_models import thumbnails


def test_task_without_thumbnail_uses_server_fallback(monkeypatch):
    tasks = [
        {"id": "own", "thumbnailId": "thumbnail-id"},
        {"id": "fallback", "thumbnailId": None},
        {"id": "none", "thumbnailId": None},
    ]
    get_tasks = Mock(return_value=tasks)
    get_thumbnail_path = Mock(return_value="/own.png")
    get_entity_thumbnail_path = Mock(
        side_effect=lambda _project, _type, task_id: (
            "/version.png" if task_id == "fallback" else None
        )
    )
    monkeypatch.setattr(thumbnails.ayon_api, "get_tasks", get_tasks)
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)
    monkeypatch.setattr(
        thumbnails, "get_entity_thumbnail_path", get_entity_thumbnail_path
    )

    model = thumbnails.ThumbnailsModel()
    task_ids = {"own", "fallback", "none"}
    expected = {
        "own": "/own.png",
        "fallback": "/version.png",
        "none": None,
    }
    assert model.get_thumbnail_paths("demo", "task", task_ids) == expected
    # Task with own thumbnail does not need the fallback request
    assert get_entity_thumbnail_path.call_count == 2

    # Nothing is requested again until the cache expires
    assert model.get_thumbnail_paths("demo", "task", task_ids) == expected
    assert get_tasks.call_count == 1
    assert get_thumbnail_path.call_count == 1
    assert get_entity_thumbnail_path.call_count == 2


def test_fallback_can_be_disabled(monkeypatch):
    get_entity_thumbnail_path = Mock(return_value="/resolved.png")
    monkeypatch.setattr(
        thumbnails.ayon_api,
        "get_folders",
        Mock(return_value=[{"id": "folder", "thumbnailId": None}]),
    )
    monkeypatch.setattr(
        thumbnails, "get_entity_thumbnail_path", get_entity_thumbnail_path
    )

    model = thumbnails.ThumbnailsModel()
    assert model.get_thumbnail_paths(
        "demo", "folder", {"folder"}, use_server_fallback=False
    ) == {"folder": None}
    get_entity_thumbnail_path.assert_not_called()

    assert model.get_thumbnail_paths("demo", "folder", {"folder"}) == {
        "folder": "/resolved.png"
    }
    get_entity_thumbnail_path.assert_called_once_with(
        "demo", "folder", "folder"
    )
