"""Cache of user avatars on local storage.

Avatars are downloaded once per machine: the cache is a directory shared
by all AYON processes of the user, like the thumbnails cache.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time

import ayon_api

from ayon_core.lib.local_settings import get_launcher_local_dir

_MIME_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpeg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
# Marks a user that has no avatar on the server
_NO_AVATAR_EXTENSION = ".none"


class AvatarsCache:
    """Cache of user avatars on local storage.

    Each server has its own subfolder, as usernames are unique only within
    a server. An avatar has no id that would change with the image, so a
    cached avatar is downloaded again when it is older than
    :attr:`lifetime`. Users without an avatar are remembered for the same
    time, so the server is not asked for them over and over.
    """

    # Lifetime of a cached avatar (in seconds)
    # - default 1 day
    lifetime = 24 * 60 * 60

    def __init__(self) -> None:
        self._avatars_dir: str | None = None

    def get_avatars_dir(self) -> str:
        """Root directory where avatars of the current server are stored.

        Returns:
            Path to the directory.
        """
        if self._avatars_dir is None:
            server_url = ayon_api.get_base_url() or ""
            server_hash = hashlib.sha1(
                server_url.encode("utf-8")
            ).hexdigest()[:12]
            self._avatars_dir = get_launcher_local_dir(
                "avatars", server_hash
            )
        return self._avatars_dir

    def get_avatar_filepath(self, username: str) -> tuple[bool, str | None]:
        """Get the cached avatar of a user.

        Args:
            username: Name of the user.

        Returns:
            If a valid cache entry exists, and the path to the image. The
            path is None for a user that is known to have no avatar.
        """
        base_path = self._get_base_path(username)
        min_time = time.time() - self.lifetime
        for ext in (*_MIME_EXTENSIONS.values(), _NO_AVATAR_EXTENSION):
            filepath = base_path + ext
            try:
                modified = os.path.getmtime(filepath)
            except OSError:
                continue
            if modified < min_time:
                continue
            if ext == _NO_AVATAR_EXTENSION:
                return True, None
            return True, filepath
        return False, None

    def store_avatar(
        self, username: str, content: bytes | None, mime_type: str | None
    ) -> str | None:
        """Store the avatar of a user, or that the user has none.

        Args:
            username: Name of the user.
            content: Content of the image, None if there is no avatar.
            mime_type: Mime type of the image.

        Returns:
            Path to the cached image, None if there is no avatar.
        """
        ext = _MIME_EXTENSIONS.get(mime_type or "")
        if not content or ext is None:
            content, ext = b"", _NO_AVATAR_EXTENSION

        base_path = self._get_base_path(username)
        avatars_dir = os.path.dirname(base_path)
        os.makedirs(avatars_dir, exist_ok=True)
        # Other processes may read the file while it is written
        fd, tmp_path = tempfile.mkstemp(dir=avatars_dir, suffix=".tmp")
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        filepath = base_path + ext
        os.replace(tmp_path, filepath)

        # Remove the previous avatar stored with a different extension
        for other_ext in (*_MIME_EXTENSIONS.values(), _NO_AVATAR_EXTENSION):
            if other_ext == ext:
                continue
            try:
                os.remove(base_path + other_ext)
            except OSError:
                pass

        if ext == _NO_AVATAR_EXTENSION:
            return None
        return filepath

    def _get_base_path(self, username: str) -> str:
        filename = re.sub(r"[^a-zA-Z0-9_.@-]", "_", username)
        return os.path.join(self.get_avatars_dir(), filename)


class _CacheItems:
    avatars_cache = AvatarsCache()


def get_user_avatar_path(username: str) -> str | None:
    """Get path to the avatar image of a user.

    The avatar is downloaded if it is not cached, so it should not be
    called from the main thread of a tool.

    Args:
        username: Name of the user.

    Returns:
        Path to the avatar image or None if the user has no avatar.
    """
    if not username:
        return None

    cache = _CacheItems.avatars_cache
    is_cached, filepath = cache.get_avatar_filepath(username)
    if is_cached:
        return filepath

    con = ayon_api.get_server_api_connection()
    response = con.raw_get(f"users/{username}/avatar")
    content = getattr(response, "content", None)
    if getattr(response, "status_code", 200) != 200:
        content = None
    return cache.store_avatar(
        username, content, getattr(response, "content_type", None)
    )
