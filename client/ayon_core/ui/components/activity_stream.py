"""Feed of comments, publishes and status changes of an entity.

The stream is display-only: it is handed already converted activity models
and knows nothing about the server, so it can be reused by any tool and
previewed with sample data. Whatever needs the server is left to the
owner: it saves edited comments, and downloads attachments of the rows
reported by :meth:`AYActivityStream.get_visible_activities`.
"""

from __future__ import annotations

import re
from typing import Any, Union

from qtpy import QtCore, QtWidgets

from ..data_models import (
    ActivityCategory,
    CommentModel,
    StatusChangeModel,
    VersionPublishModel,
)
from .buttons import AYButton
from .comment import (
    AYComment,
    AYPublish,
    AYStatusChange,
    ThumbnailLoader,
)
from .comment_completion import MentionSource
from .container import AYContainer
from .label import AYLabel
from .scroll_area import AYScrollArea
from .tab_bar import AYTabBar
from .table_filter import AYFilterBar, FilterCriterion, filter_values_match
from .table_model import FilterEntry, ValueOption
from .user_avatars import UserAvatarCache

ActivityModel = Union[CommentModel, VersionPublishModel, StatusChangeModel]

# Filters of the feed, as in the feed of the web frontend
_SEARCH_KEY = "text"
# Types of activities, an activity of any of the picked types is shown
_TYPE_FILTERS: dict[str, ActivityCategory] = {
    "comments": ActivityCategory.COMMENT,
    "versions": ActivityCategory.VERSION_PUBLISH,
    "updates": ActivityCategory.STATUS_CHANGE,
    "checklists": ActivityCategory.CHECKLIST,
}
# Checkboxes of checklists in comments, the group is the check mark
_CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[([xX ])\]", re.MULTILINE)


def _create_filters(with_categories: bool) -> list[FilterEntry]:
    filters = [
        FilterEntry("comments", "Comments", icon="chat", flag=True),
        FilterEntry("versions", "Versions", icon="layers", flag=True),
        FilterEntry(
            "updates", "Updates", icon="arrow_circle_right", flag=True
        ),
        FilterEntry(
            "checklists", "Checklists", icon="check_circle", flag=True
        ),
        FilterEntry(
            "attachments", "Attachments", icon="attach_file", flag=True
        ),
    ]
    if with_categories:
        filters.append(
            FilterEntry(
                "category",
                "Category",
                icon="label",
                show_has_value_filters=True,
            )
        )
    filters.extend((
        FilterEntry("author", "User", icon="person"),
        FilterEntry(_SEARCH_KEY, "Text", icon="search", text_search=True),
    ))
    return filters


def _get_search_text(activity: ActivityModel) -> str:
    """Text of an activity that the text filter searches in."""
    if isinstance(activity, CommentModel):
        parts = (activity.user_full_name, activity.comment)
    elif isinstance(activity, VersionPublishModel):
        parts = (activity.user_full_name, activity.product, activity.version)
    else:
        parts = (
            activity.user_full_name,
            activity.product,
            activity.version,
            activity.old_status,
            activity.new_status,
        )
    return " ".join(part for part in parts if part)


def _get_filter_value(activity: ActivityModel, key: str) -> Any:
    """Value of an activity that the filter of a key compares."""
    if key == "attachments":
        return bool(getattr(activity, "files", None))
    if key == "category":
        return getattr(activity, "category", "")
    if key == "author":
        return activity.user_name
    if key == _SEARCH_KEY:
        return _get_search_text(activity)
    return None


def _matches_criteria(
    activity: ActivityModel, criteria: list[FilterCriterion]
) -> bool:
    """Whether an activity is shown with the criteria of the filter bar.

    Picked types of activities are alternatives, other criteria all have
    to match.
    """
    picked_types = [
        _TYPE_FILTERS[criterion.key]
        for criterion in criteria
        if criterion.key in _TYPE_FILTERS and not criterion.exclude
    ]
    if picked_types and not any(
        activity.type & category for category in picked_types
    ):
        return False
    for criterion in criteria:
        if criterion.key in _TYPE_FILTERS:
            matched = bool(activity.type & _TYPE_FILTERS[criterion.key])
            if criterion.exclude and matched:
                return False
            continue
        value = _get_filter_value(activity, criterion.key)
        if isinstance(value, bool):
            # Flag, e.g. activity has attachments
            matched = value
        else:
            matched = filter_values_match(
                value, criterion.values, criterion.use_substring
            )
        if matched == criterion.exclude:
            return False
    return True


