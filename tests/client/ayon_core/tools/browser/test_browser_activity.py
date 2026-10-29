"""Tests for the activity data provided by the Browser controllers."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import Mock

import ayon_api
import pytest

from ayon_core.tools.browser.control import BrowserController
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)


@pytest.fixture(autouse=True)
def _mock_sitesync_addon(monkeypatch: pytest.MonkeyPatch) -> None:
    # The Site Sync column provider looks up the addon on creation.
    addon_manager = Mock()
    addon_manager.get.return_value = None
    monkeypatch.setattr(
        "ayon_core.tools.browser.sitesync_columns.AddonsManager",
        lambda: addon_manager,
    )


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"activities": [], "users": 0, "project": 0}

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

    monkeypatch.setattr(ayon_api, "get_activities", get_activities)
    monkeypatch.setattr(ayon_api, "get_users", get_users)
    monkeypatch.setattr(ayon_api, "get_rest_project", get_rest_project)
    return calls


def test_activity_data_comes_from_the_backend_models(fake_server):
    backend = BrowserController()
    controller = BrowserWidgetController(backend)

    items = controller.get_activity_items("demo", ["version_id"])
    assert [item.activity_id for item in items] == ["comment"]
    assert fake_server["activities"] == [("demo", {"version_id"})]

    # Statuses and users are cached by the models of the controller
    for _ in range(2):
        statuses = controller.get_project_status_items("demo")
        users = controller.get_user_items("demo")
    assert [status.name for status in statuses] == ["Approved"]
    assert [(user.username, user.full_name) for user in users] == [
        ("libor", "Libor Batek")
    ]
    assert (fake_server["users"], fake_server["project"]) == (1, 1)
    assert users == backend.get_user_items("demo")


def test_version_thumbnail_comes_from_the_thumbnails_model(
    monkeypatch: pytest.MonkeyPatch,
):
    calls = []

    def get_thumbnail_path(
        project_name: str, entity_type: str, entity_id: str, thumbnail_id: str
    ):
        calls.append((project_name, entity_type, entity_id, thumbnail_id))
        return None if thumbnail_id == "missing" else "/cache/thumbnail.jpg"

    # The cache of thumbnails shared by all tools and processes
    monkeypatch.setattr(
        "ayon_core.tools.common_models.thumbnails.get_thumbnail_path",
        get_thumbnail_path,
    )
    controller = BrowserWidgetController(BrowserController())

    path = controller.get_version_thumbnail_path("demo", "v1", "t1")
    assert path == "/cache/thumbnail.jpg"
    assert controller.get_version_thumbnail_path("demo", "v1", "") is None
    assert calls == [("demo", "version", "v1", "t1")]

    assert (
        controller.get_version_thumbnail_path("demo", "v2", "missing")
        is None
    )


def test_thumbnail_loader_asks_the_controller(tmp_path):
    from ayon_core.tools.browser.ui._browser_thumbnails import (
        _thumbnail_loader,
    )

    image_path = tmp_path / "thumbnail.png"
    image_path.write_bytes(b"image")

    class Controller:
        calls = []

        def get_version_thumbnail_path(self, *args):
            self.calls.append(args)
            return None if args[2] == "missing" else str(image_path)

    controller = Controller()
    # A key that is not in the image cache of the machine yet
    project_name = f"demo_{uuid.uuid4().hex}"
    key = f"{project_name}/v1/t1"

    cached_path = _thumbnail_loader(key, controller)
    assert cached_path
    with open(cached_path, "rb") as stream:
        assert stream.read() == b"image"
    # The image cache serves the key from now on
    assert _thumbnail_loader(key, controller) == cached_path
    assert controller.calls == [(project_name, "v1", "t1")]

    assert _thumbnail_loader(f"{project_name}/v1/missing", controller) == ""


def test_users_are_queried_once_for_table_and_activity(fake_server):
    controller = BrowserWidgetController(BrowserController())

    assert controller._get_user_full_names("demo") == {
        "libor": "Libor Batek"
    }
    user_items = controller.get_user_items("demo")
    assert [user_item.username for user_item in user_items] == ["libor"]
    assert fake_server["users"] == 1
