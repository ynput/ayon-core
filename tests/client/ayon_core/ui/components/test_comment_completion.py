"""Tests for the user mention completer of comments."""

from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components import comment_completion
from ayon_core.ui.components.comment_completion import (
    UserCompleterDelegate,
    UserCompleterModel,
)
from ayon_core.ui.data_models import User


def test_completer_shows_downloaded_avatars(qtbot, monkeypatch) -> None:
    sources: dict[str, str] = {}
    user_image_cls = comment_completion.AYUserImage

    def user_image(*args, **kwargs):
        sources[kwargs["name"]] = kwargs["src"]
        # Render initials, there is no image file to load
        kwargs["src"] = ""
        return user_image_cls(*args, **kwargs)

    monkeypatch.setattr(comment_completion, "AYUserImage", user_image)
    users = [
        User(
            name="kayla",
            short_name="kayla",
            full_name="Kayla",
            email="",
            avatar_url="https://ayon.server/api/users/kayla/avatar",
            avatar_local_path="/cache/kayla.png",
        ),
        User(name="roy", short_name="roy", full_name="Roy", email=""),
    ]
    view = QtWidgets.QListView()
    qtbot.addWidget(view)
    view.setModel(UserCompleterModel(users, view))
    view.setItemDelegate(UserCompleterDelegate(view))
    view.resize(200, 80)
    view.show()
    view.grab()

    # The local avatar file is used, the url can not be loaded as an image
    assert sources == {"kayla": "/cache/kayla.png", "roy": ""}
