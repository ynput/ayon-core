import ayon_api

from ayon_core.lib import CacheItem


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
        return cls(
            user_data["name"],
            user_data["attrib"]["fullName"],
            user_data["attrib"]["email"],
            user_data["attrib"]["avatarUrl"],
            user_data["active"],
        )


class UsersModel:
    def __init__(self, controller):
        self._controller = controller
        self._users_cache = CacheItem(default_factory=list)

    def get_user_items(self):
        """Get user items.

        Returns:
            List[UserItem]: List of user items.

        """
        self._invalidate_cache()
        return self._users_cache.get_data()

    def get_user_items_by_name(self):
        """Get user items by name.

        Implemented as most of cases using this model will need to find
            user information by username.

        Returns:
            Dict[str, UserItem]: Dictionary of user items by name.

        """
        return {
            user_item.username: user_item
            for user_item in self.get_user_items()
        }

    def get_user_item_by_username(self, username):
        """Get user item by username.

        Args:
            username (str): Username.

        Returns:
            Union[UserItem, None]: User item or None if not found.

        """
        self._invalidate_cache()
        for user_item in self.get_user_items():
            if user_item.username == username:
                return user_item
        return None

    def _invalidate_cache(self):
        if self._users_cache.is_valid:
            return
        self._users_cache.update_data([
            UserItem.from_entity_data(user)
            for user in ayon_api.get_users()
        ])
