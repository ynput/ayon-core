"""Tests for the Browser's compatibility with older AYON servers.

The Browser supports AYON server 1.15.0 and newer, the legacy Loader is
shown on older servers instead. What an older supported server
lacks is detected by introspecting its GraphQL schema, see
:mod:`ayon_core.tools.browser.server_capabilities`.

Each test of a fallback is marked with ``server_compat``, naming the
last server version that needs the fallback. Once the minimum supported
server is newer than that version, the test and the fallback it covers
can be removed::

    pytest -m server_compat tests/client/ayon_core/tools/browser
"""

from __future__ import annotations

import collections
import logging
import re
from types import SimpleNamespace
from typing import Any

import ayon_api
import pytest

from ayon_core.tools.browser import server_capabilities
from ayon_core.tools.browser.ui import browser_queries
from ayon_core.tools.browser.ui._browser_table import BrowserTable
from ayon_core.tools.browser.ui._browser_toolbar import Customize
from ayon_core.tools.browser.ui.browser_controller import (
    BrowserWidgetController,
)
from ayon_core.tools.browser.ui.browser_group_by import (
    GROUP_BY_STATUS_KEY,
    GroupByOption,
)

#: Arguments of the ``ProjectNode.versions`` and ``ProjectNode.products``
#: resolvers of server 1.15.0, taken from the ayon-backend source.
_ARGUMENTS_1_15_0: dict[str, tuple[str, ...]] = {
    "versions": (
        "first", "after", "last", "before", "ids", "version", "versions",
        "statuses", "tags", "productIds", "taskIds", "folderIds",
        "includeFolderChildren", "authors", "latestOnly", "heroOnly",
        "heroOrLatestOnly", "hasReviewables", "featuredOnly", "hasLinks",
        "search", "filter", "taskFilter", "productFilter", "sortBy",
    ),
    "products": (
        "first", "after", "last", "before", "ids", "hasLinks", "folderIds",
        "includeFolderChildren", "names", "namesCi", "nameEx", "pathEx",
        "productTypes", "productBaseTypes", "statuses", "tags", "search",
        "filter", "versionFilter", "taskFilter", "sortBy",
    ),
}

#: Arguments the resolvers gained since, by the server version that
#: added them.
_ADDED_ARGUMENTS: dict[str, dict[str, tuple[str, ...]]] = {
    "1.15.5": {
        "versions": ("calculateStatistics", "calculateSpecificStatistics"),
        "products": ("calculateStatistics", "calculateSpecificStatistics"),
    },
    "1.16.1": {
        "versions": (
            "hasHero", "featuredOnlyEntityType", "latestPerFolder",
            "folderFilter",
        ),
        "products": ("folderFilter",),
    },
    "1.16.5": {
        "versions": ("includeInternalFolder",),
        "products": ("includeInternalFolder",),
    },
    "1.16.7": {
        "versions": ("representationFilter", "visibility"),
        "products": ("hasReviewables", "visibility"),
    },
}

#: A server that has every argument the Browser uses.
_CURRENT_SERVER = "1.16.7"


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _server_arguments(server_version: str) -> dict[str, dict[str, str]]:
    """Return the resolver arguments of a server version.

    Returns:
        Argument descriptions by argument name, by field name - like
        ``server_capabilities._get_project_fields_args``.
    """
    arguments = {
        field: list(names) for field, names in _ARGUMENTS_1_15_0.items()
    }
    for added_in, added in _ADDED_ARGUMENTS.items():
        if _version_tuple(added_in) > _version_tuple(server_version):
            continue
        for field, names in added.items():
            arguments[field].extend(names)
    return {
        field: dict.fromkeys(names, "")
        for field, names in arguments.items()
    }


@pytest.fixture
def use_server(monkeypatch):
    """Make the capability checks see the schema of a server version."""

    def _use_server(server_version: str) -> dict[str, dict[str, str]]:
        arguments = _server_arguments(server_version)
        monkeypatch.setattr(
            server_capabilities,
            "_get_project_fields_args",
            lambda: arguments,
        )
        return arguments

    return _use_server


def _assert_query_matches_server(
    query: str,
    field: str,
    server_arguments: dict[str, dict[str, str]],
) -> set[str]:
    """Assert a query is valid for the arguments a server has.

    A server rejects a query that passes an argument it does not know,
    as well as one that declares a variable it does not use.

    Returns:
        The arguments the query passes to the field.
    """
    assert "__OPTIONAL" not in query

    header, body = query.split(") {", 1)
    declared = set(re.findall(r"\$(\w+)\s*:", header))
    used = set(re.findall(r"\$(\w+)", body))
    assert declared == used

    match = re.search(rf"\b{field}\(\n(.*?)\n\s*\) {{", body, re.DOTALL)
    assert match is not None
    field_arguments = set(re.findall(r"^\s*(\w+):", match.group(1), re.M))
    assert field_arguments
    assert field_arguments - set(server_arguments[field]) == set()
    return field_arguments


