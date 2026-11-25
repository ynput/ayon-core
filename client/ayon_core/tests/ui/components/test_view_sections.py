"""Tests for how the view selector groups saved views into sections."""

from unittest.mock import MagicMock, Mock

from qtpy.QtWidgets import QDialog

from ayon_core.ui.components.views import server_view_manager
from ayon_core.ui.components.views.data_models import View, Visibility
from ayon_core.ui.components.views.server_view_manager import (
    ServerViewManager,
)
from ayon_core.ui.components.views.view_selector import AYViewSelector


ME = "me"


def _view(view_id: str, owner: str, visibility: Visibility, **kwargs):
    return View(
        id=view_id,
        label=view_id,
        owner=owner,
        visibility=visibility,
        **kwargs,
    )


def _sections(views: list[View], supports_sharing: bool = True):
    selector = Mock(spec=AYViewSelector)
    selector._views = views
    selector._current_user = ME
    selector._manager = Mock()
    selector._manager.supports_sharing.return_value = supports_sharing
    return {
        key: (title, [v.id for v in section_views])
        for key, title, section_views in (
            AYViewSelector._get_view_sections(selector)
        )
    }


def test_views_are_grouped_like_the_frontend():
    views = [
        _view("working", ME, Visibility.PRIVATE, working=True),
        _view("my_public", ME, Visibility.PUBLIC),
        _view("my_private", ME, Visibility.PRIVATE),
        _view("shared", "bob", Visibility.PUBLIC),
        _view("not_shared", "bob", Visibility.PUBLIC, shared_with_me=False),
    ]

    assert _sections(views) == {
        "my_views": ("My views", ["my_public", "my_private"]),
        "shared_views": ("Shared with me", ["shared"]),
        "all_views": ("All views (admin only)", ["not_shared"]),
    }


def test_empty_sections_are_left_out():
    views = [_view("working", ME, Visibility.PRIVATE, working=True)]

    assert _sections(views) == {}


def test_other_users_views_need_sharing_support():
    views = [
        _view("mine", ME, Visibility.PRIVATE),
        _view("shared", "bob", Visibility.PUBLIC),
    ]

    assert _sections(views, supports_sharing=False) == {
        "my_views": ("My views", ["mine"]),
    }


def test_shared_with_me_is_read_from_the_listing():
    payload = {"id": "v1", "label": "v1", "sharedWithMe": False}

    view = View.from_payload(payload)

    assert view.shared_with_me is False
    assert "sharedWithMe" not in view.to_payload()
    assert View.from_payload({"id": "v2"}).shared_with_me is True


def test_shared_with_me_survives_load_and_save(monkeypatch):
    api = Mock()
    api.get.return_value.data = {"id": "v1", "label": "v1"}
    api.patch.return_value.data = {"id": "v1", "label": "renamed"}
    monkeypatch.setattr(server_view_manager, "ayon_api", api)
    manager = ServerViewManager("test")
    monkeypatch.setattr(manager, "supports_sharing", lambda: False)
    listed = _view("v1", "bob", Visibility.PUBLIC, shared_with_me=False)
    listed.view_type = "versions"
    listed.loaded = False

    loaded = manager.load_view(listed)
    saved = manager.save_view(loaded)

    assert loaded.shared_with_me is False
    assert saved.shared_with_me is False


def test_editing_a_view_keeps_shared_with_me():
    listed = _view("v1", "bob", Visibility.PUBLIC, shared_with_me=False)
    selector = MagicMock(spec=AYViewSelector)
    selector._manager = Mock()
    selector._manager.load_view.return_value = listed
    selector._current_view = None
    editor = selector._create_editor.return_value
    editor.exec.return_value = QDialog.DialogCode.Accepted
    editor.delete_requested.return_value = False
    selector._create_editor.side_effect = lambda view: (
        editor.get_view.configure_mock(return_value=view) or editor
    )

    AYViewSelector._on_edit_clicked(selector, listed)

    edited = selector._save_view.call_args.args[0]
    assert edited is not listed
    assert edited.shared_with_me is False
