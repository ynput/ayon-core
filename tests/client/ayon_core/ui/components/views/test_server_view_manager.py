"""Tests for :class:`ServerViewManager`.

The tests mock :mod:`ayon_api` so no real network is contacted.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from ayon_core.ui.components.views import (
    Scope,
    ServerViewManager,
    View,
    ViewSettings,
    Visibility,
)


_MODULE = "ayon_core.ui.components.views.server_view_manager"


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
        "visibility": "public",
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


def _patch_bundle(powerpack_version: str | None = None):
    """Patch the bundle lookup so no server is ever contacted.

    Args:
        powerpack_version: Version of the powerpack addon in the bundle,
            or ``None`` for a bundle without powerpack.
    """
    addons = []
    if powerpack_version:
        addons.append(
            SimpleNamespace(name="powerpack", version=powerpack_version)
        )
    return patch(
        _MODULE + ".get_bundle_information",
        return_value=SimpleNamespace(addons=addons),
    )


# ---------------------------------------------------------------------------
# list_views
# ---------------------------------------------------------------------------


def test_list_views_parses_dict_with_views_key() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
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
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("a", "A")])
        views = mgr.list_views("versions")
    assert len(views) == 1
    assert views[0].id == "a"


def test_list_views_uses_cache_on_second_call() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("a", "A")])
        mgr.list_views("versions")
        mgr.list_views("versions")
    fake_get.assert_called_once()


def test_list_views_network_error_emits_error_and_returns_empty() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)
    with patch(_MODULE + ".ayon_api.get", side_effect=RuntimeError("boom")):
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
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp(payloads)
        views = mgr.list_views("versions")
    assert [v.id for v in views] == ["b", "a", "c"]


def test_list_views_empty_project_returns_empty_without_network() -> None:
    """list_views must not call the server when project_name is empty."""
    mgr = ServerViewManager(project_name="")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        views = mgr.list_views("versions")
    assert views == []
    fake_get.assert_not_called()


def test_list_views_populates_id_to_type_map() -> None:
    """id-map must be populated from list_views for delete_view."""
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")
    assert mgr._id_to_view_attributes.get("v1") == (
        "versions", Scope.PROJECT
    )


# ---------------------------------------------------------------------------
# save_view
# ---------------------------------------------------------------------------


def test_save_view_empty_id_posts() -> None:
    mgr = ServerViewManager(project_name="P")
    view = View(label="New", view_type="versions", owner="alice",
                settings=ViewSettings())
    # id is empty string — must POST

    saved_ids: list[str] = []
    changed_types: list[str] = []
    mgr.view_saved.connect(saved_ids.append)
    mgr.views_changed.connect(changed_types.append)

    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.post",
               return_value=_resp({})) as fake_post, \
         patch(_MODULE + ".ayon_api.patch") as fake_patch:
        mgr.save_view(view)

    fake_post.assert_called_once()
    fake_patch.assert_not_called()
    endpoint = fake_post.call_args.args[0]
    assert endpoint.startswith("views/versions")
    assert "project_name=P" in endpoint
    assert "id" not in fake_post.call_args.kwargs
    assert changed_types == ["versions"]


def test_save_view_non_empty_id_patches_even_without_cache() -> None:
    """save_view must PATCH for any view with a non-empty id,
    regardless of whether the cache has been populated."""
    mgr = ServerViewManager(project_name="P")
    # Cache is cold — no list_views() called.
    view = _make_view("remote_id", "Existing")

    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.post") as fake_post, \
         patch(_MODULE + ".ayon_api.patch",
               return_value=_resp({})) as fake_patch:
        mgr.save_view(view)

    fake_patch.assert_called_once()
    fake_post.assert_not_called()


def test_save_view_known_remote_patches() -> None:
    mgr = ServerViewManager(project_name="P")
    # Prime the cache.
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    view = _make_view("v1", "Edited")
    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.post") as fake_post, \
         patch(_MODULE + ".ayon_api.patch",
               return_value=_resp({})) as fake_patch:
        mgr.save_view(view)

    fake_patch.assert_called_once()
    fake_post.assert_not_called()
    endpoint = fake_patch.call_args.args[0]
    assert endpoint.startswith("views/versions/v1")


def test_save_view_updates_cache_in_place() -> None:
    """save_view must update the cached list in-place, not pop it."""
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.patch", return_value=_resp({})):
        mgr.save_view(_make_view("v1", "Edited"))

    # Cache should still be populated (not cleared).
    assert "versions" in mgr._cache
    assert mgr._cache["versions"][0].label == "Edited"


def test_save_view_no_extra_round_trip_after_in_place_update() -> None:
    """After save_view, list_views should NOT re-fetch from server."""
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.patch", return_value=_resp({})):
        mgr.save_view(_make_view("v1", "Edited"))

    # Next list_views should come from the in-place-updated cache.
    with patch(_MODULE + ".ayon_api.get") as fake_get2:
        mgr.list_views("versions")
    fake_get2.assert_not_called()


def test_save_view_network_error_emits_and_raises() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)

    with _patch_bundle(), \
         patch(_MODULE + ".ayon_api.post",
               side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            mgr.save_view(View(label="New", view_type="versions",
                               owner="alice", settings=ViewSettings()))
    assert errors and "boom" in errors[0]


def test_save_view_shares_as_public_when_access_has_positive_values() -> None:
    """Positive access levels publish the view via the share endpoint."""
    mgr = ServerViewManager(project_name="P")
    view = View(
        id="v1",
        label="Shared",
        view_type="versions",
        owner="alice",
        settings=ViewSettings(),
    )
    view.visibility = Visibility.PRIVATE
    view.access = {"__everyone__": 20}

    fake_patch = MagicMock(return_value=_resp({}))
    conn = MagicMock()
    conn.raw_post = MagicMock()

    with patch(_MODULE + ".ayon_api.patch", fake_patch), \
         _patch_bundle(powerpack_version="1.6.3"), \
         patch(_MODULE + ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    # Visibility is owned by the share endpoint, not the view PATCH.
    fake_patch.assert_called_once()
    conn.raw_post.assert_called_once()
    share_endpoint = conn.raw_post.call_args.args[0]
    assert "addons/powerpack/1.6.3/views/versions/v1/share" in share_endpoint
    share_json = conn.raw_post.call_args.kwargs["json"]
    assert share_json["visibility"] == "public"
    assert share_json["access"] == {"__everyone__": 20}


def test_save_view_unshares_when_access_is_non_positive() -> None:
    """Non-positive access levels revoke sharing (visibility private)."""
    mgr = ServerViewManager(project_name="P")
    view = View(
        id="v1",
        label="NoShare",
        view_type="versions",
        owner="alice",
        settings=ViewSettings(),
        access={"__everyone__": 0},
    )

    fake_patch = MagicMock(return_value=_resp({}))
    conn = MagicMock()
    conn.raw_post = MagicMock()

    with patch(_MODULE + ".ayon_api.patch", fake_patch), \
         _patch_bundle(powerpack_version="1.6.3"), \
         patch(_MODULE + ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    conn.raw_post.assert_called_once()
    share_json = conn.raw_post.call_args.kwargs["json"]
    assert share_json["visibility"] == "private"
    assert share_json["access"] == {"__everyone__": 0}


def test_save_view_skips_share_endpoint_without_powerpack() -> None:
    """Without the powerpack addon, save_view must never call share.

    Even a view with positive access levels must not reach the share
    endpoint when the bundle has no powerpack addon - supports_sharing()
    should gate the whole patch_view_access() call, not just the
    positive-vs-non-positive access decision.
    """
    mgr = ServerViewManager(project_name="P")
    view = View(
        id="v1",
        label="Shared",
        view_type="versions",
        owner="alice",
        settings=ViewSettings(),
        access={"__everyone__": 20},
    )

    fake_patch = MagicMock(return_value=_resp({}))
    conn = MagicMock()
    conn.raw_post = MagicMock()

    with patch(_MODULE + ".ayon_api.patch", fake_patch), \
         _patch_bundle(), \
         patch(_MODULE + ".ayon_api.get_server_api_connection",
               return_value=conn):
        mgr.save_view(view)

    fake_patch.assert_called_once()
    conn.raw_post.assert_not_called()


# ---------------------------------------------------------------------------
# delete_view
# ---------------------------------------------------------------------------


def test_delete_view_calls_endpoint_and_emits() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    deleted: list[str] = []
    changed: list[str] = []
    mgr.view_deleted.connect(deleted.append)
    mgr.views_changed.connect(changed.append)

    with patch(_MODULE + ".ayon_api.delete") as fake_delete:
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
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1", "A")])
        mgr.list_views("versions")

    # Clear the per-type cache manually (as set_project would).
    mgr._cache.clear()

    with patch(_MODULE + ".ayon_api.delete") as fake_delete:
        mgr.delete_view("v1")

    # Should still call delete using the id-map lookup.
    fake_delete.assert_called_once_with(
        "views/versions/v1", project_name="P"
    )


def test_delete_view_removes_entry_in_place() -> None:
    """delete_view must remove the entry from the cached list in place."""
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp(
            [_payload("v1", "A"), _payload("v2", "B")]
        )
        mgr.list_views("versions")

    with patch(_MODULE + ".ayon_api.delete"):
        mgr.delete_view("v1")

    # Cache should still exist but without v1.
    assert "versions" in mgr._cache
    assert all(v.id != "v1" for v in mgr._cache["versions"])


def test_delete_view_unknown_id_emits_error_only() -> None:
    mgr = ServerViewManager(project_name="P")
    errors: list[str] = []
    mgr.error.connect(errors.append)
    with patch(_MODULE + ".ayon_api.delete") as fake_delete:
        mgr.delete_view("nope")
    fake_delete.assert_not_called()
    assert errors and "nope" in errors[0]


def test_delete_view_empty_project_is_noop() -> None:
    """delete_view must silently no-op when project_name is empty."""
    mgr = ServerViewManager(project_name="")
    # inject manually
    mgr._id_to_view_attributes["v1"] = ("versions", Scope.PROJECT)
    with patch(_MODULE + ".ayon_api.delete") as fake_delete:
        mgr.delete_view("v1")
    fake_delete.assert_not_called()


# ---------------------------------------------------------------------------
# set_project
# ---------------------------------------------------------------------------


def test_set_project_emits_project_changed() -> None:
    """set_project announces the switch via project_changed only."""
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1")])
        mgr.list_views("versions")

    projects: list[str] = []
    changed_types: list[str] = []
    mgr.project_changed.connect(projects.append)
    mgr.views_changed.connect(changed_types.append)
    mgr.set_project("Q")
    mgr.set_project("R")
    assert mgr.project_name == "R"
    assert projects == ["Q", "R"]
    assert changed_types == []


def test_set_project_noop_when_same() -> None:
    mgr = ServerViewManager(project_name="P")
    emitted: list[str] = []
    mgr.project_changed.connect(emitted.append)
    mgr.views_changed.connect(emitted.append)
    mgr.set_project("P")
    assert emitted == []


def test_set_project_clears_both_caches() -> None:
    mgr = ServerViewManager(project_name="P")
    with patch(_MODULE + ".ayon_api.get") as fake_get:
        fake_get.return_value = _resp([_payload("v1")])
        mgr.list_views("versions")

    assert "v1" in mgr._id_to_view_attributes
    assert "versions" in mgr._cache

    mgr.set_project("Q")
    assert mgr._id_to_view_attributes == {}
    assert mgr._cache == {}