# ----------------------------------------------------------------------
# Capability checks
# ----------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    (
        "server_version",
        "statistics",
        "folder_filter",
        "latest_per_folder",
        "representation_filter",
    ),
    [
        pytest.param(
            "1.15.0", False, False, False, False,
            marks=pytest.mark.server_compat("1.15.4"),
        ),
        pytest.param(
            "1.15.4", False, False, False, False,
            marks=pytest.mark.server_compat("1.15.4"),
        ),
        pytest.param(
            "1.15.5", True, False, False, False,
            marks=pytest.mark.server_compat("1.16.0"),
        ),
        pytest.param(
            "1.16.0", True, False, False, False,
            marks=pytest.mark.server_compat("1.16.0"),
        ),
        pytest.param(
            "1.16.1", True, True, True, False,
            marks=pytest.mark.server_compat("1.16.6"),
        ),
        pytest.param(
            "1.16.6", True, True, True, False,
            marks=pytest.mark.server_compat("1.16.6"),
        ),
        pytest.param(_CURRENT_SERVER, True, True, True, True),
    ],
)
def test_server_capabilities(
    use_server,
    server_version: str,
    statistics: bool,
    folder_filter: bool,
    latest_per_folder: bool,
    representation_filter: bool,
) -> None:
    use_server(server_version)

    assert (
        server_capabilities.server_supports_version_statistics()
        is statistics
    )
    assert (
        server_capabilities.server_supports_folder_filter() is folder_filter
    )
    assert (
        server_capabilities.server_supports_latest_per_folder()
        is latest_per_folder
    )
    assert (
        server_capabilities.server_supports_representation_filter()
        is representation_filter
    )


@pytest.mark.unit
@pytest.mark.server_compat("1.16.6")
def test_capabilities_are_unsupported_without_introspection(
    monkeypatch,
) -> None:
    """A server refusing the introspection query is treated as old."""
    monkeypatch.setattr(
        server_capabilities, "_get_project_fields_args", lambda: {}
    )

    assert not server_capabilities.server_supports_version_statistics()
    assert not server_capabilities.server_supports_folder_filter()
    assert not server_capabilities.server_supports_latest_per_folder()
    assert not server_capabilities.server_supports_representation_filter()
    _assert_query_matches_server(
        browser_queries.get_versions_query(),
        "versions",
        _server_arguments("1.15.0"),
    )


# ----------------------------------------------------------------------
# Queries
# ----------------------------------------------------------------------

_OPTIONAL_VERSIONS_ARGUMENTS = {
    "folderFilter", "latestPerFolder", "representationFilter"
}

_QUERY_SERVERS = [
    pytest.param(
        "1.15.0", set(), marks=pytest.mark.server_compat("1.16.0")
    ),
    pytest.param(
        "1.16.0", set(), marks=pytest.mark.server_compat("1.16.0")
    ),
    pytest.param(
        "1.16.1",
        {"folderFilter", "latestPerFolder"},
        marks=pytest.mark.server_compat("1.16.6"),
    ),
    pytest.param(
        "1.16.6",
        {"folderFilter", "latestPerFolder"},
        marks=pytest.mark.server_compat("1.16.6"),
    ),
    pytest.param(_CURRENT_SERVER, _OPTIONAL_VERSIONS_ARGUMENTS),
]


@pytest.mark.unit
@pytest.mark.parametrize(("server_version", "optional"), _QUERY_SERVERS)
def test_versions_query_matches_server(
    use_server, server_version: str, optional: set[str]
) -> None:
    server_arguments = use_server(server_version)

    query = browser_queries.get_versions_query(
        {"thumb", "status", "folderName", "attr:folder:fps"}
    )

    arguments = _assert_query_matches_server(
        query, "versions", server_arguments
    )
    assert arguments & _OPTIONAL_VERSIONS_ARGUMENTS == optional


@pytest.mark.unit
@pytest.mark.parametrize(
    ("server_version", "optional"),
    # Servers up to 1.15.4 have no statistics to query at all, see
    # 'test_group_counts_are_not_queried_without_statistics'.
    [
        param
        for param in _QUERY_SERVERS
        if param.values[0] != "1.15.0"
    ],
)
@pytest.mark.parametrize("include_product", [False, True])
def test_version_group_counts_query_matches_server(
    use_server,
    server_version: str,
    optional: set[str],
    include_product: bool,
) -> None:
    server_arguments = use_server(server_version)

    query = browser_queries.get_version_group_counts_query(
        include_product=include_product
    )

    arguments = _assert_query_matches_server(
        query, "versions", server_arguments
    )
    assert "calculateSpecificStatistics" in arguments
    assert arguments & _OPTIONAL_VERSIONS_ARGUMENTS == optional


