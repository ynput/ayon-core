from typing import Any, Iterable, Iterator, Optional

import ayon_api

from ayon_core.lib import NestedCacheItem, get_ayon_username

NOT_SET = object()


def get_users(
    project_name: str,
    usernames: Optional[Iterable[str]] = None,
) -> Iterator[dict[str, Any]]:
    """Yield user entities for a project, optionally filtered by username.

    Delegates to :func:`ayon_api.get_users`. Used by launcher workfile
    tooltips without going through :class:`UsersModel` cache.
    """
    yield from ayon_api.get_users(
        project_name=project_name,
        usernames=usernames,
    )


class UserItem:
    def __init__(
        self,
        username,
        full_name,
        email,
        avatar_url,
        active,
    ):
        self.username = username
        self.full_name = full_name
        self.email = email
        self.avatar_url = avatar_url
        self.active = active

    @classmethod
    def from_entity_data(cls, user_data):
        # GraphQL may omit `attrib` or individual sub-keys depending on field
        # selection / server version; fall back to safe defaults so the
        # Workfiles tree can still build user labels.
        attrib = user_data.get("attrib") or {}
        username = user_data.get("name") or ""
        return cls(
            username,
            attrib.get("fullName") or username,
            attrib.get("email") or "",
            attrib.get("avatarUrl") or "",
            user_data.get("active", True),
        )


class UsersModel:
    def __init__(self, controller):
        self._current_username = NOT_SET
        self._controller = controller
        self._users_cache = NestedCacheItem(default_factory=list)

    def get_current_username(self) -> Optional[str]:
        if self._current_username is NOT_SET:
            self._current_username = get_ayon_username()
        return self._current_username

    def reset(self) -> None:
        self._users_cache.reset()

    def get_user_items(self, project_name):
        """Get user items.

        Returns:
            List[UserItem]: List of user items.

        """
        self._invalidate_cache(project_name)
        return self._users_cache[project_name].get_data()

    def get_user_items_by_name(self, project_name):
        """Get user items by name.

        Implemented as most of cases using this model will need to find
            user information by username.

        Returns:
            Dict[str, UserItem]: Dictionary of user items by name.

        """
        return {
            user_item.username: user_item
            for user_item in self.get_user_items(project_name)
        }

    def get_user_item_by_username(self, project_name, username):
        """Get user item by username.

        Args:
            username (str): Username.

        Returns:
            Union[UserItem, None]: User item or None if not found.

        """
        self._invalidate_cache(project_name)
        for user_item in self.get_user_items(project_name):
            if user_item.username == username:
                return user_item
        return None

    def _invalidate_cache(self, project_name):
        cache = self._users_cache[project_name]
        if cache.is_valid:
            return

        if project_name is None:
            cache.update_data([])
            return

        self._users_cache[project_name].update_data([
            UserItem.from_entity_data(user)
            for user in ayon_api.get_users(project_name=project_name)
        ])
