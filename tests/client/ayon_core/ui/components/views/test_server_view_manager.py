"""Tests for :class:`ServerViewManager`.

The tests mock :mod:`ayon_api` so no real network is contacted.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ayon_core.ui.components.views import (
    ServerViewManager,
    View,
    ViewSettings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(
    view_id: str = "view_1",
    label: str = "A",
    position: int = 0,
    view_type: str = "versions",
) -> dict[str, Any]:
    """Return a minimal server-shaped view payload."""
    return {
        "id": view_id,
        "label": label,
        "viewType": view_type,
        "owner": "alice",
        "scope": "project",
        "visibility": "shared",
        "working": False,
        "position": position,
        "settings": {"columns": []},
    }


def _make_view(
    view_id: str = "view_1",
    label: str = "A",
    view_type: str = "versions",
    position: int = 0,
) -> View:
    return View(
        id=view_id,
        label=label,
        view_type=view_type,
        owner="alice",
        position=position,
        settings=ViewSettings(),
    )


def _resp(data: Any) -> MagicMock:
    """Build a fake response object with a ``data`` attribute."""
    resp = MagicMock()
    resp.data = data
    return resp


# ---------------------------------------------------------------------------
# list_views
# ---------------------------------------------------------------------------


def test_list_views_parses_dict_with_views_key() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp(
            {"views": [_payload("a", "A", 1), _payload("b", "B", 0)]}
        )
        views = mgr.list_views("versions")
    assert [v.id for v in views] == ["b", "a"]  # sorted by position
    fake_get.assert_called_once_with(
        "views/versions", project_name="P"
    )


def test_list_views_parses_flat_list() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("a", "A")])
        views = mgr.list_views("versions")
    assert len(views) == 1
    assert views[0].id == "a"


def test_list_views_uses_cache_on_second_call() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("a", "A")])
        mgr.list_views("versions")
        mgr.list_views("versions")
    fake_get.assert_called_once()


def test_list_views_network_error_emits_error_and_returns_empty() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get", side_effect=RuntimeError("boom")):
        views = mgr.list_views("versions")
    assert views == []
    assert errors and "boom" in errors[0]


def test_list_views_sorts_by_position_then_label_lower() -> None:
    mgr = ServerViewManager(project_name="P")
    payloads = [
        _payload("c", "ccc", 1),
        _payload("a", "Bbb", 0),
        _payload("b", "aaa", 0),
    ]
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp(payloads)
        views = mgr.list_views("versions")
    assert [v.id for v in views] == ["b", "a", "c"]


def test_list_views_empty_project_returns_empty_without_network() -> None:
    """list_views must not call the server when project_name is empty."""
    mgr = ServerViewManager(project_name="")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        views = mgr.list_views("versions")
    assert views == []
    fake_get.assert_not_called()


def test_list_views_populates_id_to_type_map() -> None:
    """id-map must be populated from list_views for delete_view."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")
    assert mgr._id_to_type.get("v1") == "versions"


# ---------------------------------------------------------------------------
# save_view
# ---------------------------------------------------------------------------


def test_save_view_empty_id_posts() -> None:
    mgr = ServerViewManager(project_name="P")
    view = View(label="New", view_type="versions", owner="alice",
                settings=ViewSettings())
    # id is empty string — must POST

    raw_post = MagicMock(return_value=_resp({}))
    raw_patch = MagicMock()

    conn = MagicMock()
    conn.raw_post = raw_post
    conn.raw_patch = raw_patch

    saved_ids: list[str] = []
    changed_types: list[str] = []
    mgr.view_saved.connect(saved_ids.append)
    mgr.views_changed.connect(changed_types.append)

    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    raw_post.assert_called_once()
    raw_patch.assert_not_called()
    endpoint = raw_post.call_args.args[0]
    assert endpoint.startswith("views/versions")
    assert "project_name=P" in endpoint
    assert changed_types == ["versions"]


def test_save_view_non_empty_id_patches_even_without_cache() -> None:
    """save_view must PATCH for any view with a non-empty id,
    regardless of whether the cache has been populated."""
    mgr = ServerViewManager(project_name="P")
    # Cache is cold — no list_views() called.
    view = _make_view("remote_id", "Existing")

    raw_post = MagicMock()
    raw_patch = MagicMock(return_value=_resp({}))
    conn = MagicMock()
    conn.raw_post = raw_post
    conn.raw_patch = raw_patch

    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    raw_patch.assert_called_once()
    raw_post.assert_not_called()


def test_save_view_known_remote_patches() -> None:
    mgr = ServerViewManager(project_name="P")
    # Prime the cache.
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    raw_post = MagicMock()
    raw_patch = MagicMock(return_value=_resp({}))
    conn = MagicMock()
    conn.raw_post = raw_post
    conn.raw_patch = raw_patch

    view = _make_view("v1", "Edited")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    raw_patch.assert_called_once()
    raw_post.assert_not_called()
    endpoint = raw_patch.call_args.args[0]
    assert endpoint.startswith("views/versions/v1")