@pytest.mark.unit
@pytest.mark.parametrize(
    ("server_version", "has_folder_filter"),
    [
        pytest.param(
            "1.15.0", False, marks=pytest.mark.server_compat("1.16.0")
        ),
        pytest.param(
            "1.16.0", False, marks=pytest.mark.server_compat("1.16.0")
        ),
        pytest.param("1.16.1", True),
        pytest.param(_CURRENT_SERVER, True),
    ],
)
def test_products_query_matches_server(
    use_server, server_version: str, has_folder_filter: bool
) -> None:
    server_arguments = use_server(server_version)

    query = browser_queries.get_products_query()

    arguments = _assert_query_matches_server(
        query, "products", server_arguments
    )
    assert ("folderFilter" in arguments) is has_folder_filter


# ----------------------------------------------------------------------
# Group counts
# ----------------------------------------------------------------------


class GroupCountsStub:
    """Just enough of the controller to fetch the group counts."""

    _server_supports = BrowserWidgetController._server_supports
    _get_group_counts = BrowserWidgetController._get_group_counts

    def __init__(self) -> None:
        self.log = logging.getLogger(__name__)
        self._current_project = "project"
        self._selected_folder_ids: list[str] = []
        self._include_folder_children = False
        self._latest_per_folder = False
        self.queries: list[str] = []

    def _get_query_filters(self) -> dict[str, Any]:
        return {
            "version_filter": "",
            "product_filter": "",
            "task_filter": "",
            "folder_filter": "",
            "representation_filter": "",
            "featured_only": None,
            "search": None,
            "version_ids": None,
            "has_reviewables": None,
        }

    def query_graphql(self, query: str, variables: dict[str, Any]):
        self.queries.append(query)
        return SimpleNamespace(
            errors=None,
            data={"data": {"project": {"versions": {"fieldStats": [{
                "columnName": "status",
                "valueFilledCount": 3,
                "valueNotFilledCount": 0,
                "distribution": [{"value": "Approved", "count": 3}],
            }]}}}},
        )


_STATUS_GROUP = GroupByOption(GROUP_BY_STATUS_KEY, "Status")


@pytest.mark.unit
@pytest.mark.server_compat("1.15.4")
@pytest.mark.parametrize("server_version", ["1.15.0", "1.15.4"])
def test_group_counts_are_not_queried_without_statistics(
    use_server, monkeypatch, server_version: str
) -> None:
    """Groups fall back to the grouping metadata on these servers."""
    use_server(server_version)
    stub = GroupCountsStub()
    monkeypatch.setattr(ayon_api, "get_server_api_connection", lambda: stub)

    assert stub._get_group_counts(_STATUS_GROUP) is None
    assert stub.queries == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "server_version",
    [
        pytest.param("1.15.5", marks=pytest.mark.server_compat("1.16.0")),
        pytest.param(_CURRENT_SERVER),
    ],
)
def test_group_counts_are_queried_with_statistics(
    use_server, monkeypatch, server_version: str
) -> None:
    server_arguments = use_server(server_version)
    stub = GroupCountsStub()
    monkeypatch.setattr(ayon_api, "get_server_api_connection", lambda: stub)

    group_counts = stub._get_group_counts(_STATUS_GROUP)

    assert group_counts is not None
    assert group_counts.counts == {"Approved": 3}
    assert len(stub.queries) == 1
    _assert_query_matches_server(
        stub.queries[0], "versions", server_arguments
    )


# ----------------------------------------------------------------------
# User interface
# ----------------------------------------------------------------------


