"""Tests for fetching entity activity feeds."""

from __future__ import annotations

import json
from typing import Any

import pytest

from ayon_core.tools.common_models import activities
from ayon_core.tools.common_models.activities import (
    ActivitiesModel,
    ActivityAnnotationItem,
    ActivityFileItem,
    ActivityItem,
)
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
        "activityData": {
            "category": "Feedback",
            "annotations": [
                {
                    "id": "annotation_id",
                    "range": [1001, 1001],
                    "composite": "file_id",
                    "transparent": "transparent_id",
                }
            ],
        },
        "body": "Looks good",
        "author": {"name": "libor"},
        "createdAt": "2026-10-03T10:00:00+00:00",
        "updatedAt": "2026-10-03T11:00:00+00:00",
        "files": [{"id": "file_id", "mime": "image/png"}],
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


def test_items_are_deduplicated_and_newest_first(fake_server):
    items = ActivitiesModel().get_activity_items("demo", ["version_id"])

    assert [item.activity_id for item in items] == [
        "comment",
        "status",
        "publish",
    ]
    comment, status, publish = items
    assert comment == ActivityItem(
        activity_id="comment",
        activity_type="comment",
        author="libor",
        body="Looks good",
        created_at="2026-10-03T10:00:00+00:00",
        updated_at="2026-10-03T11:00:00+00:00",
        category="Feedback",
        files=[ActivityFileItem("file_id", "image/png")],
        annotations=[
            ActivityAnnotationItem(
                "annotation_id", [1001, 1001], "file_id", "transparent_id"
            )
        ],
    )
    assert status.activity_type == "status.change"
    assert (status.product_name, status.version_name) == (
        "modelMain",
        "v003",
    )
    assert (status.old_status, status.new_status) == (
        "In progress",
        "Approved",
    )
    assert publish.activity_type == "version.publish"
    assert publish.author == "roy"
    assert (publish.product_name, publish.version_name) == (
        "modelMain",
        "v003",
    )
    # Current status and thumbnail come from the published version
    assert fake_server["versions"]["version_ids"] == {"version_id"}
    assert publish.version_id == "version_id"
    assert publish.version_status == "Approved"
    assert publish.thumbnail_id == "t1"
    # Users and statuses are not a concern of the activities
    assert (fake_server["users"], fake_server["project"]) == (0, 0)


def test_items_are_limited_and_handle_missing_author(
    fake_server, monkeypatch: pytest.MonkeyPatch
):
    def get_activities(project_name: str, **kwargs: Any):
        # 'limit' argument fails in ayon_api
        assert "limit" not in kwargs
        for idx in range(10):
            yield {
                "activityId": str(idx),
                "activityType": "comment",
                "activityData": None,
                "body": "",
                "author": None,
                "createdAt": f"2026-10-0{idx}T10:00:00+00:00",
                "updatedAt": f"2026-10-0{idx}T10:00:00+00:00",
            }

    monkeypatch.setattr(activities.ayon_api, "get_activities", get_activities)
    items = ActivitiesModel().get_activity_items("demo", {"a"}, limit=3)

    assert [item.activity_id for item in items] == ["2", "1", "0"]
    assert items[0].author is None
    # No version was published, so there is nothing to ask for
    assert "versions" not in fake_server


def test_items_of_removed_versions_have_no_status(
    fake_server, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        activities.ayon_api, "get_versions", lambda *_, **__: iter(())
    )
    publish = ActivitiesModel().get_activity_items("demo", ["a"])[-1]

    assert publish.version_id == "version_id"
    assert (publish.version_status, publish.thumbnail_id) == (None, None)


def test_items_query_related_references(fake_server):
    ActivitiesModel().get_activity_items("demo", ["task_id"])

    kwargs = fake_server["activities"][0]
    assert kwargs["entity_ids"] == {"task_id"}
    assert set(kwargs["activity_types"]) == {
        "comment",
        "version.publish",
        "status.change",
    }
    assert set(kwargs["reference_types"]) == {
        "origin",
        "mention",
        "relation",
    }


def test_nothing_is_fetched_without_project_or_entities(fake_server):
    model = ActivitiesModel()

    assert model.get_activity_items("demo", []) == []
    assert model.get_activity_items("", ["a"]) == []
    assert fake_server["activities"] == []


def test_items_survive_a_json_round_trip(fake_server):
    items = ActivitiesModel().get_activity_items("demo", ["version_id"])

    data = json.loads(json.dumps([item.to_data() for item in items]))

    assert [ActivityItem.from_data(item_data) for item_data in data] == items
    # Conversion does not change the data it was given
    assert data == [item.to_data() for item in items]


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
