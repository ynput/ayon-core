import json
import collections

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


def get_users(project_name=None, usernames=None, fields=None):
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
        self._users_cache = NestedCacheItem(default_factory=list)

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
            for user in get_users(project_name)
        ])
