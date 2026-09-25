"""AYON server GraphQL capability checks shared across Browser modules.

Kept separate from `ui.browser_queries` (and anything else under `ui`)
so a Qt-free module - such as a column provider - can import this
without pulling in `ayon_core.tools.browser.ui`'s package `__init__`,
which imports the whole Qt window stack.
"""

from __future__ import annotations

import functools
import re

import ayon_api

#: Prefix of the ``sortBy`` argument description of the server's
#: connection resolvers, followed by a comma-separated list of the
#: accepted values.
_SORT_BY_DESCRIPTION_PREFIX = "Sort by one of "


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