class _ItemsContainer(AYContainer):
    """Feed content that never forces the scroll area wider.

    A scroll area does not shrink its widget below the minimum size hint,
    which would cut items off instead of eliding or wrapping them.
    """

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(0, super().minimumSizeHint().height())


class AYActivityStream(AYContainer):
    """Scrollable activity feed with a search and filter bar.

    The bar offers the filters of the feed of the web frontend: types of
    activities, attachments, comment categories, users and text. Comments
    and checklists can also be toggled by the buttons next to it. Filters
    are kept when other activities are set, e.g. of another entity.

    Args:
        *args: Forwarded to ``AYContainer``.
        status_definitions: Project statuses as dictionaries with ``text``,
            ``short_text``, ``icon`` and ``color`` keys, used to render
            status changes.
        mention_source: Users, versions and tasks to mention when editing a
            comment, can be shared with other comment editors.
        thumbnail_loader: Non-blocking loader of thumbnails of published
            versions, called as ``(key, on_loaded)`` with the
            ``thumbnail_key`` of a publish that is not in the image cache.
        avatar_cache: Source of user avatars downloaded from the server,
            users are shown with their initials without it.
        variant: Background variant of the feed.
        editable: Comments can be edited and deleted and their checklists
            toggled. The stream only reports it with
            :attr:`comment_edited` and :attr:`comment_deleted`, the owner
            saves the change and sets the updated activities. A stream
            that is not editable is read-only.
        compact: Fit narrow side panels: status changes show the previous
            status as an icon only.
        stick_to_bottom: For feeds with the newest activity last. A new
            feed starts at its end, and a feed that is scrolled to its
            end stays there when rows are added or change their height.
        lazy_attachments: The owner downloads attachments of comments on
            demand and reports them with :meth:`refresh_attachment`.
            Attachments that are not available locally are shown as
            placeholders, so rows keep their height when they arrive.
        **kwargs: Forwarded to ``AYContainer``.

    Signals:
        comment_edited (CommentModel): A comment of an editable stream was
            edited, or one of its checkboxes toggled.
        comment_deleted (CommentModel): Deletion of a comment of an
            editable stream was confirmed by the user.
        viewport_changed (): Other rows may be in view, e.g. after
            scrolling or a refresh. Emitted with a delay, so it is cheap
            to react to.
    """

    comment_edited = QtCore.Signal(object)
    comment_deleted = QtCore.Signal(object)
    viewport_changed = QtCore.Signal()

    avatar_size = 20
    # Delay of 'viewport_changed' in milliseconds
    viewport_changed_delay = 150

    def __init__(
        self,
        *args,
        status_definitions: list[dict[str, Any]] | None = None,
        mention_source: MentionSource | None = None,
        thumbnail_loader: ThumbnailLoader = None,
        avatar_cache: UserAvatarCache | None = None,
        variant: AYContainer.Variants = AYContainer.Variants.Low,
        editable: bool = False,
        compact: bool = True,
        stick_to_bottom: bool = False,
        lazy_attachments: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=variant,
            layout_spacing=8,
            **kwargs,
        )
        self._status_definitions = status_definitions or []
        self._mention_source = mention_source or MentionSource(self)
        self._thumbnail_loader = thumbnail_loader
        self._editable = editable
        self._compact = compact
        self._stick_to_bottom = stick_to_bottom
        self._lazy_attachments = lazy_attachments
        # The feed is at its end and follows it, see 'stick_to_bottom'
        self._pinned_to_bottom = stick_to_bottom
        self._avatar_cache = avatar_cache
        if avatar_cache is not None:
            avatar_cache.avatar_updated.connect(self._refresh_avatars)
        self._activities: list[ActivityModel] = []
        self._widgets: list[tuple[ActivityModel, QtWidgets.QWidget]] = []
        # Indexes of rows in '_widgets' by id of their attached files
        self._rows_by_file_id: dict[str, list[int]] = {}
        # Pages shown instead of the feed, see 'add_page'
        self._tab_bar: AYTabBar | None = None
        self._pages: list[QtWidgets.QWidget] = []
        self._page: QtWidgets.QWidget | None = None
        self._criteria: list[FilterCriterion] = []
        self._has_categories = False
        self._empty_text = "No activity yet"
        self._build()

    def _build(self) -> None:
        self._filter_bar = AYFilterBar(
            _create_filters(self._has_categories),
            parent=self,
            values_getter=self._get_filter_values,
            placeholder="Search and filter",
            search_key=_SEARCH_KEY,
            compact=True,
        )
        self._filter_bar.add_quick_action("comments", "chat", "Comments")
        self._checklists_button = self._filter_bar.add_quick_action(
            "checklists", "check_circle", "Checklists"
        )
        self._filter_bar.filters_changed.connect(self._on_filters_changed)
        self.add_widget(self._filter_bar)

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

        self._viewport_timer = QtCore.QTimer(self)
        self._viewport_timer.setSingleShot(True)
        self._viewport_timer.setInterval(self.viewport_changed_delay)
        self._viewport_timer.timeout.connect(self.viewport_changed)
        scroll_bar = self._scroll.verticalScrollBar()
        scroll_bar.valueChanged.connect(self._on_scroll_value_changed)
        scroll_bar.rangeChanged.connect(self._on_scroll_range_changed)
        self._refresh_visibility()

    def add_page(
        self,
        label: str,
        widget: QtWidgets.QWidget,
        icon: str | None = None,
    ) -> AYButton:
        """Add a page that is shown instead of the feed.

        Pages are tabs, laid out like the tabs of the web details panel:
        the feed is an icon on the left, pages are on the right, e.g. to
        show details of the entity.

        Args:
            label: Label of the tab of the page.
            widget: Content of the page.
            icon: Icon of the tab, shown instead of the label.

        Returns:
            The button of the tab that shows the page.
        """
        if self._tab_bar is None:
            self._tab_bar = AYTabBar(variant=self.Variants.Low)
            self._tab_bar.add_tab("Activity", icon="forum", icon_only=True)
            self._tab_bar.add_stretch()
            self._tab_bar.current_changed.connect(self._on_tab_changed)
            self.insert_widget(0, self._tab_bar)
        index = self._tab_bar.add_tab(label, icon=icon, icon_only=True)
        widget.setVisible(False)
        self.add_widget(widget, stretch=1)
        self._pages.append(widget)
        return self._tab_bar.button(index)

    def set_status_definitions(
        self, status_definitions: list[dict[str, Any]]
    ) -> None:
        """Set statuses used to render status changes and publishes.

        Rows that are already displayed are updated.

        Args:
            status_definitions: Project statuses, see class docstring.
        """
        status_definitions = status_definitions or []
        if status_definitions == self._status_definitions:
            return
        self._status_definitions = status_definitions
        self._recreate_rows((AYPublish, AYStatusChange))

    def mention_source(self) -> MentionSource:
        """Users, versions and tasks to mention when editing a comment."""
        return self._mention_source

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

        Active filters are kept, and apply to the new activities.

        Rows of activities that are displayed already and did not change
        are reused, matched by ``activity_id``, so a refresh of the same
        feed only creates rows for what is new. The scroll position is
        kept in that case, the feed scrolls back to the top only when
        none of the previous activities is left. With ``stick_to_bottom``
        it scrolls to the end instead, and stays there if it was there.

        Args:
            activities: Activities in display order.
            empty_text: Message shown when there is nothing to display.
        """
        self._empty_text = empty_text
        self._activities = list(activities)

        reusable = {
            activity.activity_id: (activity, widget)
            for activity, widget in self._widgets
            if activity.activity_id
        }
        anchor = self._get_scroll_anchor()
        previous_widgets = [widget for _, widget in self._widgets]
        layout = self._items._layout
        # Take everything out of the layout, reused rows are added back
        #   at their new position.
        while layout.count():
            layout.takeAt(0)

        self._widgets = []
        reused_widgets = set()
        for activity in self._activities:
            previous_activity, widget = reusable.pop(
                activity.activity_id, (None, None)
            )
            if widget is None or previous_activity != activity:
                widget = self._create_widget(activity)
                if widget is None:
                    continue
            else:
                reused_widgets.add(widget)
            self._items.add_widget(widget)
            self._widgets.append((activity, widget))

        for widget in previous_widgets:
            if widget not in reused_widgets:
                self._release_widget(widget)

        self._refresh_avatars()
        # Keep items at their own height when the feed is shorter than
        #   the panel, instead of stretching them to fill it.
        self._items.addStretch(1)
        self._rows_by_file_id = {}
        for idx, (activity, _widget) in enumerate(self._widgets):
            for file in getattr(activity, "files", ()):
                self._rows_by_file_id.setdefault(file.id, []).append(idx)

        self._update_filters()
        self._refresh_visibility()
        if self._stick_to_bottom and (
            self._pinned_to_bottom or not reused_widgets
        ):
            self.scroll_to_bottom()
        elif anchor is not None and anchor[0] in reused_widgets:
            self._restore_scroll_anchor(*anchor)
        else:
            self._scroll.verticalScrollBar().setValue(0)

    def scroll_to_bottom(self) -> None:
        """Scroll to the end of the feed.

        With ``stick_to_bottom`` the feed stays there until it is
        scrolled away.
        """
        self._pinned_to_bottom = self._stick_to_bottom
        # The range of the scroll bar is known after the layout is updated
        self._update_items_height()
        scroll_bar = self._scroll.verticalScrollBar()
        scroll_bar.setValue(scroll_bar.maximum())

    def get_visible_activities(self) -> list[ActivityModel]:
        """Return activities of the rows that are in view.

        Use it together with :attr:`viewport_changed` to load data only
        for what the user looks at, e.g. attachments of comments.

        Returns:
            Activities in display order, empty if the feed is not shown.
        """
        if not self._scroll.isVisible():
            return []
        top = self._scroll.verticalScrollBar().value()
        bottom = top + self._scroll.viewport().height()
        output = []
        for activity, widget in self._widgets:
            if widget.isHidden():
                continue
            geometry = widget.geometry()
            if geometry.bottom() < top:
                continue
            if geometry.top() > bottom:
                break
            output.append(activity)
        return output

    def refresh_attachment(self, file_id: str, project_name: str) -> bool:
        """Show an attachment of a comment that became available locally.

        The file is looked up in the image cache with
        :func:`ayon_core.ui.image_cache.make_activity_cache_key`.

        Args:
            file_id: Id of the attached file.
            project_name: Name of the project the file belongs to.

        Returns:
            True if a displayed comment has the attachment.
        """
        refreshed = False
        for idx in self._rows_by_file_id.get(file_id, ()):
            widget = self._widgets[idx][1]
            if not isinstance(widget, AYComment):
                continue
            widget.refresh_image(file_id, None, project_name)
            widget.images_container.setVisible(True)
            refreshed = True
        return refreshed

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

    @staticmethod
    def _release_widget(widget: QtWidgets.QWidget) -> None:
        """Delete a row that is not displayed anymore."""
        widget.setVisible(False)
        widget.setParent(None)
        widget.deleteLater()

    def _recreate_rows(self, widget_types: tuple[type, ...]) -> None:
        """Create rows of given types again, to render changed data."""
        layout = self._items._layout
        for idx, (activity, widget) in enumerate(self._widgets):
            if not isinstance(widget, widget_types):
                continue
            new_widget = self._create_widget(activity)
            layout.replaceWidget(widget, new_widget)
            self._release_widget(widget)
            self._widgets[idx] = (activity, new_widget)
        self._refresh_avatars()
        self._refresh_visibility()

    def _get_scroll_anchor(self) -> tuple[QtWidgets.QWidget, int] | None:
        """Get the first row in view and its offset to the top of the view.

        Returns:
            The row and its offset, None if the feed is at the top or
            nothing is displayed.
        """
        scroll_value = self._scroll.verticalScrollBar().value()
        if not scroll_value:
            return None
        for _, widget in self._widgets:
            if not widget.isVisible():
                continue
            geometry = widget.geometry()
            if geometry.bottom() >= scroll_value:
                return widget, geometry.top() - scroll_value
        return None

    def _restore_scroll_anchor(
        self, widget: QtWidgets.QWidget, offset: int
    ) -> None:
        """Scroll so a row is at the offset it had before a refresh.

        Rows added above the reader would otherwise push the activity
        they are looking at out of view.
        """
        # Positions of the rows are known after the layout is updated
        self._update_items_height()
        scroll_bar = self._scroll.verticalScrollBar()
        scroll_bar.setValue(widget.geometry().top() - offset)

    def _update_items_height(self) -> None:
        """Give the feed the height of its rows right away.

        The scroll area does it with the next layout request, which is
        too late to scroll to a row. Only the height is changed: a change
        of the width, as with ``adjustSize``, would wrap the text of all
        rows again, which is slow for long feeds.
        """
        layout = self._items._layout
        layout.activate()
        width = self._items.width()
        if layout.hasHeightForWidth():
            height = layout.totalHeightForWidth(width)
        else:
            height = layout.totalMinimumSize().height()
        height = max(height, self._scroll.viewport().height())
        self._items.resize(width, height)

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
                compact=self._compact,
            )
        return None

    def _create_comment(self, activity: CommentModel) -> AYComment:
        widget = AYComment(data=activity, mention_source=self._mention_source)
        if self._editable:
            widget.comment_edited.connect(self.comment_edited)
            widget.comment_deleted.connect(self.comment_deleted)
        else:
            for button in (widget.del_button, widget.edit_button):
                button.setVisible(False)
            # A toggled checkbox would look changed without being saved
            widget.text_field.set_checkboxes_enabled(False)
        widget.reaction.setVisible(False)
        # Reserve no space for the category badge or attachments of
        #   comments that have none. The edit buttons are in the same
        #   line as the badge.
        widget.top_line.setVisible(
            bool(activity.category) or self._editable
        )
        # Attachments are shown only if their files are available locally,
        #   the stream does not download them. Placeholders are shown if
        #   the owner does.
        if self._lazy_attachments:
            show_attachments = bool(activity.files)
        else:
            show_attachments = any(
                file.local_path for file in activity.files
            )
        widget.images_container.setVisible(show_attachments)
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

    def _get_filter_values(self, key: str) -> list[ValueOption]:
        """Values of a filter in the displayed activities."""
        options: dict[str, ValueOption] = {}
        for activity, _widget in self._widgets:
            if key == "author" and activity.user_name:
                options.setdefault(
                    activity.user_name,
                    ValueOption(
                        activity.user_name,
                        activity.user_full_name or activity.user_name,
                        icon="person",
                    ),
                )
            elif key == "category" and getattr(activity, "category", ""):
                options.setdefault(
                    activity.category,
                    ValueOption(
                        activity.category,
                        activity.category,
                        icon="crop_square",
                        color=activity.category_color or None,
                    ),
                )
        return sorted(options.values(), key=lambda item: item.label.lower())

    def _update_filters(self) -> None:
        """Update filters and quick actions to the displayed activities."""
        has_categories = any(
            getattr(activity, "category", "")
            for activity, _widget in self._widgets
        )
        if has_categories != self._has_categories:
            self._has_categories = has_categories
            self._filter_bar.set_filters(_create_filters(has_categories))

        # Checked and total checkboxes of all checklists
        marks = [
            mark
            for activity, _widget in self._widgets
            if activity.type & ActivityCategory.CHECKLIST
            for mark in _CHECKBOX_RE.findall(activity.comment)
        ]
        checked = sum(1 for mark in marks if mark != " ")
        self._checklists_button.setText(
            f"{checked}/{len(marks)}" if marks else ""
        )

    def _on_filters_changed(self, criteria: list[FilterCriterion]) -> None:
        self._criteria = list(criteria)
        self._refresh_visibility()

    def _on_tab_changed(self, index: int) -> None:
        # The feed is the first tab
        self._page = self._pages[index - 1] if index else None
        self._refresh_visibility()

    def _on_scroll_value_changed(self, value: int) -> None:
        scroll_bar = self._scroll.verticalScrollBar()
        self._pinned_to_bottom = (
            self._stick_to_bottom and value >= scroll_bar.maximum()
        )
        self._viewport_timer.start()

    def _on_scroll_range_changed(self, _minimum: int, maximum: int) -> None:
        # Rows were added or changed their height, e.g. when a comment
        #   is wrapped or its attachments are loaded.
        if self._pinned_to_bottom:
            self._scroll.verticalScrollBar().setValue(maximum)
        self._viewport_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._viewport_timer.start()

    def _refresh_visibility(self) -> None:
        visible = 0
        for activity, widget in self._widgets:
            show = _matches_criteria(activity, self._criteria)
            widget.setVisible(show)
            visible += show
        total = len(self._widgets)
        on_page = self._page is not None
        self._filter_bar.setVisible(not on_page)
        self._message_label.setText(
            self._empty_text if not total else "Nothing matches the filter"
        )
        self._message_label.setVisible(not visible and not on_page)
        self._scroll.setVisible(bool(visible) and not on_page)
        for page in self._pages:
            page.setVisible(page is self._page)
        self._viewport_timer.start()
