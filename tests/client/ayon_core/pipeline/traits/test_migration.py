"""Tests for upgrade of stored trait data."""
from __future__ import annotations

import json
from fractions import Fraction
from typing import Any

import pytest
from ayon_core.pipeline.traits import FileLocations, FrameRanged, Handles
from ayon_core.pipeline.traits.migration import (
    upgrade_representation_traits,
    upgrade_traits_data,
)

FRAME_RANGED_V1 = "ayon.time.FrameRanged.v1"
FILE_LOCATIONS_V1 = "ayon.content.FileLocations.v1"


def _v1_traits() -> dict[str, Any]:
    return {
        FRAME_RANGED_V1: {
            "frame_start": 1001,
            "frame_end": 1010,
            "frames_per_second": "24000/1001",
        },
        FILE_LOCATIONS_V1: {
            "file_paths": [
                {"file_path": "/a/b.1001.exr", "file_size": 10},
            ],
        },
        Handles.id: {"frame_start_handle": 5, "frame_end_handle": 5},
        "unknown.addon.Foo.v3": {"value": 1},
    }


def test_upgrade_traits_data() -> None:
    """Test old trait versions are upgraded, other data are kept."""
    traits = _v1_traits()
    result = upgrade_traits_data(traits)

    assert result.changed
    assert result.upgraded == {
        FRAME_RANGED_V1: FrameRanged.id,
        FILE_LOCATIONS_V1: FileLocations.id,
    }
    assert not result.skipped
    assert set(result.traits) == {
        FrameRanged.id,
        FileLocations.id,
        Handles.id,
        "unknown.addon.Foo.v3",
    }
    assert result.traits[Handles.id] == traits[Handles.id]
    assert result.traits["unknown.addon.Foo.v3"] == {"value": 1}

    frame_ranged = FrameRanged.from_dict(result.traits[FrameRanged.id])
    assert frame_ranged.frame_rate == Fraction(24000, 1001)
    file_path = result.traits[FileLocations.id]["file_paths"][0]["file_path"]
    assert file_path == "/a/b.1001.exr"
    # Stored data must be JSON serializable
    json.dumps(result.traits)

    # Server merges patched traits, old ids are removed by None
    patch_data = result.get_patch_data()
    assert patch_data[FRAME_RANGED_V1] is None
    assert patch_data[FILE_LOCATIONS_V1] is None
    assert set(patch_data) == {
        FRAME_RANGED_V1, FILE_LOCATIONS_V1,
        FrameRanged.id, FileLocations.id,
    }


def test_current_traits_are_unchanged() -> None:
    """Test data of current trait versions are not changed."""
    traits = {
        Handles.id: {"frame_start_handle": 5, "frame_end_handle": 5},
    }
    result = upgrade_traits_data(traits)
    assert not result.changed
    assert result.traits == traits
    assert result.get_patch_data() == {}


def test_existing_newer_version_is_kept() -> None:
    """Test old data are not upgraded over existing newer data."""
    newer = {"frame_start": 1, "frame_end": 2}
    traits = {
        FRAME_RANGED_V1: {"frame_start": 1001, "frame_end": 1010},
        FrameRanged.id: newer,
    }
    result = upgrade_traits_data(traits)
    assert not result.changed
    assert FRAME_RANGED_V1 in result.skipped
    assert result.traits == traits


class _FakeSession:
    commits: list[list[tuple]] = []

    def __init__(self) -> None:
        self._operations: list[tuple] = []

    def update_entity(self, *args: Any) -> None:
        self._operations.append(args)

    def commit(self) -> None:
        _FakeSession.commits.append(self._operations)
        self._operations = []


@pytest.mark.parametrize("dry_run", [False, True])
def test_upgrade_representation_traits(
    monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    """Test representations with old traits are patched on the server."""
    import ayon_api  # noqa: PLC0415
    from ayon_api import operations  # noqa: PLC0415

    repre_entities = [
        {"id": "old", "traits": json.dumps(_v1_traits())},
        {"id": "current", "traits": {
            Handles.id: {"frame_start_handle": 0, "frame_end_handle": 0},
        }},
        {"id": "legacy", "traits": None},
    ]
    received = {}

    def get_representations(project_name: str, **kwargs: Any) -> list:
        received.update(kwargs, project_name=project_name)
        return repre_entities

    _FakeSession.commits = []
    monkeypatch.setattr(ayon_api, "get_representations", get_representations)
    monkeypatch.setattr(operations, "OperationsSession", _FakeSession)

    report = upgrade_representation_traits(
        "test", version_ids=["v1"], dry_run=dry_run)

    assert received["project_name"] == "test"
    assert received["version_ids"] == {"v1"}
    assert report.checked == 2
    assert report.updated == ["old"]
    assert report.upgraded_traits == {
        f"{FRAME_RANGED_V1} -> {FrameRanged.id}": 1,
        f"{FILE_LOCATIONS_V1} -> {FileLocations.id}": 1,
    }
    assert "1 of 2" in report.summary()
    if dry_run:
        assert _FakeSession.commits == []
        return

    assert len(_FakeSession.commits) == 1
    (operation,) = _FakeSession.commits[0]
    project_name, entity_type, entity_id, update_data = operation
    assert (project_name, entity_type, entity_id) == (
        "test", "representation", "old")
    assert update_data["traits"][FRAME_RANGED_V1] is None
    assert FrameRanged.id in update_data["traits"]
