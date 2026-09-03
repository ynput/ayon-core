"""Controller for the Reviews widget.

Centralises all business logic and data fetching for the reviews UI.
"""

from __future__ import annotations

import datetime
import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query
from ayon_core.ui.components.table_model import (
    BatchFetchRequest,
    FilterEntry,
    TableColumn,
)
from ayon_core.ui.components.tree_model import TreeNode
from qtpy import QtCore

from ayon_core.lib import Logger
from ayon_core.tools.browser.abstract import ActionItem
from ayon_core.tools.browser.columns import (
    BrowserColumnContext,
    BrowserColumnManager,
    BrowserColumnServices,
    BrowserFilter,
)
from ayon_core.tools.browser.control import LoaderController
from ayon_core.tools.browser.sitesync_columns import (
    SiteSyncBrowserColumnProvider,
)
from ayon_core.tools.browser.view_defaults import BROWSER_VIEW_DEFAULTS
from ayon_core.tools.browser.ui.browser_group_by import (
    BUILTIN_GROUPS,
    GROUP_BY_NONE_KEY,
    GROUP_BY_PRODUCT_KEY,
    GROUP_BY_PRODUCT_TYPE_KEY,
    GROUP_BY_STATUS_KEY,
    GROUP_BY_TAGS_KEY,
    GROUP_BY_TASK_TYPE_KEY,
    GroupByOption,
    GroupBySource,
    build_attribute_groups,
)
from ayon_core.tools.browser.ui.browser_queries import (
    COLUMN_TO_SORT_BY,
    EMPTY_ROW,
    GET_PRODUCTS_QUERY,
    GET_VERSION_GROUP_COUNTS_QUERY,
    get_versions_query,
)
from ayon_core.tools.browser.ui.browser_types import (
    MY_TASKS_FILTER_KEY,
    BrowserSlicerCategory,
)

# Maximum number of pages to fetch when building product group headers.
# Each page contains up to 1 000 products, so this caps the total at
# 50 000 products before a warning is logged.
_MAX_GROUP_PAGES: int = 50


def _normalize_entity_id(value: Any) -> str:
    """Return UUID-like entity IDs in AYON's compact hexadecimal form."""
    text = str(value)
    try:
        return uuid.UUID(text).hex
    except (ValueError, AttributeError):
        return text


def _timestamp_to_date(timestamp: str) -> str:
    """Convert ISO timestamp string to human-readable date.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Formatted date string as DD-MM-YYYY HH:MM:SS.
    """
    if not timestamp:
        return ""
    return datetime.datetime.fromisoformat(timestamp).strftime(
        "%d-%m-%Y %H:%M:%S"
    )


