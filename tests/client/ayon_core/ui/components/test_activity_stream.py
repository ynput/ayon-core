"""Tests for the activity stream feed."""

from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.activity_stream import (
    AYActivityStream,
    _relative_date,
)
from ayon_core.ui.data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    VersionPublishModel,
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
            thumbnail_src=thumbnail_src,
            date="2026-10-01T10:00:00+00:00",
        )
        for activity_id, thumbnail_src in (
            ("a", str(image_path)),
            ("b", ""),
        )
    )
    stream = AYActivityStream(status_definitions=STATUSES)
    qtbot.addWidget(stream)
    stream.set_activities([with_thumbnail, without_thumbnail])

    rows = [widget for _, widget in stream._widgets]
    assert rows[0].thumbnail is not None
    assert rows[1].thumbnail is None
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
        return _relative_date((now - timedelta(**kwargs)).isoformat())

    assert ago(seconds=5) == "just now"
    assert ago(minutes=1, seconds=5) == "1 minute"
    assert ago(hours=13, minutes=5) == "13 hours"
    assert ago(days=7, hours=1) == "7 days"
    assert ago(days=5 * 30 + 3) == "5 months"
    assert _relative_date("not a date") == "not a date"