class FiltersStub:
    """Just enough of the table to build its filter schema."""

    _build_filters = BrowserTable._build_filters

    def __init__(
        self, folder_filter: bool, representation_filter: bool
    ) -> None:
        attribute = {"type": "string", "title": "Attribute"}
        self._controller = SimpleNamespace(
            supports_folder_filter=folder_filter,
            supports_representation_filter=representation_filter,
            attributes_by_scope={
                "version": {"versionAttr": attribute},
                "folder": {"folderAttr": attribute},
                "representation": {"representationAttr": attribute},
            },
            get_extension_filters=lambda: [],
        )

    def _enum_filter_values(self) -> dict[str, list[str]]:
        return collections.defaultdict(list)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("folder_filter", "representation_filter", "entities"),
    [
        # Servers up to 1.16.0
        pytest.param(
            False, False,
            ["Product", "Version", "Task"],
            marks=pytest.mark.server_compat("1.16.0"),
        ),
        # Servers 1.16.1 up to 1.16.6
        pytest.param(
            True, False,
            ["Product", "Version", "Folder", "Task"],
            marks=pytest.mark.server_compat("1.16.6"),
        ),
        pytest.param(
            True, True,
            ["Product", "Version", "Folder", "Task", "Representation"],
        ),
    ],
)
def test_filters_leave_out_unsupported_entities(
    folder_filter: bool,
    representation_filter: bool,
    entities: list[str],
) -> None:
    filters = FiltersStub(folder_filter, representation_filter)

    entries = filters._build_filters()

    assert list(dict.fromkeys(entry.entity for entry in entries)) == entities
    keys = {entry.key for entry in entries}
    assert "attr:version:versionAttr" in keys
    assert ("folderName" in keys) is folder_filter
    assert ("attr:folder:folderAttr" in keys) is folder_filter
    assert ("representationName" in keys) is representation_filter
    assert (
        "attr:representation:representationAttr" in keys
    ) is representation_filter


class FakeCheckBox:
    """Stand-in for the checkbox, no QApplication needed."""

    def __init__(self) -> None:
        self.checked = False
        self.enabled = True
        self.tooltip = ""

    def blockSignals(self, block: bool) -> bool:
        return False

    def setChecked(self, checked: bool) -> None:
        self.checked = checked

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def setToolTip(self, tooltip: str) -> None:
        self.tooltip = tooltip


@pytest.mark.unit
@pytest.mark.parametrize(
    ("supported", "checked", "enabled"),
    [
        pytest.param(
            False, False, False,
            marks=pytest.mark.server_compat("1.16.0"),
        ),
        pytest.param(True, True, True),
    ],
)
def test_latest_per_folder_is_disabled_when_unsupported(
    supported: bool, checked: bool, enabled: bool
) -> None:
    customize = SimpleNamespace(latest_per_folder_ui=FakeCheckBox())

    Customize.set_latest_per_folder(customize, True, supported=supported)

    checkbox = customize.latest_per_folder_ui
    assert checkbox.checked is checked
    assert checkbox.enabled is enabled
    assert ("1.16.1" in checkbox.tooltip) is not supported
    # The setting itself is kept, so it is not lost from a saved view.
    assert customize._latest_per_folder is True


# ----------------------------------------------------------------------
# Legacy Loader on servers too old for the Browser
# ----------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize(
    ("server_version", "supported"),
    [
        pytest.param(
            (1, 14, 0, "", ""), False,
            marks=pytest.mark.server_compat("1.14.5"),
        ),
        pytest.param(
            (1, 14, 5, "", ""), False,
            marks=pytest.mark.server_compat("1.14.5"),
        ),
        pytest.param((1, 15, 0, "", ""), True),
        pytest.param((1, 16, 8, "", "DEVELOP"), True),
    ],
)
def test_server_supports_browser(
    monkeypatch, server_version: tuple[Any, ...], supported: bool
) -> None:
    monkeypatch.setattr(
        ayon_api, "get_server_version_tuple", lambda: server_version
    )

    assert server_capabilities.server_supports_browser() is supported


@pytest.mark.unit
@pytest.mark.server_compat("1.14.5")
def test_legacy_loader_is_forced_on_unsupported_server(
    monkeypatch, caplog
) -> None:
    """Not even the environment variable opens the Browser there."""
    from ayon_core.tools.utils import host_tools

    monkeypatch.setattr(
        ayon_api, "get_server_version_tuple", lambda: (1, 14, 5, "", "")
    )
    monkeypatch.setattr(ayon_api, "get_server_version", lambda: "1.14.5")
    monkeypatch.setenv("AYON_USE_LEGACY_LOADER", "0")
    # AYON loggers do not propagate to the root logger pytest captures.
    monkeypatch.setattr(
        host_tools, "Logger", SimpleNamespace(get_logger=logging.getLogger)
    )

    with caplog.at_level(logging.WARNING):
        assert host_tools.use_legacy_loader() is True
    assert "requires AYON server 1.15.0" in caplog.text


@pytest.mark.unit
def test_legacy_loader_is_optional_on_supported_server(monkeypatch) -> None:
    from ayon_core.tools.utils import host_tools

    monkeypatch.setattr(
        ayon_api, "get_server_version_tuple", lambda: (1, 15, 0, "", "")
    )

    monkeypatch.setenv("AYON_USE_LEGACY_LOADER", "0")
    assert host_tools.use_legacy_loader() is False
    monkeypatch.setenv("AYON_USE_LEGACY_LOADER", "1")
    assert host_tools.use_legacy_loader() is True
