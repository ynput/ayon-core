"""Tests for the activity stream feed."""

from __future__ import annotations

from qtpy import QtWidgets

from ayon_core.ui.components.activity_stream import AYActivityStream
from ayon_core.ui.components.comment import AYPublish, AYStatusChange
from ayon_core.ui.data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    User,
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


def _comments(count: int, first: int = 0) -> list[CommentModel]:
    return [
        CommentModel(
            activity_id=f"comment{idx}",
            user_name="libor",
            user_full_name="Libor",
            comment=f"Comment {idx}",
            comment_date="2026-10-03T10:00:00+00:00",
        )
        for idx in range(first, first + count)
    ]


def test_refresh_reuses_rows_and_releases_removed_ones(qtbot) -> None:
    stream = AYActivityStream()
    qtbot.addWidget(stream)

    stream.set_activities(_comments(3))
    rows = {
        activity.activity_id: widget for activity, widget in stream._widgets
    }
    child_count = len(stream._items.findChildren(QtWidgets.QWidget))

    # Refresh with one new activity on top and the oldest one gone
    stream.set_activities(_comments(1, first=9) + _comments(2))
    new_rows = {
        activity.activity_id: widget for activity, widget in stream._widgets
    }
    assert list(new_rows) == ["comment9", "comment0", "comment1"]
    assert new_rows["comment0"] is rows["comment0"]
    assert new_rows["comment1"] is rows["comment1"]
    layout = stream._items._layout
    assert [layout.itemAt(idx).widget() for idx in range(3)] == list(
        new_rows.values()
    )
    # The removed row is released right away, nothing piles up
    assert rows["comment2"].parent() is None
    assert (
        len(stream._items.findChildren(QtWidgets.QWidget)) == child_count
    )

    # An activity that changed gets a new row
    changed = _comments(2)
    changed[1].comment = "Edited"
    stream.set_activities(changed)
    assert stream._widgets[0][1] is rows["comment0"]
    assert stream._widgets[1][1] is not rows["comment1"]


