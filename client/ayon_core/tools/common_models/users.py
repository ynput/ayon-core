from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ayon_api

from ayon_core.lib import NestedCacheItem, get_ayon_username

NOT_SET = object()


@dataclass
class UserItem:
    username: str
    full_name: str | None
    email: str | None
    avatar_url: str | None
    active: bool

    @classmethod
    def from_entity_data(cls, user_data: dict[str, Any]) -> UserItem:
        return cls(
            user_data["name"],
            user_data["attrib"]["fullName"],
            user_data["attrib"]["email"],
            user_data["attrib"]["avatarUrl"],
            user_data["active"],
        )

    def to_data(self) -> dict[str, Any]:
        return dict(
            username=self.username,
            full_name=self.full_name,
            email=self.email,
            avatar_url=self.avatar_url,
            active=self.active,
        )

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> UserItem:
        return cls(**data)


class UsersModel:
    def __init__(self, controller):
        self._current_username = NOT_SET
        self._controller = controller
        self._users_cache = NestedCacheItem(default_factory=list)

    def get_current_username(self) -> str | None:
        if self._current_username is NOT_SET:
            self._current_username = get_ayon_username()
        return self._current_username

    def reset(self) -> None:
        self._users_cache.reset()

    def get_user_items(self, project_name: str | None) -> list[UserItem]:
        """Get user items.

        Returns:
            list[UserItem]: List of user items.

        """
        self._invalidate_cache(project_name)
        return self._users_cache[project_name].get_data()

    def get_user_items_by_name(
        self, project_name: str | None
    ) -> dict[str, UserItem]:
        """Get user items by name.

        Implemented as most of cases using this model will need to find
            user information by username.

        Returns:
            dict[str, UserItem]: Dictionary of user items by name.

        """
        return {
            user_item.username: user_item
            for user_item in self.get_user_items(project_name)
        }

    def get_user_item_by_username(
        self, project_name: str | None, username: str
    ) -> UserItem | None:
        """Get user item by username.

        Args:
            project_name (str | None): Project name.
            username (str): Username.

        Returns:
            UserItem | None: User item or None if not found.

        """
        self._invalidate_cache(project_name)
        for user_item in self.get_user_items(project_name):
            if user_item.username == username:
                return user_item
        return None

    def _invalidate_cache(self, project_name: str | None) -> None:
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
