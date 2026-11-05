"""Activity feed of entities, fetched from the server in the background."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable, Protocol

from qtpy import QtGui, shiboken

from ayon_core.lib import Logger
from ayon_core.ui.components.activity_stream import AYActivityStream
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.components.user_avatars import UserAvatarCache
from ayon_core.ui.data_models import (
    AnnotationModel,
    CommentModel,
    FileModel,
    StatusChangeModel,
    User,
    VersionPublishModel,
)

if TYPE_CHECKING:
    from ayon_core.tools.common_models import (
        ActivityItem,
        StatusItem,
        UserItem,
    )

log = Logger.get_logger(__name__)

# Shown instead of a value that is not filled
NOT_AVAILABLE = "n/a"


class ActivityController(Protocol):
    """Controller methods used by the activity widget.

    Implement them in the controller of a tool to show the widget in it.
    All of them may query the server and are called outside of the main
    thread.
    """

    def get_activity_items(
        self,
        project_name: str,
        entity_ids: list[str] | set[str],
        limit: int = 50,
    ) -> list[ActivityItem]:
        """Latest activities of entities.

        Args:
            project_name: Project name.
            entity_ids: Ids of entities to get activities for.
            limit: Maximum number of activities.

        Returns:
            Activities sorted from the newest to the oldest, see
                ``ActivitiesModel.get_activity_items``.
        """

    def get_project_status_items(
        self, project_name: str, sender: str | None = None
    ) -> list[StatusItem]:
        """Status items for a project.

        Args:
            project_name: Project name.
            sender: Who requested the items.

        Returns:
            Project statuses, see ``ProjectsModel.get_project_status_items``.
        """

    def get_user_items(self, project_name: str | None) -> list[UserItem]:
        """User items for a project.

        Args:
            project_name: Project name.

        Returns:
            Users of the project, see ``UsersModel.get_user_items``.
        """

    def get_version_thumbnail_path(
        self, project_name: str, version_id: str, thumbnail_id: str
    ) -> str | None:
        """Path to a thumbnail of a version, downloaded if needed.

        Args:
            project_name: Project name.
            version_id: Version id.
            thumbnail_id: Thumbnail id of the version.

        Returns:
            Path to the image file, or ``None`` if it is not available.
        """


@dataclass
class _ActivityFeed:
    """Data of a feed as received from the controller."""

    activity_items: list[ActivityItem]
    status_items: list[StatusItem]
    user_items: list[UserItem]


def _text(value: Any) -> str:
    return NOT_AVAILABLE if value is None else str(value)


def _create_users(user_items: list[UserItem]) -> list[User]:
    return [
        User(
            name=user_item.username,
            # Activities are matched to users by 'short_name'
            short_name=user_item.username,
            full_name=user_item.full_name or user_item.username,
            email=user_item.email or "",
        )
        for user_item in user_items
    ]


def _create_status_definitions(
    status_items: list[StatusItem],
) -> list[dict[str, Any]]:
    return [
        {
            "text": status_item.name,
            "short_text": status_item.short,
            "icon": status_item.icon,
            "color": status_item.color,
        }
        for status_item in status_items
    ]


def _create_comment(
    item: ActivityItem, user_name: str, user_full_name: str
) -> CommentModel:
    # Frames of annotations by ids of their files
    ranges: dict[str | None, list[int] | None] = {}
    annotations = []
    for annotation in item.annotations:
        annotations.append(
            AnnotationModel(
                id=_text(annotation.annotation_id),
                range=annotation.frame_range or NOT_AVAILABLE,
                composite=_text(annotation.composite),
                transparent=_text(annotation.transparent),
            )
        )
        ranges[annotation.composite] = annotation.frame_range
        ranges[annotation.transparent] = annotation.frame_range
    files = [
        FileModel(
            id=_text(file_item.file_id),
            mime=_text(file_item.mime),
            frame=(ranges.get(file_item.file_id) or (-1, -1))[0],
        )
        for file_item in item.files
    ]
    return CommentModel(
        activity_id=item.activity_id,
        user_full_name=user_full_name,
        user_name=user_name,
        comment=_text(item.body),
        comment_date=_text(item.updated_at),
        category=item.category or "",
        files=files,
        annotations=annotations,
    )


def _create_activity(
    item: ActivityItem, full_names_by_username: dict[str, str]
) -> CommentModel | VersionPublishModel | StatusChangeModel | None:
    """Convert an activity item to the model of its widget.

    Args:
        item: Activity item.
        full_names_by_username: Full names of project users.

    Returns:
        Model for the activity stream, ``None`` for an activity type
            that the stream can not show.
    """
    user_name = _text(item.author)
    user_full_name = full_names_by_username.get(user_name, user_name)
    if item.activity_type == "comment":
        return _create_comment(item, user_name, user_full_name)
    if item.activity_type == "version.publish":
        return VersionPublishModel(
            activity_id=item.activity_id,
            user_full_name=user_full_name,
            user_name=user_name,
            version=_text(item.version_name),
            product=_text(item.product_name),
            date=_text(item.updated_at),
            status=item.version_status or "",
        )
    if item.activity_type == "status.change":
        return StatusChangeModel(
            activity_id=item.activity_id,
            user_full_name=user_full_name,
            user_name=user_name,
            product=_text(item.product_name),
            version=_text(item.version_name),
            old_status=_text(item.old_status),
            new_status=_text(item.new_status),
            date=_text(item.updated_at),
        )
    return None


class ActivityWidget(AYActivityStream):
    """Activity feed showing comments and events of the set entities.

    Nothing is fetched while the widget is hidden, so it is free to keep
    in a tab that the user may never open.

    Args:
        controller: Controller of the tool, the source of all data of
            the feed.
        *args: Forwarded to ``AYActivityStream``.
        avatar_cache: Source of user avatars, created if not passed. Pass
            the cache of the tool to share it with its other views. The
            downloaded avatars are shared by all caches either way.
        **kwargs: Forwarded to ``AYActivityStream``.
    """

    def __init__(
        self,
        controller: ActivityController,
        *args,
        avatar_cache: UserAvatarCache | None = None,
        **kwargs,
    ) -> None:
        kwargs.setdefault("thumbnail_loader", self._load_thumbnail)
        super().__init__(*args, avatar_cache=avatar_cache, **kwargs)
        if avatar_cache is None:
            # Created after 'super().__init__' as it is parented to
            #   the widget
            self._avatar_cache = UserAvatarCache(self)
            self._avatar_cache.avatar_updated.connect(self._refresh_avatars)
        self._controller = controller
        self._context_id = f"activity_widget_{id(self)}"
        self._project_name = ""
        self._entity_ids: tuple[str, ...] = ()
        self._no_context_text = "Nothing selected"
        # Key of the latest request, older results are ignored
        self._request_key = ""
        # Key of the context that is displayed or being fetched
        self._loaded_key: str | None = None
        # Key of the context of the feed that is displayed
        self._displayed_key: str | None = None
        # Project name, version id and thumbnail id by 'thumbnail_key' of
        #   displayed publishes
        self._thumbnail_sources: dict[str, tuple[str, str, str]] = {}
        self.set_message(self._no_context_text)

    def set_context(
        self,
        project_name: str | None,
        entity_ids: Iterable[str],
        no_context_text: str = "Nothing selected",
    ) -> None:
        """Change entities to show the activity of.

        Args:
            project_name: Project name.
            entity_ids: Ids of entities, e.g. of a task or of versions.
            no_context_text: Message shown when there are no entities.
        """
        self._project_name = project_name or ""
        self._entity_ids = tuple(sorted(set(entity_ids)))
        self._no_context_text = no_context_text
        if self.isVisible():
            self._load()

    def refresh(self) -> None:
        """Fetch the feed of the current context again."""
        self._loaded_key = None
        if self.isVisible():
            self._load()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._load()

    def _load_thumbnail(
        self, key: str, on_loaded: Callable[[str], None]
    ) -> None:
        """Ask the controller for a version thumbnail in the background."""
        source = self._thumbnail_sources.get(key)
        if source is None:
            return
        controller = self._controller
        widget = self

        def _fetch() -> str | None:
            try:
                return controller.get_version_thumbnail_path(*source)
            except Exception:
                log.debug("Failed to fetch thumbnail %r", key, exc_info=True)
                return None

        def _on_loaded(path: str | None) -> None:
            if path and shiboken.isValid(widget):
                on_loaded(path)

        get_task_queue().enqueue(
            AsyncTask(
                name=f"activity_widget_thumbnail_{key}",
                function=_fetch,
                callback=_on_loaded,
                priority=5,
                cancellable=True,
            )
        )

    def _load(self) -> None:
        key = f"{self._project_name}|{','.join(self._entity_ids)}"
        if key == self._loaded_key:
            return
        self._loaded_key = key
        self._request_key = key

        task_queue = get_task_queue()
        # Only the latest context is relevant
        task_queue.clear_context_tasks(self._context_id)
        if not self._project_name or not self._entity_ids:
            self._displayed_key = None
            self.set_message(self._no_context_text)
            return

        # A refresh keeps the displayed feed until the new one arrives,
        #   so its rows are reused and the scroll position is kept.
        if key != self._displayed_key:
            self._displayed_key = None
            self.set_message("Loading activity…")
        controller = self._controller
        project_name = self._project_name
        entity_ids = list(self._entity_ids)
        widget = self

        def _fetch() -> _ActivityFeed | None:
            try:
                return _ActivityFeed(
                    controller.get_activity_items(project_name, entity_ids),
                    controller.get_project_status_items(project_name),
                    controller.get_user_items(project_name),
                )
            except Exception:
                log.warning("Failed to fetch activities", exc_info=True)
                return None

        def _on_loaded(feed: _ActivityFeed | None) -> None:
            if not shiboken.isValid(widget) or widget._request_key != key:
                return
            if feed is None:
                # Allow to retry by selecting the context again
                widget._loaded_key = None
                widget._displayed_key = None
                widget.set_message("Could not load activity")
                return
            widget._set_feed(project_name, feed)
            widget._displayed_key = key

        task_queue.enqueue(
            AsyncTask(
                name="activity_widget_feed",
                function=_fetch,
                callback=_on_loaded,
                priority=1,
                context_id=self._context_id,
                cancellable=True,
            )
        )

    def _set_feed(self, project_name: str, feed: _ActivityFeed) -> None:
        """Show a fetched feed."""
        users = _create_users(feed.user_items)
        full_names_by_username = {user.name: user.full_name for user in users}
        thumbnail_sources = {}
        activities = []
        for item in feed.activity_items:
            activity = _create_activity(item, full_names_by_username)
            if activity is None:
                continue
            if (
                isinstance(activity, VersionPublishModel)
                and item.version_id
                and item.thumbnail_id
            ):
                # The Browser tool stores version thumbnails in the image
                #   cache with this key, they are shown without asking
                #   the controller
                key = f"{project_name}/{item.version_id}/{item.thumbnail_id}"
                thumbnail_sources[key] = (
                    project_name, item.version_id, item.thumbnail_id
                )
                activity.thumbnail_key = key
            activities.append(activity)

        self._thumbnail_sources = thumbnail_sources
        # Activity widgets are created with the statuses and users
        self.set_status_definitions(
            _create_status_definitions(feed.status_items)
        )
        self.set_user_list(users)
        self.set_activities(activities)
