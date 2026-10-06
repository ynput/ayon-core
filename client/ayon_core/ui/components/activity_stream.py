"""Read-only feed of comments, publishes and status changes of an entity.

The stream is display-only: it is handed already converted activity models
and knows nothing about the server, so it can be reused by any tool and
previewed with sample data.
"""

from __future__ import annotations

from typing import Any, Union

from qtpy import QtCore, QtWidgets

from ..data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    User,
    VersionPublishModel,
)
from .buttons import AYButton
from .comment import (
    AYComment,
    AYPublish,
    AYStatusChange,
    ThumbnailLoader,
)
from .container import AYContainer
from .label import AYLabel
from .scroll_area import AYScrollArea
from .user_avatars import UserAvatarCache

ActivityModel = Union[CommentModel, VersionPublishModel, StatusChangeModel]

_FILTERS: tuple[tuple[str, str, ActivityCategory], ...] = (
    ("All", "", ActivityCategory.ALL),
    ("Comments", "chat", ActivityCategory.COMMENT),
    ("Publishes", "layers", ActivityCategory.VERSION_PUBLISH),
    ("Status", "arrow_circle_right", ActivityCategory.STATUS_CHANGE),
)


class _ItemsContainer(AYContainer):
    """Feed content that never forces the scroll area wider.

    A scroll area does not shrink its widget below the minimum size hint,
    which would cut items off instead of eliding or wrapping them.
    """

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, super().minimumSizeHint().height())


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
            ``thumbnail_key`` of a publish that is not in the image cache.
        avatar_cache: Source of user avatars downloaded from the server,
            users are shown with their initials without it.
        **kwargs: Forwarded to ``AYContainer``.
    """

    avatar_size = 20

    def __init__(
        self,
        *args,
        status_definitions: list[dict[str, Any]] | None = None,
        user_list: list[User] | None = None,
        thumbnail_loader: ThumbnailLoader = None,
        avatar_cache: UserAvatarCache | None = None,
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
        self._avatar_cache = avatar_cache
        if avatar_cache is not None:
            avatar_cache.avatar_updated.connect(self._refresh_avatars)
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
        self._refresh_avatars()
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
            return AYPublish(
                data=activity,
                status_definitions=self._status_definitions,
                thumbnail_loader=self._thumbnail_loader,
            )
        if isinstance(activity, StatusChangeModel):
            return AYStatusChange(
                data=activity,
                status_definitions=self._status_definitions,
                compact=True,
            )
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
        return widget

    def _refresh_avatars(self, user_name: str | None = None) -> None:
        """Show avatars from the avatar cache instead of initials.

        Args:
            user_name: Refresh only avatars of this user, all if not set.
        """
        if self._avatar_cache is None:
            return
        for activity, widget in self._widgets:
            if user_name and activity.user_name != user_name:
                continue
            # Initials are returned until the avatar is downloaded
            pixmap = self._avatar_cache.pixmap(
                activity.user_name,
                activity.user_full_name,
                self.avatar_size,
            )
            if pixmap is not None:
                widget.user_icon.setPixmap(pixmap)

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
