"""Tests for ayon_core.ui.components.views.data_models."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ayon_core.ui.components.views.data_models import (
    DEFAULT_ACCESS_LEVEL,
    ColumnState,
    FilterDef,
    GroupingDef,
    Scope,
    View,
    ViewSettings,
    Visibility,
)

FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "view_payload_versions.json"
)


def _load_fixture() -> dict:
    """Load the canonical versions payload fixture."""
    with FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# ColumnState
# ---------------------------------------------------------------------------


def test_column_state_from_payload_minimal() -> None:
    """Defaults are applied for missing optional fields."""
    cs = ColumnState.from_payload({"name": "status"})
    assert cs.name == "status"
    assert cs.visible is True
    assert cs.pinned is False
    assert cs.width is None


def test_column_state_roundtrip_preserves_width() -> None:
    """Width is preserved through roundtrip and dropped when ``None``."""
    cs = ColumnState(name="thumbnail", visible=True, pinned=True, width=80)
    payload = cs.to_payload()
    assert payload["width"] == 80
    rt = ColumnState.from_payload(payload)
    assert rt == cs

    no_width = ColumnState(name="status", visible=False)
    assert "width" not in no_width.to_payload()


def test_column_state_invalid_width_becomes_none() -> None:
    """Non-integer width values are coerced to ``None``."""
    cs = ColumnState.from_payload({"name": "x", "width": "abc"})
    assert cs.width is None


# ---------------------------------------------------------------------------
# FilterDef / GroupingDef
# ---------------------------------------------------------------------------


def test_filter_def_empty_when_no_payload() -> None:
    """``None`` payload yields an empty filter."""
    fd = FilterDef.from_payload(None)
    assert fd.is_empty()
    assert fd.operator == "and"


def test_filter_def_unknown_operator_falls_back_to_and() -> None:
    """An unknown operator falls back to ``and`` rather than crashing."""
    fd = FilterDef.from_payload({"operator": "xor", "conditions": []})
    assert fd.operator == "and"


def test_filter_def_conditions_are_copied() -> None:
    """Filter conditions are deep-copied to prevent aliasing bugs."""
    original = [{"key": "status", "values": ["Approved"]}]
    fd = FilterDef.from_payload({"operator": "or", "conditions": original})
    fd.conditions[0]["values"].append("On hold")
    assert original[0]["values"] == ["Approved"]


def test_grouping_def_is_empty_when_no_group_by() -> None:
    """``group_by=None`` reports as empty."""
    assert GroupingDef().is_empty()
    assert not GroupingDef(group_by="status").is_empty()


# ---------------------------------------------------------------------------
# ViewSettings
# ---------------------------------------------------------------------------


def test_view_settings_from_empty_payload() -> None:
    """Empty / ``None`` payload yields default settings."""
    vs = ViewSettings.from_payload(None)
    assert vs.columns == []
    assert vs.sort_by is None
    assert vs.sort_desc is False
    assert vs.row_height == 32
    assert vs.grouping.is_empty()
    assert vs.filter.is_empty()
    assert vs.extra == {}


def test_view_settings_preserves_unknown_keys_in_extra() -> None:
    """Settings keys that are not first-class are stashed in ``extra``."""
    payload = {
        "columns": [],
        "sortBy": "version",
        "sortDesc": True,
        "showProducts": True,
        "gridHeight": 220,
        "featuredVersionOrder": "latest",
        "slicerType": "folders",
    }
    vs = ViewSettings.from_payload(payload)
    assert vs.sort_by == "version"
    assert vs.sort_desc is True
    assert vs.extra == {
        "showProducts": True,
        "gridHeight": 220,
        "featuredVersionOrder": "latest",
        "slicerType": "folders",
    }


def test_view_settings_extra_known_keys_dont_override_first_class() -> None:
    """Sneaking a known key into ``extra`` cannot override the real field."""
    vs = ViewSettings(sort_by="version", extra={"sortBy": "name"})
    out = vs.to_payload()
    assert out["sortBy"] == "version"


# ---------------------------------------------------------------------------
# View (full fixture roundtrip)
# ---------------------------------------------------------------------------


def test_view_from_payload_parses_known_fields() -> None:
    """Top-level fields are mapped from camelCase to snake_case."""
    payload = _load_fixture()
    view = View.from_payload(payload)
    assert view.id == "view_abc123"
    assert view.label == "My Approved Versions"
    assert view.view_type == "versions"
    assert view.owner == "alice"
    assert view.scope == Scope.PROJECT
    assert view.visibility == Visibility.SHARED
    assert view.working is False
    assert view.position == 2
    assert view.access_level == 30
    assert view.access == {
        "users": ["alice", "bob"],
        "groups": ["leads"],
    }


def test_view_payload_roundtrip_is_lossless() -> None:
    """Loading and re-serialising the fixture preserves every key."""
    payload = _load_fixture()
    view = View.from_payload(payload)
    out = view.to_payload()

    # Unknown top-level keys (metadata) survive in view.extra.
    assert out["metadata"] == payload["metadata"]

    # Unknown settings keys survive in settings.extra.
    settings_out = out["settings"]
    for key in (
        "showProducts",
        "gridHeight",
        "featuredVersionOrder",
        "slicerType",
    ):
        assert settings_out[key] == payload["settings"][key]

    # Known first-class fields roundtrip identically.
    assert settings_out["sortBy"] == "version"
    assert settings_out["sortDesc"] is True
    assert settings_out["rowHeight"] == 48
    assert settings_out["groupBy"] == "status"
    assert settings_out["groupSortByDesc"] is False
    assert settings_out["showEmptyGroups"] is True

    # Filter roundtrip.
    filt = settings_out["filter"]
    assert filt["operator"] == "and"
    assert len(filt["conditions"]) == 1
    assert filt["conditions"][0]["values"] == ["Approved", "Pending review"]

    # Columns: order, visibility, pinned, width all preserved.
    payload_cols = payload["settings"]["columns"]
    out_cols = settings_out["columns"]
    assert len(out_cols) == len(payload_cols)
    for src, dst in zip(payload_cols, out_cols):
        assert src["name"] == dst["name"]
        assert src["visible"] == dst["visible"]
        assert src["pinned"] == dst["pinned"]
        if "width" in src:
            assert src["width"] == dst["width"]


def test_view_double_roundtrip_is_stable() -> None:
    """Two roundtrips produce identical payloads."""
    payload = _load_fixture()
    view_a = View.from_payload(payload)
    view_b = View.from_payload(view_a.to_payload())
    assert view_a.to_payload() == view_b.to_payload()


def test_view_from_payload_uses_defaults_for_missing_keys() -> None:
    """Optional top-level fields fall back to sensible defaults."""
    view = View.from_payload({"id": "x", "label": "L", "viewType": "t"})
    assert view.owner == ""
    assert view.scope == Scope.PROJECT
    assert view.visibility == Visibility.PRIVATE
    assert view.access_level == DEFAULT_ACCESS_LEVEL
    assert view.access == {}


def test_view_from_payload_rejects_non_dict() -> None:
    """Passing a non-dict payload raises TypeError."""
    with pytest.raises(TypeError):
        View.from_payload([])  # type: ignore[arg-type]


def test_view_from_payload_handles_unknown_visibility() -> None:
    """Unknown visibility values fall back to PRIVATE."""
    payload = _load_fixture()
    payload["visibility"] = "highly_classified"
    view = View.from_payload(payload)
    assert view.visibility == Visibility.PRIVATE


# ---------------------------------------------------------------------------
# View.can_edit access logic
# ---------------------------------------------------------------------------


def test_private_view_only_editable_by_owner() -> None:
    """A private view is editable only by its owner."""
    v = View(
        id="v1",
        label="Mine",
        view_type="versions",
        owner="alice",
        visibility=Visibility.PRIVATE,
    )
    assert v.can_edit("alice") is True
    assert v.can_edit("bob") is False
    assert v.can_edit("") is False


def test_shared_view_editable_when_access_level_sufficient() -> None:
    """A shared view requires an access level >= the view's threshold."""
    v = View(
        id="v2",
        label="Team",
        view_type="versions",
        owner="alice",
        visibility=Visibility.SHARED,
        access_level=30,
    )
    assert v.can_edit("bob", user_access_level=30) is True
    assert v.can_edit("bob", user_access_level=29) is False
    # Default user_access_level=50 means callers without level info
    # don't get read-locked unexpectedly.
    assert v.can_edit("bob") is True


# ---------------------------------------------------------------------------
# Input safety: payload mutation
# ---------------------------------------------------------------------------


def test_from_payload_does_not_mutate_input() -> None:
    """``from_payload`` must not mutate the caller's dict."""
    payload = _load_fixture()
    snapshot = copy.deepcopy(payload)
    View.from_payload(payload)
    assert payload == snapshot
