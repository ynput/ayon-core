"""Tests for the activity stream feed."""

from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.activity_stream import AYActivityStream
from ayon_core.ui.components.comment import AYPublish, AYStatusChange
from ayon_core.ui.data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    VersionPublishModel,
    relative_date,
)

STATUSES = [
    {
        "text": "Approved",
        "short_text": "APP",
        "icon": "task_alt",
        "color": "#00f0b4",
    }
]


def _activities() -> list:
    return [
        CommentModel(
            activity_id="comment",
            user_name="libor",
            user_full_name="Libor",
            comment="Looks good",
            comment_date="2026-10-03T10:00:00+00:00",
        ),
        StatusChangeModel(
            activity_id="status",
            user_name="libor",
            user_full_name="Libor",
            old_status="In progress",
            new_status="Approved",
            date="2026-10-02T10:00:00+00:00",
        ),
        VersionPublishModel(
            activity_id="publish",
            user_name="roy",
            user_full_name="Roy Nieterau",
            product="modelMain",
            version="v003",
            status="Approved",
            date="2026-10-01T10:00:00+00:00",
        ),
    ]


def test_stream_filters_by_category(qtbot) -> None:
    stream = AYActivityStream(status_definitions=STATUSES)
    qtbot.addWidget(stream)
    stream.show()

    stream.set_activities(_activities())
    assert stream.activity_count() == 3
    assert stream.activity_count(ActivityCategory.COMMENT) == 1

    stream._on_filter_clicked(1)
    visible = [
        activity.activity_id
        for activity, widget in stream._widgets
        if widget.isVisible()
    ]
    assert visible == ["comment"]
    assert stream._count_label.text() == "1 of 3"

    stream.set_message("Loading")
    assert stream.activity_count() == 0
    assert stream._message_label.text() == "Loading"


def test_publish_card_shows_version_status_and_thumbnail(
    qtbot, tmp_path
) -> None:
    from qtpy import QtGui

    image_path = tmp_path / "thumbnail.png"
    pixmap = QtGui.QPixmap(8, 8)
    pixmap.fill(QtGui.QColor("red"))
    pixmap.save(str(image_path))

    with_thumbnail, without_thumbnail = (
        VersionPublishModel(
            activity_id=activity_id,
            product="modelMain",
            version="v003",
            status="Approved",
            thumbnail_key=thumbnail_key,
            date="2026-10-01T10:00:00+00:00",
        )
        for activity_id, thumbnail_key in (
            ("a", "test_activity_stream/version/thumbnail"),
            ("b", ""),
        )
    )
    requested_keys = []

    def thumbnail_loader(key: str, on_loaded) -> None:
        requested_keys.append(key)
        on_loaded(str(image_path))

    stream = AYActivityStream(
        status_definitions=STATUSES, thumbnail_loader=thumbnail_loader
    )
    qtbot.addWidget(stream)
    stream.set_activities([with_thumbnail, without_thumbnail])

    rows = [widget for _, widget in stream._widgets]
    assert rows[0].thumbnail is not None
    assert rows[1].thumbnail is None
    # The key is not in the image cache, so it is asked from the loader
    assert requested_keys == ["test_activity_stream/version/thumbnail"]
    # Labels with an icon or elide keep their text in '_text'
    labels = {
        getattr(label, "_text", "") or label.text()
        for label in rows[0].findChildren(QtWidgets.QLabel)
    }
    assert {"modelMain", "v003", "Approved"} <= labels

    # The thumbnail gives way to the text when the row gets narrow
    stream.resize(400, 300)
    stream.show()
    qtbot.waitUntil(rows[0].thumbnail.isVisible)
    stream.resize(180, 300)
    qtbot.waitUntil(lambda: not rows[0].thumbnail.isVisible())


def test_relative_date_uses_the_largest_unit() -> None:
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)

    def ago(**kwargs) -> str:
        return relative_date((now - timedelta(**kwargs)).isoformat())

    assert ago(seconds=5) == "just now"
    assert ago(minutes=1, seconds=5) == "1 minute"
    assert ago(hours=13, minutes=5) == "13 hours"
    assert ago(days=7, hours=1) == "7 days"
    assert ago(days=5 * 30 + 3) == "5 months"
    assert relative_date("not a date") == "not a date"


def test_shared_rows_work_without_stream_data(qtbot) -> None:
    """Rows are also created on their own, e.g. by the review desktop."""
    parent = QtWidgets.QWidget()
    qtbot.addWidget(parent)

    publish = AYPublish(
        parent, data=VersionPublishModel(product="modelMain", version="v003")
    )
    # No status and thumbnail in the data, so only product and version
    assert publish.thumbnail is None
    assert publish.parent() is parent

    status_change = AYStatusChange(
        parent,
        data=StatusChangeModel(
            product="modelMain",
            version="v003",
            old_status="In progress",
            new_status="Approved",
        ),
    )
    labels = {
        getattr(label, "_text", "") or label.text()
        for label in status_change.findChildren(QtWidgets.QLabel)
    }
    # Both statuses are named and the version is shown when not compact
    assert {"In progress", "Approved", "modelMain v003"} <= labels

    compact = AYStatusChange(
        parent,
        data=StatusChangeModel(
            product="modelMain",
            version="v003",
            old_status="In progress",
            new_status="Approved",
        ),
        status_definitions=[
            {"text": "In progress", "icon": "play_arrow", "color": "#fff"}
        ],
        compact=True,
    )
    labels = {
        getattr(label, "_text", "") or label.text()
        for label in compact.findChildren(QtWidgets.QLabel)
    }
    assert "Approved" in labels
    assert not {"In progress", "modelMain v003"} & labels
    assert "modelMain v003" in compact.toolTip()


def test_stream_shows_avatars_from_cache(qtbot) -> None:
    from qtpy import QtCore, QtGui

    class FakeAvatarCache(QtCore.QObject):
        avatar_updated = QtCore.Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self.color = QtGui.QColor("red")
            self.requested: list[str] = []

        def pixmap(self, user_name: str, full_name: str, size: int):
            self.requested.append(user_name)
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(self.color)
            return pixmap

    def avatar_color(widget: QtWidgets.QWidget) -> str:
        return widget.user_icon.pixmap().toImage().pixelColor(1, 1).name()

    cache = FakeAvatarCache()
    stream = AYActivityStream(avatar_cache=cache)
    qtbot.addWidget(stream)
    stream.set_activities(_activities())

    # Comments, status changes and publishes all get the cached avatar
    assert cache.requested == ["libor", "libor", "roy"]
    assert {avatar_color(widget) for _, widget in stream._widgets} == {
        "#ff0000"
    }

    # Only avatars of the user whose download finished are replaced
    cache.color = QtGui.QColor("blue")
    cache.avatar_updated.emit("roy")
    assert [avatar_color(widget) for _, widget in stream._widgets] == [
        "#ff0000",
        "#ff0000",
        "#0000ff",
    ]
