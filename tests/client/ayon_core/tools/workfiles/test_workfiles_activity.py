"""Tests for the activity data provided by the Workfiles controller."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ayon_api
import pytest

from ayon_core.tools.common_models import thumbnails
from ayon_core.tools.workfiles.abstract import AbstractWorkfilesFrontend
from ayon_core.tools.workfiles.control import BaseWorkfileController


@pytest.fixture
def fake_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> dict[str, Any]:
    # Cached thumbnail paths are used only if their files exist
    thumbnail_path = tmp_path / "thumbnail.jpg"
    thumbnail_path.touch()
    calls: dict[str, Any] = {
        "activities": [],
        "users": 0,
        "project": 0,
        "thumbnails": [],
        "thumbnail_path": str(thumbnail_path),
    }

    def get_activities(project_name: str, **kwargs: Any):
        calls["activities"].append((project_name, kwargs["entity_ids"]))
        yield {
            "activityId": "comment",
            "activityType": "comment",
            "activityData": {},
            "body": "Looks good",
            "author": {"name": "libor"},
            "createdAt": "2026-10-03T10:00:00+00:00",
            "updatedAt": "2026-10-03T10:00:00+00:00",
        }

    def get_users(project_name: str, **kwargs: Any):
        calls["users"] += 1
        yield {
            "name": "libor",
            "active": True,
            "attrib": {
                "fullName": "Libor Batek",
                "email": None,
                "avatarUrl": None,
            },
        }

    def get_rest_project(project_name: str):
        calls["project"] += 1
        return {
            "name": project_name,
            "statuses": [
                {
                    "name": "Approved",
                    "shortName": "APP",
                    "icon": "task_alt",
                    "color": "#00f0b4",
                    "state": "done",
                }
            ],
        }

    def get_thumbnail_path(*args: str) -> str:
        calls["thumbnails"].append(args)
        return calls["thumbnail_path"]

    monkeypatch.setattr(ayon_api, "get_activities", get_activities)
    monkeypatch.setattr(ayon_api, "get_users", get_users)
    monkeypatch.setattr(ayon_api, "get_rest_project", get_rest_project)
    monkeypatch.setattr(thumbnails, "get_thumbnail_path", get_thumbnail_path)
    return calls


def test_activity_data_comes_from_the_backend_models(fake_server):
    controller: AbstractWorkfilesFrontend = BaseWorkfileController()

    items = controller.get_activity_items("demo", ["task_id"])
    assert [item.activity_id for item in items] == ["comment"]
    assert fake_server["activities"] == [("demo", {"task_id"})]

    # Statuses and users are cached by the models of the controller
    for _ in range(2):
        statuses = controller.get_project_status_items("demo")
        users = controller.get_user_items("demo")
    assert [status.name for status in statuses] == ["Approved"]
    assert [(user.username, user.full_name) for user in users] == [
        ("libor", "Libor Batek")
    ]
    assert (fake_server["users"], fake_server["project"]) == (1, 1)


def test_version_thumbnail_comes_from_the_thumbnails_model(fake_server):
    controller: AbstractWorkfilesFrontend = BaseWorkfileController()

    for _ in range(2):
        path = controller.get_version_thumbnail_path("demo", "v1", "t1")
        assert path == fake_server["thumbnail_path"]
    assert fake_server["thumbnails"] == [("demo", "version", "v1", "t1")]

    assert controller.get_version_thumbnail_path("demo", "v1", "") is None
    assert len(fake_server["thumbnails"]) == 1