class BrowserController(QtCore.QObject):
    """Controller for the Reviews widget.

    Centralises all business logic and data fetching for the reviews
    UI. Emits signals when state changes so that widgets can react.
    """

    project_changed = QtCore.Signal(str)  # type: ignore
    project_info_changed = QtCore.Signal()  # type: ignore
    category_changed = QtCore.Signal(str)  # type: ignore
    tree_reset_requested = QtCore.Signal()  # type: ignore
    selection_changed = QtCore.Signal(list, list)  # type: ignore
    group_by_options_changed = QtCore.Signal(dict)  # type: ignore
    slicer_filters_changed = QtCore.Signal(set)  # type: ignore

    def __init__(
        self,
        loader_controller: LoaderController,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader_controller = loader_controller
        self._current_project: str = ""
        self._current_category: str = (
            BrowserSlicerCategory.HIERARCHY.value
        )
        self._project_info: dict[str, Any] = {}
        self._review_sessions_cache: list[dict[str, Any]] = []
        self._graphql_has_more: bool = False
        self._graphql_cursor: str = ""
        self._folder_cursors: dict[str, str] = {}
        self._folder_has_more: dict[str, bool] = {}
        self._tree_mode = (
            BROWSER_VIEW_DEFAULTS.group_by_key != GROUP_BY_NONE_KEY
        )
        self._selected_folder_ids: list[str] = []
        self._folder_parent_ids: dict[str, str | None] = {}
        self._review_session_version_ids: list[str] | None = None
        self._version_attributes: dict[str, Any] = {}
        self._attributes_by_scope: dict[
            str, dict[str, dict[str, Any]]
        ] = {}
        self._group_by_options: dict[str, GroupByOption] = {
            option.key: option for option in BUILTIN_GROUPS
        }
        self._group_by_key = BROWSER_VIEW_DEFAULTS.group_by_key
        self._hide_empty_groups = (
            not BROWSER_VIEW_DEFAULTS.show_empty_groups
        )
        self._include_folder_children = (
            BROWSER_VIEW_DEFAULTS.include_children
        )
        self._featured_version_order: list[str] = [
            *BROWSER_VIEW_DEFAULTS.featured_version_order,
        ]
        self._latest_per_folder = BROWSER_VIEW_DEFAULTS.latest_per_folder
        self._active_slicer_filters: set[str] = set()
        self._folder_id_scope: set[str] | None = None
        self._task_id_scope: set[str] | None = None
        self._query_filter_criteria: list[tuple[str, list[str], bool]] = []
        self._requested_column_keys: set[str] | None = None
        column_services = BrowserColumnServices(loader_controller)
        self._column_manager = BrowserColumnManager(
            column_services,
            [SiteSyncBrowserColumnProvider(
                loader_controller,
                column_services,
            )],
            addon_manager=loader_controller.addons_manager,
        )
        self.log = Logger.get_logger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_project(self) -> str:
        """Return the currently active project name."""
        return self._current_project

    @property
    def include_folder_children(self) -> bool:
        """Return whether hierarchy queries include descendant folders."""
        return self._include_folder_children

    def set_include_folder_children(self, enabled: bool) -> None:
        """Set descendant-folder querying for the hierarchy slicer."""
        enabled = bool(enabled)
        if self._include_folder_children == enabled:
            return
        self._include_folder_children = enabled
        self._reset_pagination()

    def set_requested_columns(self, column_keys: set[str]) -> bool:
        """Set visible query columns and return whether they changed."""
        normalized = set(column_keys)
        if self._requested_column_keys == normalized:
            return False
        self._requested_column_keys = normalized
        self._reset_pagination()
        return True

    def get_extension_columns(self) -> list[TableColumn]:
        """Return columns contributed by enabled addons."""
        return self._column_manager.get_columns(self._get_column_context())

    def get_extension_filters(self) -> list[FilterEntry]:
        """Return filters contributed by enabled addons."""
        return self._column_manager.get_filters(self._get_column_context())

    def get_extension_filter_keys(self) -> set[str]:
        """Return filter keys handled locally after row enrichment."""
        return self._column_manager.get_filter_keys(
            self._get_column_context()
        )

    @property
    def current_category(self) -> str:
        """Return the currently active slicer category."""
        return self._current_category

    @property
    def project_info(self) -> dict[str, Any]:
        """Return project metadata dict."""
        return self._project_info

    @property
    def version_attributes(self) -> dict[str, Any]:
        """Return version attributes dict."""
        return self._version_attributes

    @property
    def attributes_by_scope(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return custom attribute definitions grouped by entity scope."""
        return self._attributes_by_scope

    @property
    def has_selection(self) -> bool:
        """Return whether the slicer has at least one selected entity."""
        return bool(self._selected_folder_ids)

    @property
    def tree_mode(self) -> bool:
        """Return whether tree mode is currently active."""
        return self._tree_mode

    @property
    def selected_folder_id(self) -> str:
        """Return the first selected folder ID, or empty string."""
        if self._selected_folder_ids:
            return self._selected_folder_ids[0]
        return ""

    @property
    def group_by(self) -> GroupByOption:
        """Return the current group-by option."""
        return self._group_by_options.get(
            self._group_by_key, self._group_by_options[GROUP_BY_NONE_KEY]
        )

    @property
    def group_by_key(self) -> str:
        """Return key of the current group-by option."""
        return self._group_by_key

    def get_group_by_options(self) -> list[GroupByOption]:
        """Return available group-by options, including custom attrs."""
        return list(self._group_by_options.values())

    def get_folder_id_path(self, folder_id: str) -> list[str]:
        """Return folder IDs from the project root to the target folder."""
        folder_items = self._loader_controller.get_folder_items(
            self._current_project
        )
        path = []
        item = folder_items.get(folder_id)
        while item is not None:
            path.append(item.entity_id)
            item = folder_items.get(item.parent_id)
        path.reverse()
        return path

    @property
    def hide_empty_groups(self) -> bool:
        """Return whether empty group headers should be hidden."""
        return self._hide_empty_groups

    @property
    def featured_version_order(self) -> list[str]:
        """Return the current featured-version priority order.

        Returns:
            A copy of the ordered list of GraphQL featured-version type
            keys (e.g. ``["latestDone", "latest", "hero"]``).
        """
        return list(self._featured_version_order)

    @property
    def latest_per_folder(self) -> bool:
        """Return whether only the latest version per folder is shown."""
        return self._latest_per_folder

    def set_latest_per_folder(self, enabled: bool) -> None:
        """Set whether the query returns one latest version per folder."""
        enabled = bool(enabled)
        if self._latest_per_folder == enabled:
            return
        self._latest_per_folder = enabled
        self._reset_pagination()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_project(self, project_name: str) -> None:
        """Set the active project and refresh data.

        Args:
            project_name: AYON project name to activate.
        """
        if self._current_project == project_name:
            return
        self._current_project = project_name
        self._review_sessions_cache = []
        self._reset_pagination()
        self._selected_folder_ids = []
        self._folder_parent_ids = {}
        # Keep sticky slicer filters (e.g. "My Tasks") active across a
        # project switch, just re-resolved against the new project.
        self._recompute_slicer_filter_scope()
        self._build_project_info()
        self._get_review_session_list()
        self.project_changed.emit(project_name)
        self.project_info_changed.emit()
        self.tree_reset_requested.emit()

    def set_category(self, category: str) -> None:
        """Set the active slicer category.

        Resets per-category state so switching back and forth between
        ``Hierarchy`` and ``Reviews`` never leaves stale group-by or
        tree-mode flags behind.  Reviews are always a flat version list,
        while Hierarchy restores the group-by / tree-mode combination
        derived from the current ``group_by_key``.

        Args:
            category: Category name, e.g. ``"Hierarchy"`` or ``"Reviews"``.
        """
        if self._current_category == category:
            return
        self._current_category = category
        self._selected_folder_ids = []
        self._review_session_version_ids = None

        if category == BrowserSlicerCategory.REVIEWS.value:
            # Reviews are always flat — drop any grouping/tree state that
            # was active in the Hierarchy view so the table fetch path
            # takes the plain flat-version branch.
            self._group_by_key = GROUP_BY_NONE_KEY
            self._tree_mode = False
        else:
            # Restore tree-mode consistent with the active group-by.
            self._tree_mode = self._group_by_key != GROUP_BY_NONE_KEY
        self._reset_pagination()
        self.category_changed.emit(category)
        self.tree_reset_requested.emit()

    def set_slicer_filters(self, keys: set[str]) -> None:
        """Set the active slicer-level filter keys (e.g. "My Tasks").

        Unlike the table's :meth:`set_filter_criteria`, these filters
        scope which folders the Hierarchy tree fetches at all, so
        changing them resets and re-fetches the tree. Unknown keys
        (a filter not currently recognised by
        :meth:`_recompute_slicer_filter_scope`) are stored but simply
        have no effect, so ``SLICER_FILTER_OPTIONS`` can grow without
        this method needing to change.

        Args:
            keys: The full set of currently selected slicer filter
                keys, as reported by the slicer's filter menu.
        """
        if keys == self._active_slicer_filters:
            return
        self._active_slicer_filters = set(keys)
        self._recompute_slicer_filter_scope()
        self._reset_pagination()
        self.slicer_filters_changed.emit(set(self._active_slicer_filters))
        self.tree_reset_requested.emit()

    @property
    def active_slicer_filters(self) -> set[str]:
        """Return the currently active slicer filter keys.

        Used by ``BrowserTable`` to capture the filter selection into
        a saved View (see ``_capture_view_extras``).
        """
        return set(self._active_slicer_filters)

    def _recompute_slicer_filter_scope(self) -> None:
        """Recompute id scopes implied by the active slicer filters.

        Only the ``my_tasks`` key is understood today: it resolves to
        the folders that directly own a task assigned to the current
        user, widened to include every ancestor folder so the tree can
        still be navigated down to them, plus the matching task ids
        themselves (consumed by ``BrowserTasksWidget`` to narrow the
        task list under a selected folder).
        """
        if (
            MY_TASKS_FILTER_KEY not in self._active_slicer_filters
            or not self._current_project
        ):
            self._folder_id_scope = None
            self._task_id_scope = None
            return

        entity_ids = self._loader_controller.get_my_tasks_entity_ids(
            self._current_project
        )
        folder_ids = set(entity_ids.get("folder_ids") or [])
        scope = set(folder_ids)
        for folder_id in folder_ids:
            scope.update(self.get_folder_id_path(folder_id))
        self._folder_id_scope = scope
        self._task_id_scope = set(entity_ids.get("task_ids") or [])

    def get_task_id_scope(self) -> set[str] | None:
        """Return task ids implied by the active "My Tasks" filter.

        Returns:
            The set of task ids to restrict the task list to, or
            ``None`` when no id-scoping filter is active.
        """
        return self._task_id_scope

    def on_tree_selection_changed(
        self, ids: list[str], names: list[str]
    ) -> None:
        """Handle a selection change in the tree view.

        Args:
            ids: IDs of the selected entities, or empty list when
                the selection is cleared.
            names: Names of the selected entities (parallel to *ids*).
        """
        previous_folder_ids = self._selected_folder_ids
        previous_review_version_ids = self._review_session_version_ids
        self._selected_folder_ids = list(ids)
        if (
            self._include_folder_children
            and self._current_category == BrowserSlicerCategory.HIERARCHY.value
        ):
            self._selected_folder_ids = (
                self._get_top_level_selected_folder_ids(ids)
            )
        self._review_session_version_ids = None  # always clear first

        if (
            self._current_category == BrowserSlicerCategory.REVIEWS.value
            and ids
        ):
            ids_set: set[str] = set()
            for sid in ids:
                ids_set.update(self._get_review_session_version_ids(sid))
            self._review_session_version_ids = (
                list(ids_set) if ids_set else None
            )

        if (
            self._selected_folder_ids == previous_folder_ids
            and self._review_session_version_ids
            == previous_review_version_ids
        ):
            return

        self._reset_pagination()
        self.selection_changed.emit(ids, names)

    def set_tree_mode(self, enabled: bool) -> None:
        """Enable or disable tree mode for the version table.

        Args:
            enabled: When ``True``, the table shows root folders as
                expandable nodes instead of a flat version list.
        """
        self._tree_mode = enabled
        self._reset_pagination()

    def set_group_by(self, group_by: GroupByOption | str) -> None:
        """Set the group-by mode for the version table.

        Args:
            group_by: Dynamic option key or :class:`GroupByOption`.
        """
        key = self._normalize_group_by_key(group_by)
        self._group_by_key = key
        self._reset_pagination()

    def set_hide_empty_groups(self, hide_empty: bool) -> None:
        """Set whether group headers with no rows should be hidden.

        Args:
            hide_empty: When ``True``, only groups with matching rows are
                shown. When ``False``, all configured groups are shown.
        """
        self._hide_empty_groups = hide_empty
        self._reset_pagination()

    def set_featured_version_order(self, order: list[str]) -> None:
        """Set the priority order used to pick the featured version.

        Args:
            order: Ordered list of GraphQL featured-version type keys
                (e.g. ``["latestDone", "latest", "hero"]``).  When
                group-by is set to ``"product"`` the pagination state is
                reset so the next page fetch will use the new order.
        """
        self._featured_version_order = list(order)
        if self._group_by_key == GROUP_BY_PRODUCT_KEY:
            self._reset_pagination()

    def set_filter_criteria(self, criteria: list[Any]) -> None:
        """Set filters that are sent to the versions GraphQL query."""
        key_aliases = {
            "product_name": "productName",
        }
        self._query_filter_criteria = [
            (
                key_aliases.get(str(item.key), str(item.key)),
                [str(value) for value in item.values],
                bool(item.use_substring),
            )
            for item in criteria
            if item.values
        ]
        self._reset_pagination()

    def _get_query_filters(self) -> dict[str, Any]:
        version_conditions: list[dict[str, Any]] = []
        product_conditions: list[dict[str, Any]] = []
        task_conditions: list[dict[str, Any]] = []
        folder_conditions: list[dict[str, Any]] = []
        featured_only: list[str] = []
        search: str | None = None
        version_ids: list[str] | None = None

        extension_filter_keys = self._column_manager.get_filter_keys(
            self._get_column_context()
        )
        for key, values, use_substring in self._query_filter_criteria:
            if key in extension_filter_keys:
                continue
            if key.startswith("attr:"):
                _, scope, attribute_name = key.split(":", 2)
                condition = {
                    "key": f"attrib.{attribute_name}",
                    "value": values[0] if use_substring else values,
                    "operator": "like" if use_substring else "in",
                }
                if scope == "version":
                    version_conditions.append(condition)
                elif scope == "product":
                    product_conditions.append(condition)
                elif scope == "task":
                    task_conditions.append(condition)
                elif scope == "folder":
                    folder_conditions.append(condition)
                continue
            if key in {"featuredVersionType", "version"}:
                mapping = {
                    "Latest": "latest",
                    "Latest Done": "latestDone",
                    "Hero": "hero",
                }
                version_values = []
                for value in values:
                    featured_value = mapping.get(value)
                    if featured_value is not None:
                        featured_only.append(featured_value)
                    elif key == "version":
                        version_values.append(value)
                if version_values:
                    version_conditions.append({
                        "key": "version",
                        "value": (
                            version_values[0]
                            if use_substring
                            else version_values
                        ),
                        "operator": (
                            "like" if use_substring else "in"
                        ),
                    })
                continue
            if key == "inScene":
                selected = set(values)
                loaded_ids = self._loader_controller.get_loaded_version_ids()
                if selected == {"Yes"}:
                    if loaded_ids:
                        version_conditions.append({
                            "key": "id",
                            "value": list(loaded_ids),
                            "operator": "in",
                        })
                    else:
                        version_conditions.append({
                            "key": "id",
                            "value": [],
                            "operator": "in",
                        })
                elif selected == {"No"} and loaded_ids:
                    version_conditions.append({
                        "key": "id",
                        "value": list(loaded_ids),
                        "operator": "notin",
                    })
                continue
            if key == "product/version":
                search = " ".join(values)
                continue

            operator = "like" if use_substring else "in"
            condition = {
                "key": key,
                "value": values[0] if use_substring else values,
                "operator": operator,
            }
            if key in {
                "productBaseType",
                "productType",
                "productName",
            }:
                if key == "productName":
                    condition["key"] = "name"
                product_conditions.append(condition)
            elif key == "folderName":
                folder_conditions.append({
                    "key": "name",
                    "value": condition["value"],
                    "operator": condition["operator"],
                })
            elif key == "task":
                no_task = "No task" in values
                task_names = [value for value in values if value != "No task"]
                if no_task and task_names:
                    task_conditions.append({
                        "operator": "or",
                        "conditions": [
                            {"key": "id", "operator": "isnull"},
                            {
                                "key": "name",
                                "value": task_names,
                                "operator": "in",
                            },
                        ],
                    })
                elif no_task:
                    task_conditions.append({
                        "key": "id",
                        "operator": "isnull",
                    })
                else:
                    task_conditions.append({
                        "key": "name",
                        "value": values,
                        "operator": operator,
                    })
            elif key == "taskType":
                task_conditions.append({
                    "key": "taskType",
                    "value": condition["value"],
                    "operator": condition["operator"],
                })
            elif key == "taskStatus":
                task_conditions.append({
                    "key": "status",
                    "value": condition["value"],
                    "operator": condition["operator"],
                })
            elif key == "taskTags":
                task_conditions.append({
                    "key": "tags",
                    "value": values,
                    "operator": "includesany",
                })
            elif key == "tags":
                version_conditions.append({
                    "key": "tags",
                    "value": values,
                    "operator": "includesany",
                })
            elif key == "productStatus":
                product_conditions.append({
                    "key": "status",
                    "value": condition["value"],
                    "operator": condition["operator"],
                })
            elif key == "folderStatus":
                folder_conditions.append({
                    "key": "status",
                    "value": condition["value"],
                    "operator": condition["operator"],
                })
            else:
                version_conditions.append(condition)

        def encode(conditions: list[dict[str, Any]]) -> str:
            if not conditions:
                return ""
            return json.dumps({"conditions": conditions})

        return {
            "version_filter": encode(version_conditions),
            "product_filter": encode(product_conditions),
            "task_filter": encode(task_conditions),
            "folder_filter": encode(folder_conditions),
            "featured_only": featured_only or None,
            "search": search,
            "version_ids": version_ids,
        }

    @staticmethod
    def _decode_attributes(value: Any) -> dict[str, Any]:
        """Decode an ``allAttrib`` GraphQL value defensively."""
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    @staticmethod
    def _merge_query_filters(*filters: str) -> str:
        conditions: list[dict[str, Any]] = []
        for value in filters:
            if value:
                conditions.extend(json.loads(value).get("conditions", []))
        return json.dumps({"conditions": conditions}) if conditions else ""

    def fetch_children(self, parent_id: str | None) -> list[TreeNode]:
        """Return tree nodes for the given parent.

        Dispatches to :meth:`_fetch_products` or
        :meth:`_fetch_reviews` depending on the current category.

        Args:
            parent_id: Parent entity ID, or ``None`` for root.

        Returns:
            List of :class:`TreeNode` instances.
        """
        if self._current_category == BrowserSlicerCategory.HIERARCHY.value:
            return self._fetch_products(parent_id)
        return self._fetch_reviews(parent_id)

    def fetch_versions_page(
        self,
        page_number: int,
        page_size: int,
        sort_key: str | None = None,
        descending: bool = False,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch and enrich one Browser page."""
        rows = self._fetch_versions_page_base(
            page_number,
            page_size,
            sort_key,
            descending,
            parent_id,
        )
        return self._column_manager.enrich_rows(
            self._get_column_context(),
            rows,
        )

    def _fetch_versions_page_base(
        self,
        page_number: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch a page of version rows for the table.

        Translates the UI ``sort_key`` column name to a valid GraphQL
        ``sortBy`` value using :data:`COLUMN_TO_SORT_BY`.  Columns not
        present in that mapping are unsortable server-side; the call
        proceeds without a sort parameter so the server falls back to
        its default ordering (``creation_order``).

        In tree mode with ``parent_id=None``, returns root folder rows
        instead of version rows.  When ``parent_id`` is set, returns
        version rows for that folder using a per-folder pagination cursor.

        Args:
            page_number: Zero-based page index (used to determine
                whether to reset the cursor).
            page_size: Number of rows per page.
            sort_key: Column key to sort by, or ``None``.
            descending: Whether to sort in descending order.
            parent_id: Row ``id`` of the parent node when fetching
                child rows in tree mode, or ``None`` for root level.

        Returns:
            List of row dicts suitable for
            :class:`~ayon_ui_qt.components.table_model.PaginatedTableModel`.
        """
        if not self._current_project:
            self.log.debug(
                "fetch_versions_page called with no project set, "
                "returning empty page."
            )
            return []
        if not self._selected_folder_ids:
            self.log.debug(
                "fetch_versions_page called without a slicer selection, "
                "returning empty page."
            )
            return []

        if page_number == 0:
            if parent_id is not None:
                self._folder_cursors.pop(parent_id, None)
                self._folder_has_more.pop(parent_id, None)
            else:
                self._reset_pagination()

        sort_by = COLUMN_TO_SORT_BY.get(sort_key) if sort_key else None
        query_filters = self._get_query_filters()
        self.log.debug(
            "fetch_versions_page: page=%d sort_key=%r sort_by=%r "
            "descending=%r cursor=%r parent_id=%r",
            page_number,
            sort_key,
            sort_by,
            descending,
            self._graphql_cursor,
            parent_id,
        )

        # -- Group-by mode -----------------------------------------------
        if (
            self._current_category == BrowserSlicerCategory.HIERARCHY.value
            and self.group_by_key != GROUP_BY_NONE_KEY
        ):
            # Root level: return group header rows.
            if parent_id is None:
                # Group headers are computed in one shot; only page 0 is valid.
                if page_number > 0:
                    return []
                return self._fetch_group_headers()

            # Expanding a group header: fetch filtered versions.
            if parent_id.startswith("grp:"):
                group_key, group_value = self._parse_group_id(parent_id)

                product_ids: list[str] | None = None
                version_filter = ""
                product_filter = ""

                if group_key == GROUP_BY_PRODUCT_KEY:
                    product_ids = [group_value]
                else:
                    version_filter, product_filter = (
                        self._build_version_filter(group_key, group_value)
                    )
                version_filter = self._merge_query_filters(
                    query_filters["version_filter"], version_filter
                )
                product_filter = self._merge_query_filters(
                    query_filters["product_filter"], product_filter
                )

                cursor = self._folder_cursors.get(parent_id, "")
                if page_number > 0 and not self._folder_has_more.get(
                    parent_id, False
                ):
                    return []
                folder_ids = self._selected_folder_ids or None

                edges, page_info = self._get_versions_page(
                    self._current_project,
                    None,
                    page_size,
                    cursor=cursor,
                    sort_by=sort_by,
                    descending=descending,
                    version_ids=None,
                    include_folder_children=self._include_folder_children,
                    folder_ids=folder_ids,
                    product_ids=product_ids,
                    version_filter=version_filter,
                    product_filter=product_filter,
                    task_filter=query_filters["task_filter"],
                    folder_filter=query_filters["folder_filter"],
                    featured_only=query_filters["featured_only"],
                    latest_per_folder=(
                        self._latest_per_folder
                        and self._group_by_key != GROUP_BY_PRODUCT_KEY
                    ),
                    search=query_filters["search"],
                )
                rows = [
                    self._transform_version_edge(e)
                    for e in edges
                ]
                if descending:
                    self._folder_has_more[parent_id] = page_info[
                        "hasPreviousPage"
                    ]
                    self._folder_cursors[parent_id] = page_info["startCursor"]
                else:
                    self._folder_has_more[parent_id] = page_info["hasNextPage"]
                    self._folder_cursors[parent_id] = page_info["endCursor"]
                return rows

        # -- Default hierarchy / flat mode --------------------------------

        # Tree root: return folder rows so the model has expandable nodes.
        if (
            parent_id is None
            and self._tree_mode
            and self._current_category == BrowserSlicerCategory.HIERARCHY.value
        ):
            return self._fetch_root_folders(self._selected_folder_ids)

        # Child versions for a specific folder (tree-mode expand).
        if parent_id is not None:
            # On the first page, prepend direct sub-folder rows so that
            # the tree can be navigated depth-first all the way down to
            # version leaves.
            folder_rows = (
                self._get_child_folder_rows(parent_id)
                if page_number == 0 and not self._include_folder_children
                else []
            )

            cursor = self._folder_cursors.get(parent_id, "")
            if page_number > 0 and not self._folder_has_more.get(
                parent_id, False
            ):
                return []
            query_folder_ids = [parent_id]
            edges, page_info = self._get_versions_page(
                self._current_project,
                None,
                page_size,
                cursor=cursor,
                sort_by=sort_by,
                descending=descending,
                include_folder_children=self._include_folder_children,
                folder_ids=query_folder_ids,
                version_filter=query_filters["version_filter"],
                product_filter=query_filters["product_filter"],
                task_filter=query_filters["task_filter"],
                folder_filter=query_filters["folder_filter"],
                featured_only=query_filters["featured_only"],
                latest_per_folder=(
                    self._latest_per_folder
                    and self._group_by_key != GROUP_BY_PRODUCT_KEY
                ),
                search=query_filters["search"],
            )
            version_rows = [
                self._transform_version_edge(e)
                for e in edges
            ]
            if descending:
                self._folder_has_more[parent_id] = page_info["hasPreviousPage"]
                self._folder_cursors[parent_id] = page_info["startCursor"]
            else:
                self._folder_has_more[parent_id] = page_info["hasNextPage"]
                self._folder_cursors[parent_id] = page_info["endCursor"]
            self.log.debug(
                "Received %d sub-folders and %d child version edges for "
                "folder %r, page info: %s",
                len(folder_rows),
                len(edges),
                parent_id,
                page_info,
            )
            return folder_rows + version_rows

        # Flat mode.
        folder_ids: list[str] | None = None
        if self._current_category == BrowserSlicerCategory.REVIEWS.value:
            version_ids = self._review_session_version_ids  # None = no filter
            if not version_ids:
                # No review session selected yet — show nothing
                return []
        else:
            folder_ids = self._selected_folder_ids or None
            version_ids = None

        if page_number > 0 and not self._graphql_has_more:
            return []

        cursor = self._graphql_cursor
        edges, page_info = self._get_versions_page(
            self._current_project,
            None,
            page_size,
            cursor=cursor,
            sort_by=sort_by,
            descending=descending,
            version_ids=version_ids,
            folder_ids=folder_ids,
            include_folder_children=self._include_folder_children,
            version_filter=query_filters["version_filter"],
            product_filter=query_filters["product_filter"],
            task_filter=query_filters["task_filter"],
            folder_filter=query_filters["folder_filter"],
            featured_only=query_filters["featured_only"],
            latest_per_folder=(
                self._latest_per_folder
                and self._group_by_key != GROUP_BY_PRODUCT_KEY
            ),
            search=query_filters["search"],
        )
        self.log.debug(
            "Received %d edges, page info: %s", len(edges), page_info
        )
        page = [
            self._transform_version_edge(e)
            for e in edges
        ]

        if descending:
            has_more = page_info["hasPreviousPage"]
            next_cursor = page_info["startCursor"]
        else:
            has_more = page_info["hasNextPage"]
            next_cursor = page_info["endCursor"]

        cursor_advanced = bool(next_cursor) and next_cursor != cursor
        self._graphql_has_more = bool(has_more and cursor_advanced)
        self._graphql_cursor = next_cursor or cursor
        if has_more and not cursor_advanced:
            self.log.warning(
                "Stopping version pagination because the cursor did not "
                "advance from %r.",
                cursor,
            )

        return page

    def fetch_versions_page_batch(
        self,
        requests: list[BatchFetchRequest],
    ) -> dict[str | None, list[dict[str, Any]]]:
        """Fetch child pages for multiple parents in one batch callback.

        Group-by requests (``parent_id`` starts with ``"grp:"``) are
        delegated to :meth:`fetch_versions_page` individually because
        they carry heterogeneous filter parameters.

        Hierarchy requests are processed inside one worker-task callback,
        but each parent is fetched with its own cursor state to preserve
        correctness for cursor-based pagination.

        Args:
            requests: List of :class:`BatchFetchRequest` objects produced
                by :class:`PaginatedTableModel._dispatch_batch`.

        Returns:
            Dict mapping each ``parent_id`` to its list of row dicts,
            exactly as expected by
            :meth:`PaginatedTableModel._on_batch_ready`.
        """
        if not self._current_project:
            return {}
        if not self._selected_folder_ids:
            return {}

        result: dict[str | None, list[dict[str, Any]]] = {}
        query_filters = self._get_query_filters()

        # Separate group-by requests (must be fetched individually) from
        # plain hierarchy requests (can be batched).
        grp_requests: list[BatchFetchRequest] = []
        batch_requests: list[BatchFetchRequest] = []
        for req in requests:
            if req.parent_id and req.parent_id.startswith("grp:"):
                grp_requests.append(req)
            else:
                batch_requests.append(req)

        # -- Group-by fetches --------------------------------------------
        # Match the frontend's Promise.all behavior: independent groups
        # are requested concurrently instead of serially per row.
        if grp_requests:
            with ThreadPoolExecutor(
                max_workers=min(8, len(grp_requests))
            ) as executor:
                futures = {
                    req.parent_id: executor.submit(
                        self._fetch_versions_page_base,
                        req.page,
                        req.page_size,
                        req.sort_key,
                        req.descending,
                        req.parent_id,
                    )
                    for req in grp_requests
                }
                for parent_id, future in futures.items():
                    result[parent_id] = future.result()

        # -- Hierarchy fetches -------------------------------------------
        if not batch_requests:
            return self._enrich_batch_result(result)

        for req in batch_requests:
            if req.parent_id is None:
                result[req.parent_id] = self._fetch_versions_page_base(
                    req.page,
                    req.page_size,
                    req.sort_key,
                    req.descending,
                    req.parent_id,
                )
                continue

            parent_id = req.parent_id
            sort_by = (
                COLUMN_TO_SORT_BY.get(req.sort_key) if req.sort_key else None
            )

            if req.page == 0:
                self._folder_cursors.pop(parent_id, None)
                self._folder_has_more.pop(parent_id, None)
            elif not self._folder_has_more.get(parent_id, False):
                result[parent_id] = []
                continue

            cursor = self._folder_cursors.get(parent_id, "")
            query_folder_ids = [parent_id]
            edges, page_info = self._get_versions_page(
                self._current_project,
                None,
                req.page_size,
                cursor=cursor,
                sort_by=sort_by,
                descending=req.descending,
                include_folder_children=self._include_folder_children,
                folder_ids=query_folder_ids,
                version_filter=query_filters["version_filter"],
                product_filter=query_filters["product_filter"],
                task_filter=query_filters["task_filter"],
                folder_filter=query_filters["folder_filter"],
                featured_only=query_filters["featured_only"],
                latest_per_folder=(
                    self._latest_per_folder
                    and self._group_by_key != GROUP_BY_PRODUCT_KEY
                ),
                search=query_filters["search"],
            )

            version_rows = [
                self._transform_version_edge(e)
                for e in edges
            ]
            folder_rows = (
                self._get_child_folder_rows(parent_id)
                if req.page == 0 and not self._include_folder_children
                else []
            )

            if req.descending:
                self._folder_has_more[parent_id] = page_info["hasPreviousPage"]
                self._folder_cursors[parent_id] = page_info["startCursor"]
            else:
                self._folder_has_more[parent_id] = page_info["hasNextPage"]
                self._folder_cursors[parent_id] = page_info["endCursor"]

            result[parent_id] = folder_rows + version_rows

        return self._enrich_batch_result(result)

    def fetch_product_versions(
        self,
        product_id: str,
        page_size: int = 250,
    ) -> list[dict[str, Any]]:
        """Fetch every version for a product without the active filters.

        This intentionally bypasses current slicer filters so hidden
        versions can be selected as replacements.
        """
        if not self._current_project or not product_id:
            return []

        cursor: str | None = None
        rows: list[dict[str, Any]] = []
        while True:
            edges, page_info = self._get_versions_page(
                self._current_project,
                None,
                page_size,
                cursor=cursor,
                product_ids=[product_id],
                include_folder_children=True,
                version_filter="",
                product_filter="",
                task_filter="",
                folder_filter="",
                featured_only=None,
                latest_per_folder=False,
                search=None,
            )
            rows.extend(
                self._transform_version_edge(edge) for edge in edges
            )
            if not page_info.get("hasNextPage"):
                break
            next_cursor = page_info.get("endCursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return rows

    def fetch_projects(self) -> list[dict[str, Any]]:
        """Fetch all projects using GraphQL.

        Returns:
            List of project dicts with at least ``name``, ``active``,
            ``library`` and ``data`` keys.
        """
        api = ayon_api.get_server_api_connection()
        query = projects_graphql_query({"name", "active", "library", "data"})
        projects: list[dict[str, Any]] = []
        for parsed_data in query.continuous_query(api):  # type: ignore
            for project in parsed_data["projects"]:
                project_data = project["data"]
                if project_data is None:
                    project["data"] = {}
                elif isinstance(project_data, str):
                    project["data"] = json.loads(project_data)
                projects.append(project)
        return projects

    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        """Return action items for the given entity selection.

        Delegates to the main loader controller when one was provided at
        construction time.  Returns an empty list when no loader
        controller is available.

        Args:
            project_name: AYON project name.
            entity_ids: Set of selected entity IDs.
            entity_type: Entity type string (e.g. ``"version"``).

        Returns:
            List of :class:`ActionItem` objects.
        """
        return self._loader_controller.get_action_items(
            project_name, entity_ids, entity_type
        )

    def get_representation_items(
        self,
        project_name: str,
        version_ids: list[str],
    ) -> list[Any]:
        """Return representation items for the given version ids.

        Delegates to the main loader controller when one was provided at
        construction time.  Returns an empty list when no loader
        controller is available.

        Args:
            project_name: AYON project name.
            version_ids: List of version IDs to query.

        Returns:
            List of :class:`~ayon_core.tools.browser.abstract.RepreItem`
            objects.
        """
        return self._loader_controller.get_representation_items(
            project_name, version_ids
        )

    def _get_column_context(self) -> BrowserColumnContext:
        """Return an immutable state snapshot for column providers."""
        filters = tuple(
            BrowserFilter(
                key=key,
                values=tuple(values),
                use_substring=use_substring,
            )
            for key, values, use_substring in self._query_filter_criteria
        )
        return BrowserColumnContext(
            project_name=self._current_project or None,
            category=self._current_category,
            selected_folder_ids=tuple(self._selected_folder_ids),
            selected_task_ids=tuple(
                self._loader_controller.get_selected_task_ids()
            ),
            enabled_column_keys=frozenset(
                self._requested_column_keys or set()
            ),
            active_filters=filters,
            group_by_key=self._group_by_key,
            include_folder_children=self._include_folder_children,
        )

    def _enrich_batch_result(
        self,
        result: dict[str | None, list[dict[str, Any]]],
    ) -> dict[str | None, list[dict[str, Any]]]:
        """Enrich all rows from a batch in one provider call."""
        rows = [
            row
            for page_rows in result.values()
            for row in page_rows
        ]
        self._column_manager.enrich_rows(
            self._get_column_context(),
            rows,
        )
        return result

    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: dict[str, Any] | None,
        options: dict[str, Any],
        form_values: dict[str, Any],
    ) -> None:
        """Trigger an action item by identifier.

        Delegates to the main loader controller when one was provided at
        construction time.  Does nothing when no loader controller is
        available.

        Args:
            identifier: Action plugin identifier.
            project_name: AYON project name.
            selected_ids: Set of selected entity IDs.
            selected_entity_type: Entity type string (e.g. ``"version"``).
            data: Optional action-specific payload.
            options: Loader option values.
            form_values: Form values returned by the action dialog.
        """
        self._loader_controller.trigger_action_item(
            identifier=identifier,
            project_name=project_name,
            selected_ids=selected_ids,
            selected_entity_type=selected_entity_type,
            data=data,
            options=options,
            form_values=form_values,
        )

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _reset_pagination(self) -> None:
        """Reset the GraphQL pagination cursor, has-more flag, and all
        per-folder pagination state."""
        self._graphql_cursor = ""
        self._graphql_has_more = False
        self._folder_cursors = {}
        self._folder_has_more = {}

    def _get_top_level_selected_folder_ids(
        self, folder_ids: list[str]
    ) -> list[str]:
        """Remove selected folders covered by another selected ancestor."""
        selected = set(folder_ids)
        result = []
        for folder_id in folder_ids:
            parent_id = self._folder_parent_ids.get(folder_id)
            covered = False
            while parent_id is not None:
                if parent_id in selected:
                    covered = True
                    break
                parent_id = self._folder_parent_ids.get(parent_id)
            if not covered:
                result.append(folder_id)
        return result

    def _fetch_root_folders(
        self, selected_folder_ids: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch folders to use as tree root rows.

        When *selected_folder_ids* is a non-empty list, those folders
        are returned as the root rows so the table shows them expanded.
        Otherwise, all top-level folders (depth 1) are returned
        collapsed.

        Args:
            selected_folder_ids: IDs of the folders currently selected
                in the slicer tree, or ``None``/empty list for the
                default root view.

        Returns:
            List of row dicts with ``has_children=True`` so the table
            model renders them as expandable nodes.
        """
        _fields = {
            "id", "name", "label", "folderType", "hasChildren", "allAttrib"
        }
        if selected_folder_ids:
            folders = list(
                ayon_api.get_folders(
                    self._current_project,
                    folder_ids=selected_folder_ids,
                    fields=_fields,
                )
            )
        else:
            folders = list(
                ayon_api.get_folders(
                    self._current_project,
                    parent_ids=[None],  # type: ignore[list-item]
                    fields=_fields,
                )
            )
        return [self._build_folder_row(f) for f in folders]

    def _get_child_folder_rows(self, parent_id: str) -> list[dict[str, Any]]:
        """Fetch direct sub-folders of *parent_id* as table rows.

        Args:
            parent_id: Folder ID whose immediate children should be
                returned.

        Returns:
            List of row dicts built by :meth:`_build_folder_row`.
        """
        folders = ayon_api.get_folders(
            self._current_project,
            parent_ids=[parent_id],
            fields={
                "id", "name", "label", "folderType", "hasChildren",
                "allAttrib",
            },
        )
        return [self._build_folder_row(f) for f in folders]

    def _build_folder_row(self, folder: dict[str, Any]) -> dict[str, Any]:
        """Build a table row dict from a folder entity.

        Args:
            folder: Folder entity dict from ``ayon_api.get_folders``.

        Returns:
            Row dict compatible with
            :class:`~ayon_ui_qt.components.table_model.PaginatedTableModel`.
        """
        folder_type = folder.get("folderType", "")
        label = folder.get("label") or folder.get("name", "")
        icon = self._pinfo("folderTypes", folder_type, "icon", "folder")
        row = dict(EMPTY_ROW)
        row.update(
            {
                "id": folder.get("id", ""),
                "has_children": True,
                "product/version": label,
                "product/version__icon": icon,
                "folderName": label,
                "entityType": "Folder",
                "entityType__icon": "folder",
            }
        )
        for name, value in self._decode_attributes(
            folder.get("allAttrib")
        ).items():
            row[f"attr:folder:{name}"] = value
        return row

    # -- Group-by helpers ------------------------------------------------

    def _build_group_header_row(
        self,
        group_option: GroupByOption,
        value: str,
        icon: str = "",
        color: str | None = None,
        label: str | None = None,
        product_type: str | None = None,
        featured_version: dict[str, Any] | None = None,
        num_versions: int | None = None,
    ) -> dict[str, Any]:
        """Build an expandable group-header row.

        Args:
            group_option: Group-by axis.
            value: The specific group value (e.g. ``"In Progress"``).
                Stored in the row ``id`` and used as the display label
                when *label* is not provided.
            icon: Material icon name for the tree cell.
            color: Optional colour hint for the status/type badge.
            label: Optional display label. When provided, used for the
                ``"product/version"`` column instead of *value*.
            product_type: Optional product type string, required when
                *featured_version* is provided.
            featured_version: Optional dict representing the featured
                version.
            num_versions: Number of versions in the group, or ``None``
                when the count source is unavailable.

        Returns:
            Row dict containing the authoritative child count and an id
            of the form ``"grp:<group_type.value>:<value>"``.
        """
        display_label = label if label is not None else value
        row = dict(EMPTY_ROW)
        # None means filtered statistics were unavailable, not that the
        # group is empty, so keep it expandable for lazy child discovery.
        row.update(
            {
                "id": f"grp:{group_option.key}:{value}",
                "has_children": num_versions is None or num_versions > 0,
                "child_count": num_versions,
                "thumb": display_label,
                "product/version": display_label,
                "product/version__icon": icon or "label",
                "entityType": group_option.label,
                "entityType__icon": group_option.icon,
                "project_name": self._current_project,
                "inScene": False,
            }
        )
        if color:
            row["product/version__color"] = color
        if featured_version:
            assert product_type is not None, (
                "product_type is required when featured_version is provided"
            )
            row["thumbnailId"] = featured_version.get("thumbnailId", "")
            row["_version_id"] = featured_version.get("id", "")
            row["inScene"] = (
                True
                if row["_version_id"]
                in self._loader_controller.get_loaded_version_ids()
                else False
            )
            row["status"] = featured_version.get("status", "")
            row["status__icon"] = self._pinfo(
                "statuses", row["status"], "icon", ""
            )
            row["status__color"] = self._pinfo(
                "statuses", row["status"], "color", ""
            )
            row["status__short"] = self._pinfo(
                "statuses", row["status"], "shortName", ""
            )
            row["productType"] = product_type
            row["productType__icon"] = self._pinfo(
                "productTypes", product_type, "icon", "category"
            )
            row["folderName"] = featured_version.get("parents", ["", ""])[-2]
            row["author"] = featured_version.get("author", "")
            v_str = (
                f"({num_versions} versions)"
                if num_versions is not None
                else ""
            )
            row["version"] = (
                f"{featured_version.get('name', '')} {v_str}".strip()
            )
            row["productName"] = featured_version.get("parents", [""])[-1]
            row["createdAt"] = featured_version.get("createdAt", "")
            row["updatedAt"] = featured_version.get("updatedAt", "")
        return row

    def _fetch_group_headers(self) -> list[dict[str, Any]]:
        """Dispatch to the appropriate group-header fetcher.

        Returns:
            List of expandable group-header rows.
        """
        inventory_counts = self._get_group_inventory_counts(self.group_by)
        filtered_counts = self._get_group_counts(self.group_by)
        if filtered_counts is None:
            group_counts = inventory_counts or None
        else:
            group_counts = {
                value: filtered_counts.get(value, 0)
                for value in inventory_counts
            }
            group_counts.update(filtered_counts)
        if self.group_by_key == GROUP_BY_STATUS_KEY:
            return self._fetch_status_group_headers(group_counts)
        if self.group_by_key == GROUP_BY_PRODUCT_TYPE_KEY:
            return self._fetch_product_type_group_headers(group_counts)
        if self.group_by_key == GROUP_BY_PRODUCT_KEY:
            return self._fetch_product_group_headers(group_counts)
        if self.group_by_key == GROUP_BY_TAGS_KEY:
            return self._fetch_tags_group_headers(group_counts)
        if self.group_by_key == GROUP_BY_TASK_TYPE_KEY:
            return self._fetch_task_type_group_headers(group_counts)
        if self.group_by.source == GroupBySource.ATTRIBUTE:
            return self._fetch_attribute_group_headers(
                self.group_by,
                group_counts,
            )
        self.log.warning("Unknown group-by key: %s", self.group_by_key)
        return []

    def _get_group_counts(
        self,
        group_option: GroupByOption,
    ) -> dict[str, int] | None:
        """Return filtered counts, or ``None`` when stats are unavailable."""
        target_field = {
            GROUP_BY_PRODUCT_KEY: "product_id",
            GROUP_BY_STATUS_KEY: "status",
            GROUP_BY_PRODUCT_TYPE_KEY: "product_type",
            GROUP_BY_TAGS_KEY: "tags",
            GROUP_BY_TASK_TYPE_KEY: "task_type",
        }.get(group_option.key)
        if group_option.source == GroupBySource.ATTRIBUTE:
            target_field = f"attrib.{group_option.attribute_name}"
        if not target_field:
            return {}

        query_filters = self._get_query_filters()
        version_ids = query_filters["version_ids"]
        folder_ids: list[str] | None = self._selected_folder_ids or None
        if self._current_category == BrowserSlicerCategory.REVIEWS.value:
            if not self._review_session_version_ids:
                return {}
            review_ids = set(self._review_session_version_ids or ())
            if version_ids:
                review_ids.intersection_update(version_ids)
            version_ids = list(review_ids)
            folder_ids = None

        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")

        variables = {
            "projectName": self._current_project,
            "versionFilter": query_filters["version_filter"],
            "productFilter": query_filters["product_filter"],
            "taskFilter": query_filters["task_filter"],
            "folderFilter": query_filters["folder_filter"],
            "folderIds": folder_ids,
            "versionIds": version_ids,
            "includeFolderChildren": self._include_folder_children,
            "featuredOnly": query_filters["featured_only"],
            "latestPerFolder": (
                self._latest_per_folder
                and group_option.key != GROUP_BY_PRODUCT_KEY
            ),
            "search": query_filters["search"],
            "targets": [{
                "field": target_field,
                "aggregations": [
                    "DISTRIBUTION",
                    "FILLED",
                    "NOT_FILLED",
                ],
            }],
        }
        response = con.query_graphql(
            GET_VERSION_GROUP_COUNTS_QUERY,
            variables,
        )
        if response.errors:
            raise RuntimeError(response.errors)

        versions = response.data["data"]["project"]["versions"]
        column_name = target_field.replace(".", "_")
        column_name_parts = column_name.split("_")
        camel_column_name = column_name_parts[0] + "".join(
            part.title() for part in column_name_parts[1:]
        )
        expected_column_names = {column_name, camel_column_name}
        if target_field in {"product_type", "task_type"}:
            expected_column_names.add("subType")
        stats = next(
            (
                item
                for item in versions.get("fieldStats") or []
                if (
                    item.get("columnName")
                    or item.get("column_name")
                ) in expected_column_names
            ),
            None,
        )
        if stats is None:
            self.log.warning(
                "Version group statistics did not return field %r. "
                "Falling back to grouping metadata.",
                column_name,
            )
            return None

        distribution = stats.get("distribution") or []
        if isinstance(distribution, str):
            distribution = json.loads(distribution)
        if (
            not distribution
            and stats.get("valueFilledCount") is None
            and stats.get("valueNotFilledCount") is None
        ):
            self.log.warning(
                "Version group statistics for %r were incomplete. "
                "Falling back to grouping metadata.",
                column_name,
            )
            return None

        output: dict[str, int] = {}
        for item in distribution:
            count = int(item.get("count") or 0)
            raw_value = item.get("value")
            values = (
                raw_value
                if isinstance(raw_value, list)
                else [raw_value]
            )
            for value in values:
                if value is not None:
                    key = (
                        _normalize_entity_id(value)
                        if group_option.key == GROUP_BY_PRODUCT_KEY
                        else str(value)
                    )
                    output[key] = output.get(key, 0) + count
        return output

    def _get_group_inventory_counts(
        self,
        group_option: GroupByOption,
    ) -> dict[str, int]:
        """Return broad group counts used when filtered stats are absent."""
        endpoint = {
            GROUP_BY_STATUS_KEY: "grouping/version/status",
            GROUP_BY_PRODUCT_TYPE_KEY: "grouping/version/productType",
            GROUP_BY_TAGS_KEY: "grouping/version/tags",
            GROUP_BY_TASK_TYPE_KEY: "grouping/task/taskType",
        }.get(group_option.key)
        if group_option.source == GroupBySource.ATTRIBUTE:
            endpoint = (
                "grouping/version/"
                f"attrib.{group_option.attribute_name}"
            )
        if not endpoint:
            return {}

        payload = ayon_api.get(
            f"projects/{self._current_project}/{endpoint}",
            empty=True,
        )
        output: dict[str, int] = {}
        for item in (payload.data or {}).get("groups", []):
            value = item.get("value")
            if value is None:
                continue
            output[str(value)] = int(item.get("count") or 0)
        return output

    def _group_values(
        self,
        category: str,
        group_counts: dict[str, int] | None,
    ) -> list[str]:
        """Return configured values plus any values found by statistics."""
        values = list(
            self._project_info.get("by_name", {}).get(category, {})
        )
        values.extend(
            sorted(set(group_counts or {}) - set(values), key=str.casefold)
        )
        if self._hide_empty_groups and group_counts is not None:
            values = [
                value for value in values if group_counts.get(value, 0) > 0
            ]
        return values

    def _fetch_status_group_headers(
        self,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return status group rows with filter-aware version counts."""
        status_names = self._group_values("statuses", group_counts)

        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_STATUS_KEY],
                name,
                icon=self._pinfo("statuses", name, "icon", "circle"),
                color=self._pinfo("statuses", name, "color"),
                num_versions=(
                    group_counts.get(name, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for name in status_names
        ]

    def _fetch_product_type_group_headers(
        self,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return product-type rows with filter-aware version counts."""
        values = self._group_values("productTypes", group_counts)
        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_PRODUCT_TYPE_KEY],
                pt,
                icon=self._pinfo("productTypes", pt, "icon", "category"),
                color=self._pinfo("productTypes", pt, "color"),
                num_versions=(
                    group_counts.get(pt, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for pt in values
        ]

    def _fetch_tags_group_headers(
        self,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return tag rows with filter-aware version counts."""
        values = self._group_values("tags", group_counts)
        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_TAGS_KEY],
                tag,
                icon=self._pinfo("tags", tag, "icon", "label"),
                color=self._pinfo("tags", tag, "color"),
                num_versions=(
                    group_counts.get(tag, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for tag in values
        ]

    def _fetch_task_type_group_headers(
        self,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return task-type rows with filter-aware version counts."""
        values = self._group_values("taskTypes", group_counts)
        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_TASK_TYPE_KEY],
                task_type,
                icon=self._pinfo("taskTypes", task_type, "icon", "category"),
                color=self._pinfo("taskTypes", task_type, "color"),
                num_versions=(
                    group_counts.get(task_type, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for task_type in values
        ]

    def _fetch_attribute_group_headers(
        self,
        group_option: GroupByOption,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return attribute rows with filter-aware version counts."""
        attr_name = group_option.attribute_name
        if not attr_name:
            return []

        values = sorted(group_counts or {}, key=str.casefold)
        if self._hide_empty_groups and group_counts is not None:
            values = [
                value for value in values if group_counts.get(value, 0) > 0
            ]
        return [
            self._build_group_header_row(
                group_option,
                value,
                num_versions=(
                    group_counts.get(value, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for value in values
        ]

    def _get_products_page(
        self,
        project_name: str,
        folder_id: str | None,
        page_size: int,
        cursor: str | None = None,
        sort_by: str | None = None,
        descending: bool = False,
        folder_ids: list[str] | None = None,
        product_filter: str = "",
        version_filter: str = "",
        task_filter: str = "",
        folder_filter: str = "",
        search: str | None = None,
        include_folder_children: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch a single page of products via GraphQL.

        Args:
            project_name: AYON project name.
            folder_id: Filter by a single folder ID, or ``None``.
                Ignored when *folder_ids* is provided.
            page_size: Maximum number of edges to return.
            cursor: GraphQL cursor from the previous page, or ``None``
                for the first page.
            sort_by: Valid GraphQL ``sortBy`` value, or ``None``.
            descending: When ``True`` use ``last``/``before`` pagination.
            folder_ids: When provided, filters by this explicit list of
                folder IDs instead of the single *folder_id*.
            product_filter: JSON-encoded product filter string.
            version_filter: JSON-encoded version filter string.
            task_filter: JSON-encoded task filter string.
            folder_filter: JSON-encoded folder filter string.
            search: Full-text product search string.

        Returns:
            Tuple of (edges list, pageInfo dict).

        Raises:
            RuntimeError: If there is no server connection or the
                query returns errors.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")

        if folder_ids is not None:
            resolved_folder_ids: list[str] | None = folder_ids
        elif folder_id is not None:
            resolved_folder_ids = [folder_id]
        else:
            resolved_folder_ids = None

        variables: dict[str, Any] = {
            "projectName": project_name,
            "productFilter": product_filter or "",
            "versionFilter": version_filter or "",
            "taskFilter": task_filter or "",
            "folderFilter": folder_filter or "",
            "search": search,
            "includeFolderChildren": include_folder_children,
            "sortBy": sort_by,
            "folderIds": resolved_folder_ids,
            "featuredVersionOrder": self._featured_version_order,
        }
        if descending:
            variables["last"] = page_size
            variables["before"] = cursor or None
        else:
            variables["first"] = page_size
            variables["after"] = cursor or None

        resp = con.query_graphql(GET_PRODUCTS_QUERY, variables)
        if resp.errors:
            raise RuntimeError(resp.errors)
        payload = resp.data["data"]
        products_block = payload["project"]["products"]
        return products_block["edges"], products_block["pageInfo"]

    @staticmethod
    def _extract_product_group_data(
        edges: list[dict[str, Any]],
    ) -> list[tuple[str, str, str, dict[str, Any]]]:
        """Transform raw product edges into structured tuples.

        Args:
            edges: List of GraphQL product edges from
                :meth:`_get_products_page`.

        Returns:
            List of ``(product_id, product_name, product_type,
            featured_version)`` tuples.
        """
        result: list[tuple[str, str, str, dict[str, Any]]] = []
        for edge in edges:
            node = edge.get("node", {})
            product_id = _normalize_entity_id(node.get("id", ""))
            product_name = node.get("name", "")
            product_type = node.get("productType", "")
            featured_version = node.get("featuredVersion", {})
            if product_id and product_name:
                result.append(
                    (
                        product_id,
                        product_name,
                        product_type,
                        featured_version,
                    )
                )
        return result

    def _fetch_product_group_headers(
        self,
        group_counts: dict[str, int] | None,
    ) -> list[dict[str, Any]]:
        """Return one expandable row per product in the current scope.

        Fetches products via :meth:`_get_products_page`, extracts
        structured tuples via :meth:`_extract_product_group_data`, then
        builds group-header rows using product ID as the group value and
        product name as the display label.

        Returns:
            List of expandable group-header rows keyed by product ID.
        """
        folder_ids = self._selected_folder_ids or None
        query_filters = self._get_query_filters()
        all_edges: list[dict[str, Any]] = []
        cursor: str | None = None

        for _page in range(_MAX_GROUP_PAGES):
            edges, page_info = self._get_products_page(
                self._current_project,
                folder_id=None,
                page_size=1000,
                cursor=cursor,
                sort_by="path",
                folder_ids=folder_ids,
                product_filter=query_filters["product_filter"],
                version_filter=(
                    query_filters["version_filter"]
                    if self._hide_empty_groups
                    else ""
                ),
                task_filter=(
                    query_filters["task_filter"]
                    if self._hide_empty_groups
                    else ""
                ),
                folder_filter=query_filters["folder_filter"],
                search=query_filters["search"],
                include_folder_children=self._include_folder_children,
            )
            all_edges.extend(edges)

            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break
        else:
            self.log.warning(
                "Product group pagination reached the safety"
                " limit of %d pages (%d products fetched)."
                " Results may be incomplete.",
                _MAX_GROUP_PAGES,
                len(all_edges),
            )

        product_data = self._extract_product_group_data(all_edges)
        # Keep first-seen product order while dropping duplicates.
        seen_product_ids: set[str] = set()
        unique_product_data: list[
            tuple[str, str, str, dict[str, Any]]
        ] = []
        for item in product_data:
            product_id = item[0]
            if product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            unique_product_data.append(item)

        if self._hide_empty_groups and group_counts is not None:
            unique_product_data = [
                item
                for item in unique_product_data
                if group_counts.get(item[0], 0) > 0
            ]

        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_PRODUCT_KEY],
                value=p_id,
                label=p_name,
                icon=self._pinfo("productTypes", p_type, "icon", "view_in_ar"),
                color=self._pinfo("productTypes", p_type, "color"),
                product_type=p_type,
                featured_version=featured_v,
                num_versions=(
                    group_counts.get(p_id, 0)
                    if group_counts is not None
                    else None
                ),
            )
            for p_id, p_name, p_type, featured_v in unique_product_data
        ]

    @staticmethod
    def _parse_group_id(group_id: str) -> tuple[str, str]:
        """Parse a group header id into (group_type, group_value).

        Args:
            group_id: String in the form ``"grp:<type>:<value>"``.

        Returns:
            Tuple of ``(group_type, group_value)``.
        """
        _, group_type, group_value = group_id.split(":", 2)
        return group_type, group_value

    def _build_version_filter(
        self,
        group_key: str,
        group_value: str,
    ) -> tuple[str, str]:
        """Build ``versionFilter`` and ``productFilter`` JSON strings.

        Handles built-in status/product-type groups and attribute groups.
        ``product`` is intentionally excluded — it passes
        ``product_ids`` directly to :meth:`_get_versions_page` in the
        expand flow and does not need a filter expression.

        Args:
            group_key: Group option key.
            group_value: The value to filter on.

        Returns:
            Tuple of ``(version_filter, product_filter)`` JSON strings.
            Either or both may be empty when no filter is needed for
            that axis.
        """
        version_filter = ""
        product_filter = ""
        if group_key == GROUP_BY_STATUS_KEY:
            version_filter = json.dumps(
                {
                    "conditions": [
                        {
                            "key": "status",
                            "value": [group_value],
                            "operator": "in",
                        },
                    ]
                }
            )
        elif group_key == GROUP_BY_PRODUCT_TYPE_KEY:
            product_filter = json.dumps(
                {
                    "conditions": [
                        {
                            "key": "productType",
                            "value": [group_value],
                            "operator": "in",
                        },
                    ]
                }
            )
        elif group_key == GROUP_BY_TAGS_KEY:
            version_filter = json.dumps(
                {
                    "conditions": [
                        {
                            "key": "tags",
                            "value": [group_value],
                            "operator": "includesany",
                        },
                    ]
                }
            )
        elif group_key == GROUP_BY_TASK_TYPE_KEY:
            version_filter = json.dumps(
                {
                    "conditions": [
                        {
                            "key": "taskType",
                            "value": [group_value],
                            "operator": "in",
                        },
                    ]
                }
            )
        elif group_key.startswith("attr:"):
            attribute_name = group_key.split(":", 1)[1]
            attr_type = self._version_attributes.get(attribute_name, {}).get(
                "type"
            )
            if attr_type == "integer":
                typed_value: Any = int(group_value)
            elif attr_type == "float":
                typed_value = float(group_value)
            elif attr_type == "boolean":
                typed_value = group_value.lower() in {"1", "true", "yes"}
            else:
                typed_value = group_value

            version_filter = json.dumps(
                {
                    "conditions": [
                        {
                            "key": f"attrib.{attribute_name}",
                            "value": typed_value,
                            "operator": "eq",
                        },
                    ]
                }
            )
        return version_filter, product_filter

    def _fetch_reviews(self, parent_id: str | None) -> list[TreeNode]:
        """Return tree nodes for review sessions.

        Read-only: builds :class:`TreeNode` objects from the pre-populated
        :attr:`_review_sessions_cache`.  The cache is populated exclusively
        from the main thread by :meth:`_get_review_session_list`, which is
        called inside :meth:`set_project`.  Pool worker threads that call
        this method therefore only perform read access on an already-complete
        list, eliminating any generator re-entrancy race.

        Args:
            parent_id: Parent entity ID. Only root (``None``) returns
                review session nodes; children are always empty.

        Returns:
            List of :class:`TreeNode` instances.
        """
        self.log.debug("Fetching review children for %s", parent_id)
        if parent_id is not None:
            return []
        return [
            TreeNode(
                id=r.get("id", "no id"),
                label=r.get("label", "no label"),
                has_children=False,
                icon="subscriptions",
                data=r,
            )
            for r in self._review_sessions_cache
            if r.get("entityListType") == "review-session"
        ]

    def _fetch_products(self, parent_id: str | None) -> list[TreeNode]:
        """Fetch folder hierarchy level by parent folder id.

        Args:
            parent_id: Parent folder ID, or ``None`` for root.

        Returns:
            List of :class:`TreeNode` instances.
        """
        project = self._current_project
        if not project:
            return []

        self.log.debug("Fetching product children for %s", parent_id)
        parent_ids = [parent_id] if parent_id is not None else [None]
        folders = list(ayon_api.get_folders(
            project,
            parent_ids=parent_ids,  # type: ignore[arg-type]
            fields={
                "id",
                "name",
                "label",
                "folderType",
                "hasChildren",
                "hasTasks",
                "parentId",
            },
        ))
        for folder in folders:
            self._folder_parent_ids[folder["id"]] = folder.get("parentId")
        if self._folder_id_scope is not None:
            folders = [
                f for f in folders if f["id"] in self._folder_id_scope
            ]
        return [
            TreeNode(
                id=f["id"],
                label=f.get("label") or f["name"],
                has_children=f.get("hasChildren", False),
                icon=self._pinfo(
                    "folderTypes", f.get("folderType", ""), "icon", "folder"
                ),
                data=f,
            )
            for f in folders
        ]

    def _get_review_session_list(self) -> None:
        """Fetch review sessions from the server and cache them as a list.

        Materialises the generator returned by
        :func:`ayon_api.get_entity_lists` into a plain Python list so that
        the result can be read safely by pool worker threads without the
        generator re-entrancy issue.  Must only be called from the main
        thread (e.g. inside :meth:`set_project`).
        """
        project = self._current_project
        self._review_sessions_cache = list(
            ayon_api.get_entity_lists(project_name=project)
        )
        self.log.debug(
            "Review sessions cached for project %s (%d items)",
            project,
            len(self._review_sessions_cache),
        )

    def _get_review_session_version_ids(self, session_id: str) -> list[str]:
        """Return version IDs contained in the given review session.

        Args:
            session_id: Entity list ID of the review session.

        Returns:
            List of version IDs.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            return []
        versions_gen = ayon_api.get_entity_lists(
            project_name=self._current_project,
            list_ids=[session_id],
            fields={"items"},
        )
        try:
            entity_list = next(versions_gen)
        except StopIteration:
            return []
        items = entity_list.get("items", [])
        return [
            item["entityId"]
            for item in items
            if item.get("entityType") == "version"
        ]

    def _build_project_info(self, project_name: str | None = None) -> None:
        """Populate project info and folder type icon mapping.

        Sets :attr:`_project_info` in place.

        Args:
            project_name: Override for the project to query. Defaults
                to :attr:`_current_project`.
        """
        name = project_name or self._current_project
        if not name:
            return
        project_entity = ayon_api.get_project(name)
        if not project_entity:
            return
        self._project_info = dict(project_entity)
        config = project_entity.get("config", {})
        product_base_types = config.get("productBaseTypes", {})
        self._project_info["by_name"] = {
            "folderTypes": {
                ft["name"]: ft for ft in project_entity.get("folderTypes", [])
            },
            "taskTypes": {
                tt["name"]: tt for tt in project_entity.get("taskTypes", [])
            },
            "linkTypes": {
                lt["name"]: lt for lt in project_entity.get("linkTypes", [])
            },
            "statuses": {
                s["name"]: s for s in project_entity.get("statuses", [])
            },
            "tags": {t["name"]: t for t in project_entity.get("tags", [])},
            "productTypes": (
                {
                    t["name"]: t
                    for t in product_base_types.get("definitions", [])
                }
                | {"default": product_base_types.get("default", {})}
            ),
            "productBaseTypes": {
                t["name"]: t
                for t in product_base_types.get("definitions", [])
            },
        }
        self._attributes_by_scope = {
            scope: ayon_api.get_attributes_for_type(scope)
            for scope in ("folder", "task", "product", "version")
        }
        self._version_attributes = self._attributes_by_scope["version"]
        self._rebuild_group_by_options()

    def _rebuild_group_by_options(self) -> None:
        """Recompute available group-by options from project metadata."""
        old_options = self._group_by_options.copy()
        options = list(BUILTIN_GROUPS)
        if self._version_attributes:
            options.extend(build_attribute_groups(self._version_attributes))
        self._group_by_options = {option.key: option for option in options}
        if self._group_by_key not in self._group_by_options:
            self._group_by_key = GROUP_BY_NONE_KEY
        if old_options != self._group_by_options:
            self.group_by_options_changed.emit(self._group_by_options.copy())

    def _normalize_group_by_key(
        self,
        group_by: GroupByOption | str,
    ) -> str:
        """Normalize option/label input to a registered key.

        Args:
            group_by: A :class:`GroupByOption` instance, an option key,
                or an option label.

        Returns:
            Registered key string, or :data:`GROUP_BY_NONE_KEY` when the
            input cannot be matched.
        """
        if isinstance(group_by, GroupByOption):
            return (
                group_by.key
                if group_by.key in self._group_by_options
                else GROUP_BY_NONE_KEY
            )

        if group_by in self._group_by_options:
            return group_by

        for option in self._group_by_options.values():
            if option.label == group_by:
                return option.key

        return GROUP_BY_NONE_KEY

    def _pinfo(
        self, category: str, name: str, key: str, default: Any = None
    ) -> Any:
        """Get a project info value by category and key.

        Args:
            category: One of ``"folderTypes"``, ``"taskTypes"``,
                ``"linkTypes"``, ``"statuses"``, ``"tags"``, or
                ``"productTypes"``.
            name: The name of the entity to look up within the category.
            key: The name of the item to look up.
            default: The value to return if the key is not found.

        Returns:
            The value for the given key in the given category, or the
            specified default.
        """
        return (
            self._project_info.get("by_name", {})
            .get(category, {})
            .get(name, {})
            .get(key, default)
        )

    def _get_versions_page(
        self,
        project_name: str,
        folder_id: str | None,
        page_size: int,
        cursor: str | None = None,
        sort_by: str | None = None,
        descending: bool = False,
        version_ids: list[str] | None = None,
        include_folder_children: bool = False,
        folder_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
        version_filter: str = "",
        product_filter: str = "",
        task_filter: str = "",
        folder_filter: str = "",
        featured_only: list[str] | None = None,
        latest_per_folder: bool = False,
        search: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch a single page of versions via GraphQL.

        Sort direction is expressed through the pagination parameters:
        ascending order uses ``first``/``after``, while descending order
        uses ``last``/``before``.  This maps directly onto the AYON
        backend's cursor-based pagination which applies ``DESC`` only
        when ``last`` is set.

        Args:
            project_name: AYON project name.
            folder_id: Filter by a single folder ID, or ``None``.
                Ignored when *folder_ids* is provided.
            page_size: Maximum number of edges to return.
            cursor: GraphQL cursor from the previous page, or ``None``
                for the first page.
            sort_by: Valid GraphQL ``sortBy`` value, or ``None`` to use
                the server default (``creation_order``).
            descending: When ``True`` use ``last``/``before`` pagination
                to obtain results in descending order.
            version_ids: Optional list of version IDs to restrict
                results to.
            include_folder_children: Whether to include versions from
                child folders.
            folder_ids: When provided, filters by this explicit list of
                folder IDs instead of the single *folder_id*.
            product_ids: When provided, filters versions to only those
                belonging to these product IDs.
            version_filter: JSON-encoded version filter string.
            product_filter: JSON-encoded product filter string.
            task_filter: JSON-encoded task filter string.
            folder_filter: JSON-encoded folder filter string.
            featured_only: Featured version types to query.
            latest_per_folder: Whether to return one version per folder.
            search: Full-text versions search string.

        Returns:
            Tuple of (edges list, pageInfo dict).

        Raises:
            RuntimeError: If there is no server connection or the
                query returns errors.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")

        if folder_ids is not None:
            resolved_folder_ids: list[str] | None = folder_ids
        elif folder_id is not None:
            resolved_folder_ids = [folder_id]
        else:
            resolved_folder_ids = None

        variables: dict[str, Any] = {
            "projectName": project_name,
            "versionFilter": version_filter or "",
            "productFilter": product_filter or "",
            "taskFilter": task_filter or "",
            "folderFilter": folder_filter or "",
            "featuredOnly": featured_only,
            "latestPerFolder": latest_per_folder,
            "search": search,
            "sortBy": sort_by,
            "folderIds": resolved_folder_ids,
            "includeFolderChildren": include_folder_children,
            "versionIds": version_ids if version_ids is not None else None,
            "productIds": product_ids if product_ids else None,
        }
        if descending:
            variables["last"] = page_size
            variables["before"] = cursor or None
        else:
            variables["first"] = page_size
            variables["after"] = cursor or None

        # self.log.info(GET_VERSIONS_QUERY)
        # self.log.info(variables)
        requested_keys = set(self._requested_column_keys or ())
        requested_keys.update(
            self._column_manager.get_required_query_keys(
                self._get_column_context()
            )
        )
        requested_keys.add("thumb")
        filter_field_keys = {
            "status": "status",
            "tags": "tags",
            "productType": "productType",
            "productBaseType": "productBaseType",
            "productStatus": "productStatus",
            "taskType": "taskType",
            "taskStatus": "taskStatus",
            "task": "task",
            "taskTags": "taskTags",
            "folderStatus": "folderStatus",
            "representationExtension": "representationExtension",
        }
        requested_keys.update(
            field_key
            for key, field_key in filter_field_keys.items()
            if any(item[0] == key for item in self._query_filter_criteria)
        )
        requested_keys.update(
            key
            for key, _, _ in self._query_filter_criteria
            if key.startswith("attr:")
        )
        resp = con.query_graphql(
            get_versions_query(requested_keys),
            variables,
        )

        if resp.errors:
            raise RuntimeError(resp.errors)
        payload = resp.data["data"]
        versions_block = payload["project"]["versions"]
        return versions_block["edges"], versions_block["pageInfo"]

    def _transform_version_edge(self, edge: dict[str, Any]) -> dict[str, Any]:
        """Transform a GraphQL version edge into a table row dict.

        Args:
            edge: A single GraphQL edge from the versions query.

        Returns:
            Flat dict suitable for
            :class:`~ayon_ui_qt.components.table_model.PaginatedTableModel`.
        """
        n = edge["node"]
        all_attrib = self._decode_attributes(n.get("allAttrib"))
        version_data = self._decode_attributes(n.get("data"))
        status = n.get("status", "")
        product = n.get("product", {})
        product_attrib = self._decode_attributes(product.get("allAttrib"))
        folder = product.get("folder", {}) or {}
        folder_attrib = self._decode_attributes(folder.get("allAttrib"))
        product_type = product.get("productType", "")
        product_base_type = product.get("productBaseType", "")
        task = n.get("task", {}) or {}
        task_attrib = self._decode_attributes(task.get("allAttrib"))
        frame_start = all_attrib.get("frameStart", "")
        frame_end = all_attrib.get("frameEnd", "")
        is_hero = n.get("name") == "HERO"
        version_name = n.get("name", "")
        if is_hero:
            version_number = abs(int(n.get("version", 0)))
            version_name = f"★ (v{version_number:03d})"
        in_scene = (
            True
            if n.get("id") in self._loader_controller.get_loaded_version_ids()
            else False
        )
        row = {
            "project_name": self._current_project,
            "thumbnail": n.get("thumbnailId") or "",
            "thumbnailId": n.get("thumbnailId") or "",
            "product/version": (
                f"{product.get('name', '')} - {version_name}"
            ),
            "product/version__icon": "layers",
            "status": status,
            "productStatus": product.get("status", ""),
            "folderStatus": folder.get("status", ""),
            "featuredVersionType": n.get("featuredVersionType", ""),
            "inScene": in_scene,
            "status__color": self._pinfo("statuses", status, "color"),
            "status__icon": self._pinfo("statuses", status, "icon"),
            "status__short": self._pinfo(
                "statuses", status, "shortName", ""
            ),
            "entityType": n.get("entityType", "Version"),
            "entityType__icon": "layers",
            "productType": product_type,
            "productBaseType": product_base_type or product_type,
            "productType__icon": self._pinfo(
                "productTypes", product_type, "icon"
            ),
            "productType__color": self._pinfo(
                "productTypes", product_type, "color"
            ),
            "folderName": folder.get("name", ""),
            "author": n.get("author", ""),
            "version": version_name,
            "productName": product.get("name", ""),
            "taskType": task.get("taskType", ""),
            "taskStatus": task.get("status", ""),
            "task": task.get("name", ""),
            "tags": ", ".join(n.get("tags", [])),
            "taskTags": ", ".join(task.get("tags", [])),
            "createdAt": _timestamp_to_date(n.get("createdAt", "")),
            "updatedAt": _timestamp_to_date(n.get("updatedAt", "")),
            "fps": all_attrib.get("fps", ""),
            "width": folder_attrib.get("resolutionWidth", ""),
            "height": folder_attrib.get("resolutionHeight", ""),
            "pixelAspect": folder_attrib.get("pixelAspect", ""),
            "clipIn": folder_attrib.get("clipIn", ""),
            "clipOut": folder_attrib.get("clipOut", ""),
            "frameStart": frame_start,
            "frameEnd": frame_end,
            "handleStart": all_attrib.get("handleStart", ""),
            "handleEnd": all_attrib.get("handleEnd", ""),
            "step": (
                all_attrib["step"]
                if "step" in all_attrib
                else version_data.get("step", "")
            ),
            "machine": all_attrib.get("machine", ""),
            "source": all_attrib.get("source", ""),
            "path": n.get("path", ""),
            "comment": all_attrib.get("comment", ""),
            "id": n.get("id", ""),
            "productId": product.get("id", ""),
            "folderId": folder.get("id", ""),
            "taskId": task.get("id", ""),
            "heroVersionId": n.get("heroVersionId", ""),
        }
        for scope, attributes in (
            ("version", all_attrib),
            ("product", product_attrib),
            ("task", task_attrib),
            ("folder", folder_attrib),
        ):
            for name, value in attributes.items():
                row[f"attr:{scope}:{name}"] = value
        return row
