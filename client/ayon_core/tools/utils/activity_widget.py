"""Activity feed of entities, fetched from the server in the background."""

from __future__ import annotations

from typing import Callable, Iterable

from qtpy import QtGui, shiboken

from ayon_core.lib import Logger
from ayon_core.tools.common_models.activities import (
    ActivitiesModel,
    ActivityFeed,
    get_version_thumbnail_path,
)
from ayon_core.ui.components.activity_stream import AYActivityStream
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.components.user_avatars import UserAvatarCache

log = Logger.get_logger(__name__)


class ActivityWidget(AYActivityStream):
    """Activity feed showing comments and events of the set entities.

    Nothing is fetched while the widget is hidden, so it is free to keep
    in a tab that the user may never open.

    Args:
        *args: Forwarded to ``AYActivityStream``.
        activities_model: Model used to fetch the feed, created if not
            passed.
        avatar_cache: Source of user avatars, created if not passed. Pass
            the cache of the tool to share it with its other views.
        **kwargs: Forwarded to ``AYActivityStream``.
    """

    def __init__(
        self,
        *args,
        activities_model: ActivitiesModel | None = None,
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
        self._activities_model = activities_model or ActivitiesModel()
        self._context_id = f"activity_widget_{id(self)}"
        self._project_name = ""
        self._entity_ids: tuple[str, ...] = ()
        self._no_context_text = "Nothing selected"
        # Key of the latest request, older results are ignored
        self._request_key = ""
        # Key of the context that is displayed or being fetched
        self._loaded_key: str | None = None
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
        """Fetch a version thumbnail in the background."""
        widget = self

        def _on_loaded(path: str) -> None:
            if path and shiboken.isValid(widget):
                on_loaded(path)

        get_task_queue().enqueue(
            AsyncTask(
                name=f"activity_widget_thumbnail_{key}",
                function=lambda: get_version_thumbnail_path(key),
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
            self.set_message(self._no_context_text)
            return

        self.set_message("Loading activity…")
        model = self._activities_model
        project_name = self._project_name
        entity_ids = self._entity_ids
        widget = self

        def _fetch() -> ActivityFeed | None:
            try:
                return model.get_activity_feed(project_name, entity_ids)
            except Exception:
                log.warning("Failed to fetch activities", exc_info=True)
                return None

        def _on_loaded(feed: ActivityFeed | None) -> None:
            if not shiboken.isValid(widget) or widget._request_key != key:
                return
            if feed is None:
                # Allow to retry by selecting the context again
                widget._loaded_key = None
                widget.set_message("Could not load activity")
                return
            widget.set_status_definitions(feed.statuses)
            widget.set_user_list(feed.users)
            widget.set_activities(feed.activities)

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
