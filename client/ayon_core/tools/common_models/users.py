import json
import collections

from typing import Optional, Generator, Any

import ayon_api
from ayon_api.graphql import FIELD_VALUE, GraphQlQuery, fields_to_dict

from ayon_core.lib import NestedCacheItem


# --- Implementation that should be in ayon-python-api ---
# The implementation is not available in all versions of ayon-python-api.
def users_graphql_query(fields):
    query = GraphQlQuery("Users")
    names_var = query.add_variable("userNames", "[String!]")
    project_name_var = query.add_variable("projectName", "String!")

    users_field = query.add_field_with_edges("users")
    users_field.set_filter("names", names_var)
    users_field.set_filter("projectName", project_name_var)

    nested_fields = fields_to_dict(set(fields))

    query_queue = collections.deque()
    for key, value in nested_fields.items():
        query_queue.append((key, value, users_field))

    while query_queue:
        item = query_queue.popleft()
        key, value, parent = item
        field = parent.add_field(key)
        if value is FIELD_VALUE:
            continue

        for k, v in value.items():
            query_queue.append((k, v, field))
    return query


def get_users(
    project_name: Optional[str] = None,
    usernames: Optional[set[str]] = None,
    fields: Optional[set[str]] = None,
) -> Generator[dict, None, None]:
    """Get Users.

    Only administrators and managers can fetch all users. For other users
        it is required to pass in 'project_name' filter.

    Args:
        project_name (Optional[str]): Project name.
        usernames (Optional[Iterable[str]]): Filter by usernames.
        fields (Optional[Iterable[str]]): Fields to be queried
            for users.

    Returns:
        Generator[dict[str, Any]]: Queried users.

    """
    filters = {}
    if usernames is not None:
        usernames = set(usernames)
        if not usernames:
            return
        filters["userNames"] = list(usernames)

    if project_name is not None:
        filters["projectName"] = project_name

    con = ayon_api.get_server_api_connection()
    if not fields:
        fields = con.get_default_fields_for_type("user")

    query = users_graphql_query(set(fields))
    for attr, filter_value in filters.items():
        query.set_variable_value(attr, filter_value)

    for parsed_data in query.continuous_query(con):
        for user in parsed_data["users"]:
            user["accessGroups"] = json.loads(user["accessGroups"])
            yield user
# --- END of ayon-python-api implementation ---


class UserItem:
    def __init__(
        self,
        username: str,
        full_name: Optional[str],
        email: Optional[str],
        active: bool,
        icon_content_type: Optional[str] = None,
        icon_content: Optional[bytes] = None,
    ):
        self.username = username
        self.full_name = full_name
        self.email = email
        self.active = active
        self.icon_content_type = icon_content_type
        self.icon_content = icon_content

    @classmethod
    def from_entity_data(cls, user_data: dict[str, Any]) -> "UserItem":
        return cls(
            user_data["name"],
            user_data["attrib"]["fullName"],
            user_data["attrib"]["email"],
            user_data["active"],
        )


class UsersModel:
    def __init__(self, controller):
        self._controller = controller
        self._users_cache = NestedCacheItem(default_factory=list)

    def get_user_items(self, project_name: str) -> list[UserItem]:
        """Get user items.

        Returns:
            List[UserItem]: List of user items.

        """
        self._invalidate_cache(project_name)
        return self._users_cache[project_name].get_data()

    def get_user_items_by_name(self, project_name: str) -> dict[str, UserItem]:
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

    def get_user_item_by_username(
        self,
        project_name: str,
        username: str,
    ) -> Optional[UserItem]:
        """Get user item by username.

        Args:
            username (str): Username.
            project_name (Optional[str]): Project name where to look for user.

        Returns:
            Optional[UserItem]: User item or None if not found.

        """
        self._invalidate_cache(project_name)
        for user_item in self.get_user_items(project_name):
            if user_item.username == username:
                return user_item
        return None

    def _invalidate_cache(self, project_name: str) -> None:
        cache = self._users_cache[project_name]
        if cache.is_valid:
            return

        if project_name is None:
            cache.update_data([])
            return

        user_items = []
        for user in get_users(project_name):
            user_item = UserItem.from_entity_data(user)
            avatar_r = ayon_api.get(f"users/{user_item.username}/avatar")
            if avatar_r.status_code == 200:
                user_item.icon_content = avatar_r.content
                user_item.icon_content_type = avatar_r.content_type
            user_items.append(user_item)

        self._users_cache[project_name].update_data(user_items)