def test_refresh_keeps_the_scroll_position(qtbot) -> None:
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.resize(300, 200)
    stream.show()
    stream.set_activities(_comments(30))
    scroll_bar = stream._scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: scroll_bar.maximum() > 0)

    scroll_bar.setValue(scroll_bar.maximum() // 2)
    anchor, offset = stream._get_scroll_anchor()

    # New activity on top: the reader stays at the row they look at
    stream.set_activities(_comments(1, first=99) + _comments(30))
    assert scroll_bar.value() > 0
    assert anchor.geometry().top() - scroll_bar.value() == offset

    # A different feed starts at the top
    stream.set_activities(_comments(30, first=100))
    assert scroll_bar.value() == 0


def test_setters_update_displayed_rows(qtbot) -> None:
    def label_icons(widget: QtWidgets.QWidget) -> set[str]:
        return {
            label._icon
            for label in widget.findChildren(QtWidgets.QLabel)
            if isinstance(getattr(label, "_icon", None), str) and label._icon
        }

    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.set_activities(_activities())
    comment_row, status_row, publish_row = (
        widget for _, widget in stream._widgets
    )
    assert "task_alt" not in label_icons(status_row)

    # Statuses that arrive after the activities are rendered as well
    stream.set_status_definitions(STATUSES)
    new_comment_row, new_status_row, new_publish_row = (
        widget for _, widget in stream._widgets
    )
    assert "task_alt" in label_icons(new_status_row)
    assert "task_alt" in label_icons(new_publish_row)
    assert new_comment_row is comment_row

    # Setting the same statuses again does not create rows
    stream.set_status_definitions(list(STATUSES))
    assert stream._widgets[1][1] is new_status_row

    stream.set_user_list(
        [User(name="roy", short_name="roy", full_name="Roy", email="")]
    )
    assert stream._widgets[0][1] is not comment_row
    assert stream._widgets[1][1] is new_status_row


def test_relative_date_of_a_future_date_is_just_now() -> None:
    from datetime import datetime, timedelta, timezone

    future = datetime.now(timezone.utc) + timedelta(hours=2)
    assert relative_date(future.isoformat()) == "just now"


def _checklist_comment() -> CommentModel:
    return CommentModel(
        activity_id="checklist",
        user_name="libor",
        user_full_name="Libor",
        comment="To do\n\n- [ ] Fix the shoulder\n- [x] Check the cloth\n",
        comment_date="2026-10-03T10:00:00+00:00",
    )


def _click_first_checkbox(qtbot, comment_row: QtWidgets.QWidget) -> bool:
    """Click the first checkbox of a comment, if there is any to hit."""
    from qtpy import QtCore

    text_field = comment_row.text_field
    handler = text_field._checkbox_handler
    viewport = text_field.viewport()
    for y in range(0, viewport.height(), 2):
        for x in range(0, 60, 2):
            point = QtCore.QPoint(x, y)
            found = handler.find_checkbox_at_click(
                point, text_field.contentOffset().toPoint()
            )
            if found is not None and found[0]:
                qtbot.mouseClick(
                    viewport, QtCore.Qt.MouseButton.LeftButton, pos=point
                )
                return True
    return False


def test_read_only_stream_does_not_change_comments(qtbot) -> None:
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.resize(320, 300)
    stream.show()
    comment = _checklist_comment()
    stream.set_activities([comment])
    row = stream._widgets[0][1]
    qtbot.waitExposed(stream)
    markdown = comment.comment

    assert not row.edit_button.isVisible()
    assert not row.del_button.isVisible()
    # The checkbox is there, clicking it does not toggle it
    assert _click_first_checkbox(qtbot, row)
    assert comment.comment == markdown


def test_editable_stream_reports_changes_of_comments(qtbot) -> None:
    stream = AYActivityStream(editable=True, compact=False)
    qtbot.addWidget(stream)
    stream.resize(320, 300)
    stream.show()
    comment = _checklist_comment()
    stream.set_activities(
        [comment, _activities()[1]], empty_text="No activity"
    )
    row, status_row = (widget for _, widget in stream._widgets)
    qtbot.waitExposed(stream)
    edited, deleted = [], []
    stream.comment_edited.connect(edited.append)
    stream.comment_deleted.connect(deleted.append)

    # Toggling a checkbox edits the comment
    assert _click_first_checkbox(qtbot, row)
    assert edited == [comment]
    assert "[x] Fix the shoulder" in comment.comment

    row.comment_deleted.emit(comment)
    assert deleted == [comment]
    # Not compact: the previous status is named
    labels = {
        getattr(label, "_text", "") or label.text()
        for label in status_row.findChildren(QtWidgets.QLabel)
    }
    assert "In progress" in labels


def test_stream_filters_checklists(qtbot) -> None:
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.show()
    stream.set_activities([_checklist_comment()] + _activities())

    assert stream.activity_count(ActivityCategory.CHECKLIST) == 1
    stream._on_filter_clicked(3)
    assert [
        activity.activity_id
        for activity, widget in stream._widgets
        if widget.isVisible()
    ] == ["checklist"]


def test_stick_to_bottom_follows_the_end_of_the_feed(qtbot) -> None:
    stream = AYActivityStream(stick_to_bottom=True)
    qtbot.addWidget(stream)
    stream.resize(300, 200)
    stream.show()
    stream.set_activities(_comments(30))
    scroll_bar = stream._scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: scroll_bar.maximum() > 0)
    # A new feed starts at its end, where the newest activity is
    assert scroll_bar.value() == scroll_bar.maximum()

    # A new activity at the end is followed
    maximum = scroll_bar.maximum()
    stream.set_activities(_comments(31))
    qtbot.waitUntil(lambda: scroll_bar.maximum() > maximum)
    assert scroll_bar.value() == scroll_bar.maximum()

    # A reader who scrolled away stays at the row they look at
    scroll_bar.setValue(scroll_bar.maximum() // 2)
    anchor, offset = stream._get_scroll_anchor()
    stream.set_activities(_comments(32))
    qtbot.waitUntil(lambda: scroll_bar.maximum() > maximum)
    assert anchor.geometry().top() - scroll_bar.value() == offset
    assert scroll_bar.value() < scroll_bar.maximum()

    # Until asked to go to the end, e.g. after submitting a comment
    stream.scroll_to_bottom()
    assert scroll_bar.value() == scroll_bar.maximum()

    # A different feed starts at its end again
    scroll_bar.setValue(0)
    stream.set_activities(_comments(30, first=100))
    assert scroll_bar.value() == scroll_bar.maximum() > 0


def test_stream_reports_the_activities_in_view(qtbot, monkeypatch) -> None:
    monkeypatch.setattr(AYActivityStream, "viewport_changed_delay", 0)
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.resize(300, 200)
    # Nothing is in view while the stream is not shown
    stream.set_activities(_comments(30))
    assert stream.get_visible_activities() == []

    with qtbot.waitSignal(stream.viewport_changed, timeout=1000):
        stream.show()
    scroll_bar = stream._scroll.verticalScrollBar()
    qtbot.waitUntil(lambda: scroll_bar.maximum() > 0)
    visible = [a.activity_id for a in stream.get_visible_activities()]
    assert visible[0] == "comment0"
    assert 0 < len(visible) < 30

    with qtbot.waitSignal(stream.viewport_changed, timeout=1000):
        scroll_bar.setValue(scroll_bar.maximum())
    visible = [a.activity_id for a in stream.get_visible_activities()]
    assert visible[-1] == "comment29"
    assert "comment0" not in visible

    # Rows hidden by the filter are not in view
    with qtbot.waitSignal(stream.viewport_changed, timeout=1000):
        stream._on_filter_clicked(2)
    assert stream.get_visible_activities() == []


def test_lazy_attachments_are_refreshed_by_file_id(
    qtbot, tmp_path, monkeypatch
) -> None:
    from qtpy import QtGui

    from ayon_core.ui.components import comment as comment_module
    from ayon_core.ui.data_models import FileModel
    from ayon_core.ui.image_cache import make_activity_cache_key

    image_path = tmp_path / "attachment.png"
    pixmap = QtGui.QPixmap(8, 8)
    pixmap.fill(QtGui.QColor("red"))
    pixmap.save(str(image_path))

    class _ImageCache:
        """Image cache with the files downloaded by the owner."""

        paths: dict = {}

        @classmethod
        def get_instance(cls):
            return cls()

        def get_path(self, key: str):
            return self.paths.get(key)

        def get(self, key: str, file_closure) -> str:
            return str(file_closure())

    monkeypatch.setattr(comment_module, "ImageCache", _ImageCache)

    def _comment() -> CommentModel:
        return CommentModel(
            activity_id="comment",
            comment="See the attachment",
            comment_date="2026-10-03T10:00:00+00:00",
            files=[FileModel(id="file1", mime="image/png")],
        )

    # Attachments that are not downloaded take no space by default
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.show()
    stream.set_activities([_comment()])
    assert not stream._widgets[0][1].images_container.isVisible()

    stream = AYActivityStream(lazy_attachments=True)
    qtbot.addWidget(stream)
    stream.show()
    stream.set_activities([_comment(), _comments(1)[0]])
    row = stream._widgets[0][1]
    attachment = row._image_widgets["file1"]
    # A placeholder keeps the height of the row
    assert row.images_container.isVisible()
    assert not attachment._thumb_path
    assert not stream._widgets[1][1].images_container.isVisible()

    # The owner downloaded the file and reports it
    for is_thumbnail in (True, False):
        key = make_activity_cache_key("demo", "file1", is_thumbnail)
        _ImageCache.paths[key] = str(image_path)
    assert stream.refresh_attachment("file1", "demo")
    assert attachment._thumb_path == str(image_path)
    assert attachment.image_path == str(image_path)
    assert not stream.refresh_attachment("unknown", "demo")


def test_page_is_shown_instead_of_the_feed(qtbot) -> None:
    stream = AYActivityStream()
    qtbot.addWidget(stream)
    stream.show()
    page = QtWidgets.QLabel("Details of the version")
    button = stream.add_page("Details", page)
    assert not page.isVisible()

    # A page is available without activities, and so is the way back
    button.click()
    assert page.isVisible()
    assert not stream._message_label.isVisible()
    assert stream._filter_buttons[0].isEnabled()
    stream._filter_buttons[0].click()
    assert not page.isVisible()
    assert stream._message_label.isVisible()
    assert not button.isChecked()

    stream.set_activities(_activities())
    button.click()
    assert page.isVisible()
    assert not stream._scroll.isVisible()
    assert not stream._count_label.isVisible()
    # A refresh of the feed keeps the page
    stream.set_activities(_activities()[:2])
    assert page.isVisible()
    assert not stream._scroll.isVisible()

    stream._filter_buttons[1].click()
    assert not page.isVisible()
    assert stream._scroll.isVisible()
    assert stream._count_label.text() == "1 of 2"