def test_save_view_updates_cache_in_place() -> None:
    """save_view must update the cached list in-place, not pop it."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    conn = MagicMock()
    conn.raw_patch = MagicMock(return_value=_resp({}))
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(_make_view("v1", "Edited"))

    # Cache should still be populated (not cleared).
    assert "versions" in mgr._cache
    assert mgr._cache["versions"][0].label == "Edited"


def test_save_view_no_extra_round_trip_after_in_place_update() -> None:
    """After save_view, list_views should NOT re-fetch from server."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    conn = MagicMock()
    conn.raw_patch = MagicMock(return_value=_resp({}))
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(_make_view("v1", "Edited"))

    # Next list_views should come from the in-place-updated cache.
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get2:
        mgr.list_views("versions")
    fake_get2.assert_not_called()


def test_save_view_network_error_emits_and_raises() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)

    conn = MagicMock()
    conn.raw_post = MagicMock(side_effect=RuntimeError("boom"))
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get_server_api_connection",
               return_value=conn):
        with pytest.raises(RuntimeError):
            mgr.save_view(View(label="New", view_type="versions",
                               owner="alice", settings=ViewSettings()))
    assert errors and "boom" in errors[0]


# ---------------------------------------------------------------------------
# delete_view
# ---------------------------------------------------------------------------


def test_delete_view_calls_endpoint_and_emits() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    deleted: list[str] = []
    changed: list[str] = []
    mgr.view_deleted.connect(deleted.append)
    mgr.views_changed.connect(changed.append)

    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.delete") as fake_delete:
        mgr.delete_view("v1")
    fake_delete.assert_called_once_with(
        "views/versions/v1", project_name="P"
    )
    assert deleted == ["v1"]
    assert changed == ["versions"]


def test_delete_view_uses_id_map_when_cache_is_cold() -> None:
    """delete_view must work via the id-map even after cache is cleared."""
    mgr = ServerViewManager(project_name="P")
    # Populate id-map via list_views.
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    # Clear the per-type cache manually (as set_project would).
    mgr._cache.clear()

    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.delete") as fake_delete:
        mgr.delete_view("v1")

    # Should still call delete using the id-map lookup.
    fake_delete.assert_called_once_with(
        "views/versions/v1", project_name="P"
    )


def test_delete_view_removes_entry_in_place() -> None:
    """delete_view must remove the entry from the cached list in place."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp(
            [_payload("v1", "A"), _payload("v2", "B")]
        )
        mgr.list_views("versions")

    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.delete"):
        mgr.delete_view("v1")

    # Cache should still exist but without v1.
    assert "versions" in mgr._cache
    assert all(v.id != "v1" for v in mgr._cache["versions"])


def test_delete_view_unknown_id_emits_error_only() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.delete") as fake_delete:
        mgr.delete_view("nope")
    fake_delete.assert_not_called()
    assert errors and "nope" in errors[0]


def test_delete_view_empty_project_is_noop() -> None:
    """delete_view must silently no-op when project_name is empty."""
    mgr = ServerViewManager(project_name="")
    mgr._id_to_type["v1"] = "versions"  # inject manually
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.delete") as fake_delete:
        mgr.delete_view("v1")
    fake_delete.assert_not_called()


# ---------------------------------------------------------------------------
# set_project
# ---------------------------------------------------------------------------


def test_set_project_emits_per_known_type_after_list_views() -> None:
    """set_project should emit views_changed per known type."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1")])
        mgr.list_views("versions")

    emitted: list[str] = []
    mgr.views_changed.connect(emitted.append)
    mgr.set_project("Q")
    assert mgr.project_name == "Q"
    assert emitted == ["versions"]


def test_set_project_emits_sentinel_when_no_types_known() -> None:
    """Empty string sentinel is emitted when no view type has been listed."""
    mgr = ServerViewManager(project_name="P")
    emitted: list[str] = []
    mgr.views_changed.connect(emitted.append)
    mgr.set_project("Q")
    assert emitted == [""]


def test_set_project_noop_when_same() -> None:
    mgr = ServerViewManager(project_name="P")
    emitted: list[str] = []
    mgr.views_changed.connect(emitted.append)
    mgr.set_project("P")
    assert emitted == []


def test_set_project_clears_both_caches() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1")])
        mgr.list_views("versions")

    assert "v1" in mgr._id_to_type
    assert "versions" in mgr._cache

    mgr.set_project("Q")
    assert mgr._id_to_type == {}
    assert mgr._cache == {}


def test_set_project_retains_known_types_across_clears() -> None:
    """_known_types persists so the next set_project can still emit."""
    mgr = ServerViewManager(project_name="P")
    with patch("ayon_core.ui.components.views.server_view_manager"
               ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([])
        mgr.list_views("versions")

    # First switch: emits "versions" (known type)
    emitted: list[str] = []
    mgr.views_changed.connect(emitted.append)
    mgr.set_project("Q")
    assert emitted == ["versions"]
    emitted.clear()

    # Second switch without new list_views: should still know "versions"
    mgr.set_project("R")
    assert emitted == ["versions"]
