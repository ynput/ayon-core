"""Tests for fetching activities of entities."""

from __future__ import annotations

import ast
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ayon_core.tools.common_models import activities
from ayon_core.tools.common_models.activities import (
    ActivitiesModel,
    ActivityAnnotationItem,
    ActivityFileItem,
    ActivityItem,
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
    calls: dict[str, Any] = {"activities": [], "other": []}

    def get_activities(project_name: str, **kwargs: Any):
        # 'limit' argument fails in ayon_api
        assert "limit" not in kwargs
        calls["activities"].append(kwargs)
        # The same activity is returned for each matching reference
        yield from ACTIVITIES + [ACTIVITIES[1]]

    def get_versions(project_name: str, **kwargs: Any):
        calls["versions"] = kwargs
        yield {"id": "version_id", "status": "Approved", "thumbnailId": "t1"}

    def unexpected_query(*args: Any, **kwargs: Any):
        calls["other"].append((args, kwargs))
        return []

    monkeypatch.setattr(activities.ayon_api, "get_activities", get_activities)
    monkeypatch.setattr(activities.ayon_api, "get_versions", get_versions)
    # Users and statuses are not a concern of the activities
    for name in ("get_users", "get_project", "get_rest_project"):
        monkeypatch.setattr(activities.ayon_api, name, unexpected_query)
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
    assert fake_server["other"] == []


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


def _is_frontend_module(module_name: str) -> bool:
    return module_name.split(".")[0] in {
        "qtpy",
        "PySide2",
        "PySide6",
    } or module_name.startswith("ayon_core.ui")


def test_backend_does_not_use_frontend_modules():
    imported = set()
    for node in ast.walk(ast.parse(inspect.getsource(activities))):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # Relative imports stay in the backend package
            if not node.level:
                imported.add(node.module)
    assert "ayon_api" in imported
    assert not [name for name in imported if _is_frontend_module(name)]

    used = {
        getattr(value, "__module__", None) or getattr(value, "__name__", "")
        for value in vars(activities).values()
    }
    assert not [name for name in used if _is_frontend_module(name)]


def test_backend_can_be_imported_without_qt():
    # Directory with the 'ayon_core' package
    client_dir = str(Path(inspect.getfile(activities)).parents[3])
    script = (
        "import sys\n"
        "from ayon_core.tools.common_models import activities\n"
        "print([\n"
        "    name for name in sys.modules\n"
        "    if name.split('.')[0] in ('qtpy', 'PySide2', 'PySide6')\n"
        "    or name.startswith('ayon_core.ui')\n"
        "])\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [client_dir, env.get("PYTHONPATH", "")]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    assert result.stdout.strip() == "[]"
