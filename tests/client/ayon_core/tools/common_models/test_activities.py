"""Tests for fetching entity activity feeds."""

from __future__ import annotations

from typing import Any

import pytest

from ayon_core.tools.common_models import activities
from ayon_core.tools.common_models.activities import ActivitiesModel
from ayon_core.ui.data_models import (
    CommentModel,
    StatusChangeModel,
    VersionPublishModel,
)

ACTIVITIES = [
    {
        "activityId": "publish",
        "activityType": "version.publish",
        "activityData": {
            "origin": {"id": "version_id", "type": "version", "name": "v003"},
            "context": {"productName": "modelMain"},
        },
        "author": {"name": "roy"},
        "createdAt": "2026-10-01T10:00:00+00:00",
        "updatedAt": "2026-10-01T10:00:00+00:00",
    },
    {
        "activityId": "comment",
        "activityType": "comment",
        "activityData": {},
        "body": "Looks good",
        "author": {"name": "libor"},
        "createdAt": "2026-10-03T10:00:00+00:00",
        "updatedAt": "2026-10-03T10:00:00+00:00",
        "files": [],
    },
    {
        "activityId": "status",
        "activityType": "status.change",
        "activityData": {
            "origin": {"name": "v003"},
            "parents": [{"type": "product", "name": "modelMain"}],
            "oldValue": "In progress",
            "newValue": "Approved",
        },
        "author": {"name": "libor"},
        "createdAt": "2026-10-02T10:00:00+00:00",
        "updatedAt": "2026-10-02T10:00:00+00:00",
    },
]


@pytest.fixture
def fake_server(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"activities": [], "users": 0, "project": 0}

    def get_activities(project_name: str, **kwargs: Any):
        # 'limit' argument fails in ayon_api
        assert "limit" not in kwargs
        calls["activities"].append(kwargs)
        # The same activity is returned for each matching reference
        yield from ACTIVITIES + [ACTIVITIES[1]]

    def get_users(project_name: str, **kwargs: Any):
        calls["users"] += 1
        yield {"name": "roy", "attrib": {"fullName": "Roy Nieterau"}}
        yield {"name": "libor", "attrib": {"fullName": None}}

    def get_project(project_name: str):
        calls["project"] += 1
        return {
            "statuses": [
                {
                    "name": "Approved",
                    "shortName": "APP",
                    "icon": "task_alt",
                    "color": "#00f0b4",
                }
            ]
        }

    def get_versions(project_name: str, **kwargs: Any):
        calls["versions"] = kwargs
        yield {"id": "version_id", "status": "Approved", "thumbnailId": "t1"}

    monkeypatch.setattr(activities.ayon_api, "get_activities", get_activities)
    monkeypatch.setattr(activities.ayon_api, "get_versions", get_versions)
    monkeypatch.setattr(activities.ayon_api, "get_users", get_users)
    monkeypatch.setattr(activities.ayon_api, "get_project", get_project)
    return calls


def test_feed_is_deduplicated_and_newest_first(fake_server):
    feed = ActivitiesModel().get_activity_feed("demo", ["version_id"])

    assert [activity.activity_id for activity in feed.activities] == [
        "comment",
        "status",
        "publish",
    ]
    comment, status, publish = feed.activities
    assert isinstance(comment, CommentModel)
    assert comment.comment == "Looks good"
    # Falls back to the username when the full name is not filled
    assert comment.user_full_name == "libor"
    assert isinstance(status, StatusChangeModel)
    assert (status.old_status, status.new_status) == (
        "In progress",
        "Approved",
    )
    assert isinstance(publish, VersionPublishModel)
    assert publish.user_full_name == "Roy Nieterau"
    assert (publish.product, publish.version) == ("modelMain", "v003")
    # Current status and thumbnail come from the published version
    assert fake_server["versions"]["version_ids"] == {"version_id"}
    assert publish.status == "Approved"
    assert publish.thumbnail_key == "demo/version_id/t1"
    assert feed.statuses == [
        {
            "text": "Approved",
            "short_text": "APP",
            "icon": "task_alt",
            "color": "#00f0b4",
        }
    ]


def test_feed_is_limited_and_handles_missing_author(
    fake_server, monkeypatch: pytest.MonkeyPatch
):
    def get_activities(project_name: str, **kwargs: Any):
        for idx in range(10):
            yield {
                "activityId": str(idx),
                "activityType": "comment",
                "activityData": {},
                "body": "",
                "author": None,
                "createdAt": f"2026-10-0{idx}T10:00:00+00:00",
                "updatedAt": f"2026-10-0{idx}T10:00:00+00:00",
            }

    monkeypatch.setattr(activities.ayon_api, "get_activities", get_activities)
    feed = ActivitiesModel().get_activity_feed("demo", ["a"], limit=3)

    assert len(feed.activities) == 3
    assert feed.has_more
    assert feed.activities[0].user_name == "n/a"


def test_feed_queries_related_references(fake_server):
    ActivitiesModel().get_activity_feed("demo", ["task_id"])

    kwargs = fake_server["activities"][0]
    assert kwargs["entity_ids"] == {"task_id"}
    assert set(kwargs["reference_types"]) == {
        "origin",
        "mention",
        "relation",
    }


def test_project_data_is_cached_and_nothing_fetched_without_entities(
    fake_server,
):
    model = ActivitiesModel()

    assert model.get_activity_feed("demo", []).activities == []
    assert fake_server["activities"] == []

    model.get_activity_feed("demo", ["a"])
    model.get_activity_feed("demo", ["b"])
    assert len(fake_server["activities"]) == 2
    assert (fake_server["users"], fake_server["project"]) == (1, 1)
