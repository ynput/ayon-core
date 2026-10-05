"""Read-only feed of comments, publishes and status changes of an entity.

The stream is display-only: it is handed already converted activity models
and knows nothing about the server, so it can be reused by any tool and
previewed with sample data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional, Union

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt

from ..data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    User,
    VersionPublishModel,
)
from .buttons import AYButton
from .comment import AYComment
from .container import AYContainer
from .entity_thumbnail import AYEntityThumbnail
from .label import AYLabel
from .scroll_area import AYScrollArea
from .user_image import AYUserImage

ActivityModel = Union[CommentModel, VersionPublishModel, StatusChangeModel]
# Non-blocking '(key, on_loaded)' loader, see 'AYEntityThumbnail'
ThumbnailLoader = Optional[Callable[[str, Callable[[str], None]], None]]

_FILTERS: tuple[tuple[str, str, ActivityCategory], ...] = (
    ("All", "", ActivityCategory.ALL),
    ("Comments", "chat", ActivityCategory.COMMENT),
    ("Publishes", "layers", ActivityCategory.VERSION_PUBLISH),
    ("Status", "arrow_circle_right", ActivityCategory.STATUS_CHANGE),
)


def _relative_date(date_str: str) -> str:
    """Format a date as the time passed since, e.g. ``"13 hours"``.

    Args:
        date_str: Date in ISO format.

    Returns:
        Time passed in its largest unit, or the input if it can not be
        parsed.
    """
    try:
        date = datetime.fromisoformat(date_str).astimezone()
    except (TypeError, ValueError):
        return date_str
    seconds = (datetime.now().astimezone() - date).total_seconds()
    if seconds < 60:
        return "just now"
    for unit, size in (
        ("year", 365 * 86400),
        ("month", 30 * 86400),
        ("day", 86400),
        ("hour", 3600),
        ("minute", 60),
    ):
        count = int(seconds // size)
        if count:
            return f"{count} {unit}{'s' if count > 1 else ''}"
    return date_str


class _ItemsContainer(AYContainer):
    """Feed content that never forces the scroll area wider.

    A scroll area does not shrink its widget below the minimum size hint,
    which would cut items off instead of eliding or wrapping them.
    """

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, super().minimumSizeHint().height())


class _ActivityRow(AYContainer):
    """Compact one-event row: who did what and when, plus the subject.

    Args:
        user_name: Username, used for the avatar.
        user_full_name: Name displayed next to the avatar.
        user_src: Path to the avatar image.
        verb: What the user did, hidden when the row is too narrow.
        date: Date of the event in ISO format.
        tooltip: Description of the event.
        card: Show the subject on a card, like the body of a comment.
        **kwargs: Forwarded to ``AYContainer``.
    """

    thumbnail_min_row_width = 230

    def __init__(
        self,
        user_name: str,
        user_full_name: str,
        user_src: str,
        verb: str,
        date: str,
        tooltip: str,
        card: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=4 if card else 2,
            **kwargs,
        )
        self.setToolTip(tooltip)
        # Widget hidden when the row is too narrow to fit it
        self.thumbnail: QtWidgets.QWidget | None = None
        self._header = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=8,
        )
        header = self._header
        self.user_icon = AYUserImage(
            size=20,
            src=user_src,
            name=user_name,
            full_name=user_full_name,
            outline=False,
        )
        header.add_widget(self.user_icon)
        self._name_label = AYLabel(
            user_full_name,
            bold=True,
            elide_mode=Qt.TextElideMode.ElideRight,
        )
        self._verb_label = AYLabel(verb, dim=True, rel_text_size=-1)
        self._date_label = AYLabel(
            _relative_date(date), dim=True, rel_text_size=-2
        )
        header.add_widget(self._name_label)
        header.add_widget(self._verb_label)
        header.addStretch(1)
        header.add_widget(self._date_label)
        self.add_widget(header)

        if card:
            self.detail = AYContainer(
                layout=AYContainer.Layout.HBox,
                variant=AYContainer.Variants.High,
                layout_spacing=6,
                layout_margin=8,
            )
            self.add_widget(self.detail)
            return

        self.detail = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=6,
        )
        # Align the detail line with the name, past the avatar
        self.detail._layout.setContentsMargins(28, 0, 0, 0)
        self.add_widget(self.detail)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.thumbnail is not None:
            self.thumbnail.setVisible(
                event.size().width() >= self.thumbnail_min_row_width
            )
        # The verb is dropped before the name gets elided
        spacing = self._header._layout.spacing()
        # An eliding label reports a size hint smaller than its text
        font = self._name_label.font()
        font.setBold(True)
        name_width = QtGui.QFontMetrics(font).horizontalAdvance(
            self._name_label.text()
        )
        # Avatar, 3 labels and the stretch between them
        needed = (
            20
            + max(name_width, self._name_label.sizeHint().width())
            + self._verb_label.sizeHint().width()
            + self._date_label.sizeHint().width()
            + 5 * spacing
        )
        self._verb_label.setVisible(needed <= event.size().width())


class AYActivityStream(AYContainer):
    """Scrollable activity feed with category filter chips.

    Args:
        *args: Forwarded to ``AYContainer``.
        status_definitions: Project statuses as dictionaries with ``text``,
            ``short_text``, ``icon`` and ``color`` keys, used to render
            status changes.
        user_list: Project users, used to render user mentions.
        thumbnail_loader: Non-blocking loader of thumbnails of published
            versions, called as ``(key, on_loaded)`` with the
            ``thumbnail_src`` of a publish that is not a cached image.
        **kwargs: Forwarded to ``AYContainer``.
    """

    def __init__(
        self,
        *args,
        status_definitions: list[dict[str, Any]] | None = None,
        user_list: list[User] | None = None,
        thumbnail_loader: ThumbnailLoader = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("variant", AYContainer.Variants.Low)
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            layout_spacing=8,
            **kwargs,
        )
        self._status_definitions = status_definitions or []
        self._user_list = user_list or []
        self._thumbnail_loader = thumbnail_loader
        self._activities: list[ActivityModel] = []
        self._widgets: list[tuple[ActivityModel, QtWidgets.QWidget]] = []
        self._category = ActivityCategory.ALL
        self._empty_text = "No activity yet"
        self._build()

    def _build(self) -> None:
        filter_bar = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=self.Variants.Low,
            layout_spacing=4,
            parent=self,
        )
        self._filter_group = QtWidgets.QButtonGroup(self)
        self._filter_group.setExclusive(True)
        self._filter_buttons: list[AYButton] = []
        for idx, (label, icon, _category) in enumerate(_FILTERS):
            # Only the first chip has text, the others are icon only to
            #   fit in narrow side panels.
            btn = AYButton(
                label if not icon else "",
                variant=AYButton.Variants.Nav_Small,
                icon=icon or None,
                icon_size=14,
                checkable=True,
                tooltip=label,
                parent=filter_bar,
            )
            btn.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            self._filter_group.addButton(btn, idx)
            self._filter_buttons.append(btn)
            filter_bar.add_widget(btn)
        self._filter_buttons[0].setChecked(True)
        self._filter_group.idClicked.connect(self._on_filter_clicked)
        filter_bar.addStretch(1)
        self._count_label = AYLabel("", dim=True, rel_text_size=-2)
        filter_bar.add_widget(self._count_label)
        filter_bar.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.add_widget(filter_bar)

        self._message_label = AYLabel("", dim=True)
        self._message_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._message_label.setWordWrap(True)
        self._message_label.setContentsMargins(0, 24, 0, 24)
        # The message fills the space of the hidden feed, so the filter
        #   bar stays at the top at its own height.
        self.add_widget(self._message_label, stretch=1)

        self._items = _ItemsContainer(
            layout=AYContainer.Layout.VBox,
            variant=self.Variants.Low,
            layout_spacing=10,
        )
        self._items._layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignTop)
        self._scroll = AYScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll.setWidget(self._items)
        self.add_widget(self._scroll, stretch=1)
        self._refresh_visibility()

    def set_status_definitions(
        self, status_definitions: list[dict[str, Any]]
    ) -> None:
        """Set statuses used to render following status changes.

        Args:
            status_definitions: Project statuses, see class docstring.
        """
        self._status_definitions = status_definitions or []

    def set_user_list(self, user_list: list[User]) -> None:
        """Set users used to render mentions in following comments.

        Args:
            user_list: Project users.
        """
        self._user_list = user_list or []

    def set_message(self, text: str) -> None:
        """Show a message instead of the feed, e.g. while loading.

        Args:
            text: Message to show.
        """
        self.set_activities([], empty_text=text)

    def set_activities(
        self,
        activities: list[ActivityModel],
        empty_text: str = "No activity yet",
    ) -> None:
        """Replace the displayed activities.

        Args:
            activities: Activities in display order.
            empty_text: Message shown when there is nothing to display.
        """
        self._empty_text = empty_text
        self._activities = list(activities)
        self._items.clear()
        self._widgets = []
        for activity in self._activities:
            widget = self._create_widget(activity)
            if widget is None:
                continue
            self._items.add_widget(widget)
            self._widgets.append((activity, widget))
        # Keep items at their own height when the feed is shorter than
        #   the panel, instead of stretching them to fill it.
        self._items.addStretch(1)
        self._scroll.verticalScrollBar().setValue(0)
        self._refresh_visibility()

    def activity_count(
        self, category: ActivityCategory = ActivityCategory.ALL
    ) -> int:
        """Return the number of activities matching a category.

        Args:
            category: Category to count.

        Returns:
            Number of matching activities.
        """
        return sum(
            1 for activity, _ in self._widgets if activity.type & category
        )

    def _create_widget(
        self, activity: ActivityModel
    ) -> QtWidgets.QWidget | None:
        if isinstance(activity, CommentModel):
            return self._create_comment(activity)
        if isinstance(activity, VersionPublishModel):
            row = _ActivityRow(
                activity.user_name,
                activity.user_full_name,
                activity.user_src,
                "published a version",
                activity.date,
                f"Published {activity.product} {activity.version}"
                f"\n{activity.short_date}",
                card=True,
            )
            row.thumbnail = self._fill_publish_card(row.detail, activity)
            return row
        if isinstance(activity, StatusChangeModel):
            row = _ActivityRow(
                activity.user_name,
                activity.user_full_name,
                activity.user_src,
                "changed status",
                activity.date,
                f"Changed status from {activity.old_status}"
                f" to {activity.new_status}\n{activity.short_date}",
            )
            # The previous status is icon only, its name is in the tooltip
            row.detail.add_widget(
                self._create_status(activity.old_status, icon_only=True)
            )
            row.detail.add_widget(AYLabel("→", dim=True))
            row.detail.add_widget(
                self._create_status(activity.new_status), stretch=1
            )
            return row
        return None

    def _create_comment(self, activity: CommentModel) -> AYComment:
        widget = AYComment(data=activity, user_list=self._user_list)
        # Read-only for now, editing needs a write path to the server
        for button in (widget.del_button, widget.edit_button):
            button.setVisible(False)
        widget.reaction.setVisible(False)
        # Reserve no space for the category badge or attachments of
        #   comments that have none.
        widget.top_line.setVisible(bool(activity.category))
        widget.images_container.setVisible(bool(activity.files))
        widget.date.setText(_relative_date(activity.comment_date))
        widget.date.setToolTip(activity.short_date)
        return widget

    def _fill_publish_card(
        self, card: AYContainer, activity: VersionPublishModel
    ) -> AYEntityThumbnail | None:
        """Add product, version, its status and thumbnail to a card.

        Returns:
            The thumbnail widget, if the version has a thumbnail.
        """
        text = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_spacing=2,
        )
        text.add_widget(
            AYLabel(
                activity.product,
                icon="layers",
                icon_size=14,
                elide_mode=Qt.TextElideMode.ElideMiddle,
            )
        )
        version_line = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            layout_spacing=8,
        )
        version_line.add_widget(AYLabel(activity.version, dim=True))
        if activity.status:
            status_label = self._create_status(activity.status)
            status_label.setToolTip(
                f"Current status of the version: {activity.status}"
            )
            version_line.add_widget(status_label, stretch=1)
        else:
            version_line.addStretch(1)
        text.add_widget(version_line)
        card.add_widget(text, stretch=1)

        if not activity.thumbnail_src:
            return None
        thumbnail = AYEntityThumbnail(
            src=activity.thumbnail_src,
            async_file_cacher=self._thumbnail_loader,
            size=(64, 36),
            fill_area=True,
            # No frame around the image, the card is the background
            transparent=True,
            image_inset=0,
        )
        card.add_widget(thumbnail)
        return thumbnail

    def _create_status(
        self, status_name: str, icon_only: bool = False
    ) -> AYLabel:
        status = next(
            (
                status
                for status in self._status_definitions
                if status.get("text") == status_name
            ),
            {},
        )
        icon = status.get("icon", "")
        if icon_only and icon:
            return AYLabel(
                icon=icon,
                icon_color=status.get("color", ""),
                icon_size=14,
                tool_tip=status_name,
            )
        return AYLabel(
            status_name,
            icon=icon,
            icon_color=status.get("color", ""),
            icon_size=14,
            icon_text_spacing=3,
            rel_text_size=-1,
            elide_mode=Qt.TextElideMode.ElideRight,
        )

    def _on_filter_clicked(self, index: int) -> None:
        self._category = _FILTERS[index][2]
        self._refresh_visibility()

    def _refresh_visibility(self) -> None:
        visible = 0
        for activity, widget in self._widgets:
            show = bool(activity.type & self._category)
            widget.setVisible(show)
            visible += show
        total = len(self._widgets)
        self._count_label.setText(
            str(total) if visible == total else f"{visible} of {total}"
        )
        self._count_label.setVisible(bool(total))
        for button in self._filter_buttons:
            button.setEnabled(bool(total))
        self._message_label.setText(
            self._empty_text if not total else "Nothing matches the filter"
        )
        self._message_label.setVisible(not visible)
        self._scroll.setVisible(bool(visible))
