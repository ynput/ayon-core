"""Shared, non-blocking source of round user-avatar pixmaps.

Widgets that show a single user can simply build an :class:`AYUserImage`.
Painters that render many users - table cells, item delegates - need a
pixmap on the paint path without touching the network, which is what this
cache provides: initials are available immediately, and the real avatar
replaces them once it has been downloaded in the background.
"""

from __future__ import annotations

import tempfile

import ayon_api
from qtpy import QtCore, QtGui, shiboken

from ayon_core.lib import Logger

from .task_queue import AsyncTask, get_task_queue
from .user_image import AYUserImage
from ..image_cache import ImageCache

log = Logger.get_logger(__name__)

#: Background priority - avatars are decoration, never blocking content.
_FETCH_PRIORITY = 10


def _fetch_avatar_file(user_name: str) -> str:
    """Download a user avatar and return the cached file path.

    Args:
        user_name: Login name of the user.

    Returns:
        Path to the cached image file, or ``""`` when the server has no
        avatar for this user.
    """
    connection = ayon_api.get_server_api_connection()
    if connection is None:
        return ""
    response = connection.raw_get(f"users/{user_name}/avatar")
    content = getattr(response, "content", None)
    if not content:
        return ""
    content_type = getattr(response, "content_type", "") or ""
    ext = ".jpg" if "jpeg" in content_type else ".png"
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as handle:
        handle.write(content)
        return handle.name


class UserAvatarCache(QtCore.QObject):
    """Cache of round avatar pixmaps keyed by user name and size.

    :meth:`pixmap` never blocks: it returns an initials avatar right away
    and schedules the real image, emitting :attr:`avatar_updated` when the
    download lands so views can repaint.
    """

    #: Emitted with the login name once a downloaded avatar replaced the
    #: initials placeholder for that user.
    avatar_updated = QtCore.Signal(str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._pixmaps: dict[tuple[str, int], QtGui.QPixmap] = {}
        self._sources: dict[str, str] = {}
        self._pending: set[str] = set()

    def clear(self) -> None:
        """Drop every cached pixmap and downloaded source path."""
        self._pixmaps.clear()
        self._sources.clear()

    def pixmap(
        self,
        user_name: str,
        full_name: str,
        size: int,
    ) -> QtGui.QPixmap | None:
        """Return the avatar for *user_name*, scheduling a download once.

        Args:
            user_name: Login name, used as the cache key and for initials.
            full_name: Display name the initials are derived from.
            size: Avatar diameter in logical pixels.

        Returns:
            A rendered pixmap, or ``None`` when there is nothing to draw.
        """
        if not user_name:
            return None
        key = (user_name, int(size))
        pixmap = self._pixmaps.get(key)
        if pixmap is None:
            pixmap = self._render(user_name, full_name, int(size))
            self._pixmaps[key] = pixmap
        self._schedule_fetch(user_name)
        return pixmap

    def _render(
        self, user_name: str, full_name: str, size: int
    ) -> QtGui.QPixmap:
        """Render one avatar through :class:`AYUserImage`.

        The widget is only a renderer here - it is never shown - so the
        avatars stay identical to the ones the rest of the UI draws.
        """
        widget = AYUserImage(
            src=self._sources.get(user_name, ""),
            name=user_name,
            full_name=full_name or user_name,
            size=size,
            outline=False,
        )
        pixmap = widget.pxm
        widget.deleteLater()
        return pixmap

    def _schedule_fetch(self, user_name: str) -> None:
        """Queue a one-off background download of *user_name*'s avatar."""
        if user_name in self._sources or user_name in self._pending:
            return
        self._pending.add(user_name)

        def _work() -> str:
            cache = ImageCache.get_instance()
            try:
                return cache.get(
                    f"user-avatar/{user_name}",
                    lambda: _fetch_avatar_file(user_name),
                )
            except Exception:  # noqa: BLE001 - avatars are optional
                log.debug(
                    "Could not fetch avatar for %r", user_name, exc_info=True
                )
                return ""

        def _done(file_path: str) -> None:
            # The cache outlives no view, but a queued download can land
            # after the owning widget was torn down.
            if shiboken.isValid(self):
                self._on_avatar_ready(user_name, file_path)

        get_task_queue().enqueue(
            AsyncTask(
                name=f"fetch_avatar:{user_name}",
                function=_work,
                callback=_done,
                priority=_FETCH_PRIORITY,
                context_id="user-avatars",
                cancellable=False,
            )
        )

    def _on_avatar_ready(self, user_name: str, file_path: str) -> None:
        """Swap the initials placeholder for the downloaded avatar."""
        self._pending.discard(user_name)
        if not file_path:
            # Remember the miss so the download is not retried per repaint.
            self._sources[user_name] = ""
            return
        self._sources[user_name] = file_path
        for key in [k for k in self._pixmaps if k[0] == user_name]:
            del self._pixmaps[key]
        self.avatar_updated.emit(user_name)
