"""AYON server GraphQL capability checks shared across Browser modules.

Kept separate from `ui.browser_queries` (and anything else under `ui`)
so a Qt-free module - such as a column provider - can import this
without pulling in `ayon_core.tools.browser.ui`'s package `__init__`,
which imports the whole Qt window stack.
"""

from __future__ import annotations

import functools

import ayon_api


@functools.cache
def server_supports_representation_filter() -> bool:
    """Return whether the versions resolver takes ``representationFilter``.

    The server's GraphQL schema is introspected rather than its version
    compared, so a development build that has the argument before the
    release that ships it is detected correctly.

    The result is cached for the lifetime of the process. A call that
    raises is not cached, so a failed request is retried on the next call.

    Returns:
        ``True`` when the argument exists. ``False`` when it does not,
        or when the server refuses the introspection query.

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
      }
    }
  }
}
""")
    if response.errors:
        return False
    project_type = response.data["data"].get("__type") or {}
    for field in project_type.get("fields") or []:
        if field.get("name") == "versions":
            return any(
                arg.get("name") == "representationFilter"
                for arg in field.get("args") or []
            )
    return False
