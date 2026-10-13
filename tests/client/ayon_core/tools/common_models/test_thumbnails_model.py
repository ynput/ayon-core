"""Tests for thumbnails model."""

from __future__ import annotations

import os
import tempfile
import threading
from unittest.mock import Mock

import pytest

from ayon_core.tools.common_models import thumbnails


@pytest.fixture
def create_file(tmp_path):
    """Cached paths are used only if their files exist."""
    def _create_file():
        handle, path = tempfile.mkstemp(
            suffix=".png", dir=str(tmp_path)
        )
        os.close(handle)
        return path
    return _create_file


def test_task_without_thumbnail_uses_server_fallback(
    monkeypatch, create_file
):
    own_path = create_file()
    version_path = create_file()
    tasks = [
        {"id": "own", "thumbnailId": "thumbnail-id"},
        {"id": "fallback", "thumbnailId": None},
        {"id": "none", "thumbnailId": None},
    ]
    get_tasks = Mock(return_value=tasks)
    get_thumbnail_path = Mock(return_value=own_path)
    get_entity_thumbnail_path = Mock(
        side_effect=lambda _project, _type, task_id: (
            version_path if task_id == "fallback" else None
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
        "own": own_path,
        "fallback": version_path,
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


def test_not_found_entities_are_not_queried_again(monkeypatch):
    get_folders = Mock(return_value=[])
    monkeypatch.setattr(thumbnails.ayon_api, "get_folders", get_folders)
    monkeypatch.setattr(
        thumbnails, "get_entity_thumbnail_path", Mock(return_value=None)
    )

    model = thumbnails.ThumbnailsModel()
    for _ in range(2):
        assert model.get_thumbnail_paths("demo", "folder", {"removed"}) == {
            "removed": None
        }
    assert get_folders.call_count == 1


def test_failed_thumbnail_does_not_affect_others(monkeypatch):
    def _get_thumbnail_path(_project, _type, entity_id, _thumbnail_id):
        if entity_id == "broken":
            raise ValueError("Unknown mime type")
        return f"/{entity_id}.png"

    monkeypatch.setattr(
        thumbnails.ayon_api,
        "get_folders",
        Mock(return_value=[
            {"id": "broken", "thumbnailId": "thumbnail-1"},
            {"id": "valid", "thumbnailId": "thumbnail-2"},
        ]),
    )
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", _get_thumbnail_path)

    model = thumbnails.ThumbnailsModel()
    assert model.get_thumbnail_paths(
        "demo", "folder", {"broken", "valid"}
    ) == {
        "broken": None,
        "valid": "/valid.png",
    }


def test_failed_download_is_tried_again_when_cache_expires(monkeypatch):
    get_thumbnail_path = Mock(side_effect=[None, "/thumbnail.png"])
    monkeypatch.setattr(
        thumbnails.ayon_api,
        "get_folders",
        Mock(return_value=[{"id": "folder", "thumbnailId": "thumbnail-id"}]),
    )
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)

    model = thumbnails.ThumbnailsModel()
    args = ("demo", "folder", {"folder"})
    assert model.get_thumbnail_paths(*args) == {"folder": None}
    assert model.get_thumbnail_paths(*args) == {"folder": None}
    assert get_thumbnail_path.call_count == 1

    model._paths_cache.set_lifetime(0)
    assert model.get_thumbnail_paths(*args) == {"folder": "/thumbnail.png"}


def test_model_can_be_used_from_multiple_threads(monkeypatch):
    threads_count = 8
    ids_per_thread = 50
    barrier = threading.Barrier(threads_count)

    def _get_folders(_project_name, folder_ids, fields):
        return [
            {"id": folder_id, "thumbnailId": f"thumbnail-{folder_id}"}
            for folder_id in folder_ids
        ]

    monkeypatch.setattr(thumbnails.ayon_api, "get_folders", _get_folders)
    monkeypatch.setattr(
        thumbnails,
        "get_thumbnail_path",
        lambda _project, _type, entity_id, _thumbnail_id: f"/{entity_id}",
    )

    outputs = {}

    def _run(model, thread_idx):
        folder_ids = {
            f"{thread_idx}-{idx}" for idx in range(ids_per_thread)
        }
        barrier.wait()
        outputs[thread_idx] = model.get_thumbnail_paths(
            "demo", "folder", folder_ids
        )

    # Repeat to give the threads a chance to collide on a fresh model
    for _ in range(20):
        outputs.clear()
        model = thumbnails.ThumbnailsModel()
        threads = [
            threading.Thread(target=_run, args=(model, thread_idx))
            for thread_idx in range(threads_count)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(outputs) == threads_count
        for thread_idx, output in outputs.items():
            assert output == {
                f"{thread_idx}-{idx}": f"/{thread_idx}-{idx}"
                for idx in range(ids_per_thread)
            }


def test_removed_file_is_received_again(monkeypatch, create_file):
    """File can be removed by cleanup of thumbnails cache on disk."""
    paths = [create_file(), create_file()]
    get_thumbnail_path = Mock(side_effect=paths)
    monkeypatch.setattr(
        thumbnails.ayon_api,
        "get_folders",
        Mock(return_value=[{"id": "folder", "thumbnailId": "thumbnail-id"}]),
    )
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)

    model = thumbnails.ThumbnailsModel()
    args = ("demo", "folder", {"folder"})
    assert model.get_thumbnail_paths(*args) == {"folder": paths[0]}
    assert model.get_thumbnail_paths(*args) == {"folder": paths[0]}
    assert get_thumbnail_path.call_count == 1

    os.remove(paths[0])
    assert model.get_thumbnail_paths(*args) == {"folder": paths[1]}
    assert get_thumbnail_path.call_count == 2


def test_result_received_during_reset_is_not_cached(
    monkeypatch, create_file
):
    """Reset of the model while a request is running.

    Result of the request could be received before the change that the
    reset should pick up, so it must not fill the new caches.
    """
    model = thumbnails.ThumbnailsModel()
    reset_in_query = [True, True]

    def _get_folders(*_args, **_kwargs):
        if reset_in_query[0]:
            model.reset()
        return [{"id": "folder", "thumbnailId": "thumbnail-id"}]

    def _get_thumbnail_path(*_args):
        if reset_in_query[1]:
            model.reset()
        return create_file()

    get_folders = Mock(side_effect=_get_folders)
    get_thumbnail_path = Mock(side_effect=_get_thumbnail_path)
    monkeypatch.setattr(thumbnails.ayon_api, "get_folders", get_folders)
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)

    args = ("demo", "folder", {"folder"})
    # The result is returned, but nothing is cached
    assert model.get_thumbnail_paths(*args)["folder"] is not None
    reset_in_query[:] = [False, False]
    model.get_thumbnail_paths(*args)
    assert get_folders.call_count == 2
    assert get_thumbnail_path.call_count == 2

    # Without a reset the results are cached
    model.get_thumbnail_paths(*args)
    assert get_folders.call_count == 2
    assert get_thumbnail_path.call_count == 2
