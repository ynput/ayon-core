"""AYON server GraphQL capability checks shared across Browser modules.

Kept separate from `ui.browser_queries` (and anything else under `ui`)
so a Qt-free module - such as a column provider - can import this
without pulling in `ayon_core.tools.browser.ui`'s package `__init__`,
which imports the whole Qt window stack.

The Browser supports AYON server 1.15.0 and newer. What older supported
servers lack, and the Browser does without on them:

- Up to 1.15.4: version statistics, so group headers show the counts of
  the grouping metadata instead of the counts matching the filters.
- Up to 1.16.0: the ``folderFilter`` and ``latestPerFolder`` arguments,
  so there are no Folder filters and no "Latest per folder" option.
- Up to 1.16.6: the ``representationFilter`` argument, so there are no
  Representation filters.
- Any: ``sortBy`` values the server does not list.

Server 1.14 and older can't be supported the same way: they lack more
than optional arguments, e.g. filtering by product base type (1.15.0),
hero versions (1.14.4) and featured versions (1.13.0). The legacy Loader
is shown on those servers instead, see `server_supports_browser`.
"""

from __future__ import annotations

import functools
import re

import ayon_api

#: Prefix of the ``sortBy`` argument description of the server's
#: connection resolvers, followed by a comma-separated list of the
#: accepted values.
_SORT_BY_DESCRIPTION_PREFIX = "Sort by one of "

#: Oldest AYON server version the Browser works with.
BROWSER_MINIMUM_SERVER_VERSION = (1, 15, 0)


# TODO: Backwards compatibility for AYON server < 1.15.0.
#   Remove this once 1.15.0 is the minimum supported server.
def server_supports_browser() -> bool:
    """Return whether the server is new enough for the Browser.

    Unlike the other checks this one compares the server version: what
    older servers lack, e.g. the filter keys they accept, is not part of
    the GraphQL schema.

    Returns:
        ``True`` when the server is 1.15.0 or newer.
    """
    server_version = ayon_api.get_server_version_tuple()
    return tuple(server_version[:3]) >= BROWSER_MINIMUM_SERVER_VERSION


@functools.cache
def _get_project_fields_args() -> dict[str, dict[str, str]]:
    """Return arguments of the ``ProjectNode`` GraphQL fields.

    The server's GraphQL schema is introspected rather than its version
    compared, so a development build that has an argument before the
    release that ships it is detected correctly.

    The result is cached for the lifetime of the process. A call that
    raises is not cached, so a failed request is retried on the next call.

    Returns:
        Argument descriptions by argument name, by field name. Empty when
        the server refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    con = ayon_api.get_server_api_connection()
    if not con:
        raise RuntimeError("No server connection")
    response = con.query_graphql("""
query ProjectNodeArguments {
  __type(name: "ProjectNode") {
    fields {
      name
      args {
        name
        description
      }
    }
  }
}
""")
    if response.errors:
        return {}
    project_type = response.data["data"].get("__type") or {}
    return {
        field["name"]: {
            arg["name"]: arg.get("description") or ""
            for arg in field.get("args") or []
            if arg.get("name")
        }
        for field in project_type.get("fields") or []
        if field.get("name")
    }


def _get_versions_field_args() -> dict[str, str]:
    """Return arguments of the ``ProjectNode.versions`` GraphQL field.

    Returns:
        Argument descriptions by argument name. Empty when the server
        refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return _get_project_fields_args().get("versions", {})


def get_server_query_arguments(field_name: str) -> frozenset[str]:
    """Return the argument names of a ``ProjectNode`` GraphQL field.

    Args:
        field_name: Field of the project node, e.g. ``"versions"``.

    Returns:
        The argument names. Empty when the server refuses the
        introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return frozenset(_get_project_fields_args().get(field_name, {}))


# TODO: Backwards compatibility for AYON server < 1.16.1.
#   Remove this once 1.16.1 is the minimum supported server.
def server_supports_folder_filter() -> bool:
    """Return whether the versions resolver takes ``folderFilter``.

    The argument was added in server 1.16.1, to both the versions and
    the products resolver.

    Returns:
        ``True`` when the argument exists. ``False`` when it does not,
        or when the server refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return "folderFilter" in _get_versions_field_args()


# TODO: Backwards compatibility for AYON server < 1.16.1.
#   Remove this once 1.16.1 is the minimum supported server.
def server_supports_latest_per_folder() -> bool:
    """Return whether the versions resolver takes ``latestPerFolder``.

    The argument was added in server 1.16.1.

    Returns:
        ``True`` when the argument exists. ``False`` when it does not,
        or when the server refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return "latestPerFolder" in _get_versions_field_args()


# TODO: Backwards compatibility for AYON server < 1.15.5.
#   Remove this once 1.15.5 is the minimum supported server.
def server_supports_version_statistics() -> bool:
    """Return whether the versions resolver calculates statistics.

    Statistics (``calculateSpecificStatistics`` and the ``fieldStats``
    they return) were added in server 1.15.5.

    Returns:
        ``True`` when the argument exists. ``False`` when it does not,
        or when the server refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return "calculateSpecificStatistics" in _get_versions_field_args()


# TODO: Backwards compatibility for AYON server < 1.16.7.
#   Remove this once 1.16.7 is the minimum supported server.
def server_supports_representation_filter() -> bool:
    """Return whether the versions resolver takes ``representationFilter``.

    Returns:
        ``True`` when the argument exists. ``False`` when it does not,
        or when the server refuses the introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return "representationFilter" in _get_versions_field_args()


def parse_sort_by_options(description: str) -> frozenset[str]:
    """Parse the values listed in a ``sortBy`` argument description.

    Args:
        description: Description such as ``"Sort by one of a, b, c"``.

    Returns:
        The listed values, empty when the description does not list any.
    """
    if not description.startswith(_SORT_BY_DESCRIPTION_PREFIX):
        return frozenset()
    values = description[len(_SORT_BY_DESCRIPTION_PREFIX):]
    return frozenset(
        value
        for value in re.split(r"\s*,\s*", values.strip())
        if value
    )


def get_server_versions_sort_options() -> frozenset[str]:
    """Return the ``sortBy`` values the versions resolver lists.

    The server raises an error for a ``sortBy`` value it does not know,
    and older servers know fewer of them, so optional sort values are
    only sent when the server lists them. Values the resolver handles
    specially (``status`` and ``attrib.*``) are not part of the list.

    Returns:
        The listed ``sortBy`` values. Empty when the server refuses the
        introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return parse_sort_by_options(
        _get_versions_field_args().get("sortBy", "")
    )


def get_server_products_sort_options() -> frozenset[str]:
    """Return the ``sortBy`` values the products resolver lists.

    Same as :func:`get_server_versions_sort_options`, for products.

    Returns:
        The listed ``sortBy`` values. Empty when the server refuses the
        introspection query.

    Raises:
        RuntimeError: If there is no server connection.
    """
    return parse_sort_by_options(
        _get_project_fields_args().get("products", {}).get("sortBy", "")
    )
