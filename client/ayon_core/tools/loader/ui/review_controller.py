from __future__ import annotations

import datetime
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query
from ayon_ui_qt.components.table_model import BatchFetchRequest
from ayon_ui_qt.components.tree_model import TreeNode
from qtpy import QtCore

from ayon_core.lib import Logger
from ayon_core.tools.loader.abstract import ActionItem
from ayon_core.tools.loader.ui.review_types import ReviewCategory
from ayon_core.tools.utils.user_prefs import UserPreferences

if TYPE_CHECKING:
    from ayon_core.tools.loader.abstract import (
        FrontendLoaderController,
    )

GET_VERSIONS_QUERY = """
query GetVersions(
  $projectName: String!,
  $productIds: [String!],
  $versionIds: [String!],
  $versionFilter: String,
  $productFilter: String,
  $taskFilter: String,
  $featuredOnly: [String!],
  $hasReviewables: Boolean,
  $folderIds: [String!],
  $includeFolderChildren: Boolean,
  $search: String,
  $after: String,
  $first: Int,
  $before: String,
  $last: Int,
  $sortBy: String
) {
  project(name: $projectName) {
    versions(
      ids: $versionIds
      productIds: $productIds
      filter: $versionFilter
      productFilter: $productFilter
      taskFilter: $taskFilter
      featuredOnly: $featuredOnly
      hasReviewables: $hasReviewables
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      search: $search
      after: $after
      first: $first
      before: $before
      last: $last
      sortBy: $sortBy
    ) {
      pageInfo {
        startCursor
        endCursor
        hasNextPage
        hasPreviousPage
      }
      edges {
        cursor
        node {
          name
          id
          hasReviewables
          parents
          path
          active
          allAttrib
          author
          createdAt
          status
          tags
          updatedAt
          version
          featuredVersionType
          heroVersionId
          thumbnailId
          task {
            id
            taskType
            label
            name
          }
          product {
            id
            name
            productType
            allAttrib
            folder {
              id
              name
              label
              allAttrib
            }
          }
        }
      }
    }
  }
}
"""

GET_PRODUCTS_QUERY = """
query GetProducts(
  $projectName: String!,
  $folderIds: [String!],
  $productFilter: String,
  $featuredVersionOrder: [String!],
  $after: String,
  $first: Int,
  $before: String,
  $last: Int,
  $sortBy: String
) {
  project(name: $projectName) {
    products(
      folderIds: $folderIds,
      filter: $productFilter,
      includeFolderChildren: true,
      after: $after,
      first: $first,
      before: $before,
      last: $last,
      sortBy: $sortBy
    ) {
      pageInfo {
        startCursor
        endCursor
        hasNextPage
        hasPreviousPage
      }
      edges {
        node {
          id
          name
          productType
          featuredVersion(order: $featuredVersionOrder) {
            name
            id
            thumbnailId
            parents
            author
            createdAt
            status
            tags
            updatedAt
            version
            featuredVersionType
          }
          versions: versionList {
            id
            name
            version
          }
        }
        cursor
      }
    }
  }
}
"""

#: Maps table column keys to valid GraphQL ``sortBy`` values accepted by
#: the AYON versions resolver.  Only direct version fields and version
#: attrib entries are supported; columns that originate from related
#: entities (products, folders, tasks) cannot be sorted server-side and
#: are intentionally absent — clicking them is a no-op.
COLUMN_TO_SORT_BY: dict[str, str] = {
    "version": "version",
    "status": "status",
    "createdAt": "createdAt",
    "updatedAt": "updatedAt",
    "fps": "attrib.fps",
    "handleStart": "attrib.handleStart",
    "handleEnd": "attrib.handleEnd",
    "machine": "attrib.machine",
    "source": "attrib.source",
    "comment": "attrib.comment",
}

# A template for building version and folder rows.
EMPTY_ROW: MappingProxyType[str, Any] = MappingProxyType(
    {
        "id": "",
        "has_children": False,
        "product/version": "",
        "product/version__icon": "",
        "folderName": "",
        "entityType": "",
        "entityType__icon": "",
        "status": "",
        "productType": "",
        "author": "",
        "version": "",
        "productName": "",
        "taskType": "",
        "task": "",
        "tags": "",
        "createdAt": "",
        "updatedAt": "",
    }
)


def timestamp_to_date(timestamp: str) -> str:
    """Convert ISO timestamp string to human-readable date.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Formatted date string as DD-MM-YYYY HH:MM:SS.
    """
    return datetime.datetime.fromisoformat(timestamp).strftime(
        "%d-%m-%Y %H:%M:%S"
    )


def get_attribute_icon(
    name: str,
    attr_type: str | None,
    has_enum: bool,
    # entity_types_with_icons: list[str] | set[str],
    # get_entity_type_icon,
) -> str:
    """Based on shared/src/util/getAttributeIcon.ts.

    Args:
        name: Attribute name.
        attr_type: Attribute type.
        has_enum: Whether the attribute has an enum.
        entity_types_with_icons: List of entity types with icons.
        get_entity_type_icon: Function to get entity type icon.
    Returns:
        Icon name string.
    """

    icon = "format_list_bulleted"

    # Some attributes have custom icons
    custom_icons: dict[str, str] = {
        "status": "arrow_circle_right",
        "assignees": "person",
        "author": "person",
        "tags": "local_offer",
        "priority": "keyboard_double_arrow_up",
        "fps": "30fps_select",
        "resolutionWidth": "settings_overscan",
        "resolutionHeight": "settings_overscan",
        "pixelAspect": "stop",
        "clipIn": "line_start_diamond",
        "clipOut": "line_end_diamond",
        "frameStart": "line_start_circle",
        "frameEnd": "line_end_circle",
        "handleStart": "line_start_square",
        "handleEnd": "line_end_square",
        "fullName": "id_card",
        "email": "alternate_email",
        "developerMode": "code",
        "productGroup": "inventory_2",
        "machine": "computer",
        "comment": "comment",
        "colorSpace": "palette",
        "description": "description",
    }

    type_icons: dict[str, str] = {
        "integer": "pin",
        "float": "speed_1_2",
        "boolean": "radio_button_checked",
        "datetime": "calendar_month",
        "list_of_strings": "format_list_bulleted",
        "list_of_integers": "format_list_numbered",
        "list_of_any": "format_list_bulleted",
        "list_of_submodels": "format_list_bulleted",
        "dict": "format_list_bulleted",
        "string": "title",
    }

    if name in custom_icons:
        icon = custom_icons[name]
    # elif name in entity_types_with_icons:
    #     icon = get_entity_type_icon(name)
    elif has_enum:
        icon = "format_list_bulleted"
    elif attr_type and attr_type in type_icons:
        icon = type_icons[attr_type]

    return icon


class GroupBySource(Enum):
    BUILTIN = "builtin"
    ATTRIBUTE = "attribute"


@dataclass(frozen=True)
class GroupByOption:
    key: str
    label: str
    icon: str = "label"
    source: GroupBySource = GroupBySource.BUILTIN
    attribute_name: str | None = None


BUILTIN_GROUPS = [
    GroupByOption("none", "None", "close"),
    GroupByOption("product", "Product", "inventory_2"),
    GroupByOption("status", "Status", "arrow_circle_right"),
    GroupByOption("tags", "Tags", "local_offer"),
    GroupByOption("task_type", "Task type", "check_circle"),
    GroupByOption("product_type", "Product type", "category"),
]

NUM_BUILTIN_GROUPS = len(BUILTIN_GROUPS)

GROUP_BY_NONE_KEY = "none"
GROUP_BY_PRODUCT_KEY = "product"
GROUP_BY_STATUS_KEY = "status"
GROUP_BY_TAGS_KEY = "tags"
GROUP_BY_TASK_TYPE_KEY = "task_type"
GROUP_BY_PRODUCT_TYPE_KEY = "product_type"


def build_attribute_groups(
    version_attributes: dict[str, dict[str, Any]],
) -> list[GroupByOption]:
    return [
        GroupByOption(
            key=f"attr:{attr_name}",
            label=attr_def.get("title") or attr_name,
            icon=get_attribute_icon(
                attr_name,
                attr_def.get("type"),
                attr_def.get("enum") is not None,
            ),
            source=GroupBySource.ATTRIBUTE,
            attribute_name=attr_name,
        )
        for attr_name, attr_def in version_attributes.items()
    ]


# Maximum number of pages to fetch when building product group
# headers.  Each page contains up to 1 000 products, so this caps
# the total at 50 000 products before a warning is logged.
_MAX_GROUP_PAGES: int = 50


class ReviewController(QtCore.QObject):
    """Controller for the Reviews widget.

    Centralises all business logic and data fetching for the reviews
    UI. Emits signals when state changes so that widgets can react.
    """

    project_changed = QtCore.Signal(str)  # type: ignore
    project_info_changed = QtCore.Signal()  # type: ignore
    category_changed = QtCore.Signal(str)  # type: ignore
    tree_reset_requested = QtCore.Signal()  # type: ignore
    selection_changed = QtCore.Signal(str, str)  # type: ignore
    group_by_options_changed = QtCore.Signal(dict)  # type: ignore

    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        loader_controller: FrontendLoaderController | None = None,
    ) -> None:
        super().__init__(parent)
        self._loader_controller = loader_controller
        self._current_project: str = ""
        self._current_category: str = ReviewCategory.HIERARCHY.value
        self._project_info: dict[str, Any] = {}
        self._review_sessions_cache: list[dict[str, Any]] = []
        self._graphql_has_more: bool = False
        self._graphql_cursor: str = ""
        self._folder_cursors: dict[str, str] = {}
        self._folder_has_more: dict[str, bool] = {}
        self._tree_mode: bool = True
        self._selected_folder_id: str | None = None
        self._review_session_version_ids: list[str] | None = None
        self._version_attributes: dict[str, Any] = {}
        self._group_by_options: dict[str, GroupByOption] = {
            option.key: option for option in BUILTIN_GROUPS
        }
        self._group_by_key: str = GROUP_BY_NONE_KEY
        self._hide_empty_groups: bool = True
        self.log = Logger.get_logger(self.__class__.__name__)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_project(self) -> str:
        """Return the currently active project name."""
        return self._current_project

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
    def tree_mode(self) -> bool:
        """Return whether tree mode is currently active."""
        return self._tree_mode

    @property
    def selected_folder_id(self) -> str | None:
        """Return the folder ID currently selected in the slicer tree."""
        return self._selected_folder_id

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

    @property
    def hide_empty_groups(self) -> bool:
        """Return whether empty group headers should be hidden."""
        return self._hide_empty_groups

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_project(self, project_name: str) -> None:
        """Set the active project and refresh data.

        Args:
            project_name: AYON project name to activate.
        """
        self._current_project = project_name
        self._review_sessions_cache = []
        self._reset_pagination()
        self._selected_folder_id = None
        self._build_project_info()
        self._get_review_session_list()
        self.project_changed.emit(project_name)
        self.project_info_changed.emit()
        self.tree_reset_requested.emit()
        UserPreferences().set("loader.review.last_project", project_name)

    def set_category(self, category: str) -> None:
        """Set the active slicer category.

        Args:
            category: Category name, e.g. ``"Hierarchy"`` or
                ``"Reviews"``.
        """
        self._current_category = category
        self._selected_folder_id = None
        self._review_session_version_ids = None
        self._reset_pagination()
        self.category_changed.emit(category)
        self.tree_reset_requested.emit()
        UserPreferences().set("loader.review.last_category", category)

    def on_tree_selection_changed(self, id: str, name: str) -> None:
        """Handle a selection change in the tree view.

        Args:
            id: ID of the selected entity, or empty string when
                deselected.
            name: Name of the selected entity.
        """
        self._selected_folder_id = id if id else None
        self._review_session_version_ids = None  # always clear first

        if self._current_category == ReviewCategory.REVIEWS.value and id:
            self._review_session_version_ids = (
                self._get_review_session_version_ids(id)
            )

        self._reset_pagination()
        self.selection_changed.emit(id, name)

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

    def fetch_children(self, parent_id: str | None) -> list[TreeNode]:
        """Return tree nodes for the given parent.

        Dispatches to :meth:`_fetch_products` or
        :meth:`_fetch_reviews` depending on the current category.
        Ensures project info is populated before fetching.

        Args:
            parent_id: Parent entity ID, or ``None`` for root.

        Returns:
            List of :class:`TreeNode` instances.
        """
        if self._current_category == ReviewCategory.HIERARCHY.value:
            return self._fetch_products(parent_id)
        return self._fetch_reviews(parent_id)

    def fetch_versions_page(
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

        if page_number == 0:
            if parent_id is not None:
                self._folder_cursors.pop(parent_id, None)
                self._folder_has_more.pop(parent_id, None)
            else:
                self._reset_pagination()

        sort_by = COLUMN_TO_SORT_BY.get(sort_key) if sort_key else None
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
            self._current_category == ReviewCategory.HIERARCHY.value
            and self.group_by_key != GROUP_BY_NONE_KEY
        ):
            # Root level: return group header rows.
            if parent_id is None:
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

                cursor = self._folder_cursors.get(parent_id, "")
                if page_number > 0 and not self._folder_has_more.get(
                    parent_id, False
                ):
                    return []

                folder_id = self._selected_folder_id
                version_ids = None

                edges, page_info = self._get_versions_page(
                    self._current_project,
                    folder_id,
                    page_size,
                    cursor=cursor,
                    sort_by=sort_by,
                    descending=descending,
                    version_ids=version_ids,
                    include_folder_children=True,
                    product_ids=product_ids,
                    version_filter=version_filter,
                    product_filter=product_filter,
                )
                rows = [
                    self._transform_version_edge(e)
                    for e in edges
                    if e.get("node", {}).get("name") != "HERO"
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
            and self._current_category == ReviewCategory.HIERARCHY.value
        ):
            return self._fetch_root_folders(self._selected_folder_id)

        # Child versions for a specific folder (tree-mode expand).
        if parent_id is not None:
            # On the first page, prepend direct sub-folder rows so that
            # the tree can be navigated depth-first all the way down to
            # version leaves.
            if page_number == 0:
                folder_rows = self._get_child_folder_rows(parent_id)
            else:
                folder_rows = []

            cursor = self._folder_cursors.get(parent_id, "")
            if page_number > 0 and not self._folder_has_more.get(
                parent_id, False
            ):
                return []
            edges, page_info = self._get_versions_page(
                self._current_project,
                parent_id,
                page_size,
                cursor=cursor,
                sort_by=sort_by,
                descending=descending,
                include_folder_children=False,
            )
            version_rows = [
                self._transform_version_edge(e)
                for e in edges
                if e.get("node", {}).get("name") != "HERO"
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

        # Flat mode: existing behaviour.
        if self._current_category == ReviewCategory.REVIEWS.value:
            folder_id = None
            version_ids = self._review_session_version_ids  # None = no filter
            if not version_ids:
                # No review session selected yet — show nothing
                return []
        else:
            folder_id = self._selected_folder_id
            version_ids = None

        edges, page_info = self._get_versions_page(
            self._current_project,
            folder_id,
            page_size,
            cursor=self._graphql_cursor,
            sort_by=sort_by,
            descending=descending,
            version_ids=version_ids,
        )
        self.log.debug(
            "Received %d edges, page info: %s", len(edges), page_info
        )
        page = [
            self._transform_version_edge(e)
            for e in edges
            if e.get("node", {}).get("name") != "HERO"
        ]

        if descending:
            self._graphql_has_more = page_info["hasPreviousPage"]
            self._graphql_cursor = page_info["startCursor"]
        else:
            self._graphql_has_more = page_info["hasNextPage"]
            self._graphql_cursor = page_info["endCursor"]

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

        result: dict[str | None, list[dict[str, Any]]] = {}

        # Separate group-by requests (must be fetched individually) from
        # plain hierarchy requests (can be batched).
        grp_requests: list[BatchFetchRequest] = []
        batch_requests: list[BatchFetchRequest] = []
        for req in requests:
            if req.parent_id and req.parent_id.startswith("grp:"):
                grp_requests.append(req)
            else:
                batch_requests.append(req)

        # -- Individual group-by fetches ---------------------------------
        for req in grp_requests:
            rows = self.fetch_versions_page(
                req.page,
                req.page_size,
                req.sort_key,
                req.descending,
                req.parent_id,
            )
            result[req.parent_id] = rows

        # -- Hierarchy fetches -------------------------------------------
        if not batch_requests:
            return result

        # Keep execution inside one worker task (batch callback path),
        # but fetch each parent with its own cursor state to preserve
        # correctness for cursor-based pagination.
        for req in batch_requests:
            if req.parent_id is None:
                rows = self.fetch_versions_page(
                    req.page,
                    req.page_size,
                    req.sort_key,
                    req.descending,
                    req.parent_id,
                )
                result[req.parent_id] = rows
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
            edges, page_info = self._get_versions_page(
                self._current_project,
                parent_id,
                req.page_size,
                cursor=cursor,
                sort_by=sort_by,
                descending=req.descending,
                include_folder_children=False,
            )

            version_rows = [
                self._transform_version_edge(e)
                for e in edges
                if e.get("node", {}).get("name") != "HERO"
            ]
            folder_rows = (
                self._get_child_folder_rows(parent_id) if req.page == 0 else []
            )

            if req.descending:
                self._folder_has_more[parent_id] = page_info["hasPreviousPage"]
                self._folder_cursors[parent_id] = page_info["startCursor"]
            else:
                self._folder_has_more[parent_id] = page_info["hasNextPage"]
                self._folder_cursors[parent_id] = page_info["endCursor"]

            result[parent_id] = folder_rows + version_rows

        return result

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
        if self._loader_controller is None:
            return []
        return self._loader_controller.get_action_items(
            project_name, entity_ids, entity_type
        )

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
        if self._loader_controller is None:
            return
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

    def _fetch_root_folders(
        self, selected_folder_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Fetch folders to use as tree root rows.

        When *selected_folder_id* is given the selected folder is
        returned as the sole root row so the table shows that folder
        expanded.  Otherwise, all top-level folders (depth 1) are
        returned collapsed.

        Args:
            selected_folder_id: ID of the folder currently selected in
                the slicer tree, or ``None`` for the default root view.

        Returns:
            List of row dicts with ``has_children=True`` so the table
            model renders them as expandable nodes.
        """
        if selected_folder_id:
            folders = list(
                ayon_api.get_folders(
                    self._current_project,
                    folder_ids=[selected_folder_id],
                    fields={
                        "id",
                        "name",
                        "label",
                        "folderType",
                        "hasChildren",
                    },
                )
            )
        else:
            folders = list(
                ayon_api.get_folders(
                    self._current_project,
                    parent_ids=[None],  # type: ignore[list-item]
                    fields={
                        "id",
                        "name",
                        "label",
                        "folderType",
                        "hasChildren",
                    },
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
            fields={"id", "name", "label", "folderType", "hasChildren"},
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
        num_versions: int = 0,
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
                ``"product/version"`` column instead of *value*. This
                allows callers such as PRODUCT group-by to store a UUID
                in the group id while showing a human-readable name.
            product_type: Optional product type string, required when
                *featured_version* is provided.
            featured_version: Optional dict representing the featured version.
            num_versions: Optional number of versions in the group.
        Returns:
            Row dict with ``has_children=True`` and an id of the form
            ``"grp:<group_type.value>:<value>"``.
        """
        row = dict(EMPTY_ROW)
        row.update(
            {
                "id": f"grp:{group_option.key}:{value}",
                "has_children": True,
                "product/version": label if label is not None else value,
                "product/version__icon": icon or "label",
                "entityType": group_option.label,
                "entityType__icon": group_option.icon,
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
            row["status"] = featured_version.get("status", "")
            row["status__icon"] = self._pinfo(
                "statuses", row["status"], "icon", ""
            )
            row["status__color"] = self._pinfo(
                "statuses", row["status"], "color", ""
            )
            row["productType"] = product_type
            row["productType__icon"] = self._pinfo(
                "productTypes", product_type, "icon", "category"
            )
            row["folderName"] = featured_version.get("parents", ["", ""])[-2]
            row["author"] = featured_version.get("author", "")
            v_str = (
                f"{'(' + str(num_versions) + ' versions)'}"
                if num_versions
                else ""
            )
            row["version"] = f"{featured_version.get('name', '')} {v_str}"
            row["productName"] = featured_version.get("parents", [""])[-1]
            row["createdAt"] = featured_version.get("createdAt", "")
            row["updatedAt"] = featured_version.get("updatedAt", "")
        return row

    def _fetch_group_headers(self) -> list[dict[str, Any]]:
        """Dispatch to the appropriate group-header fetcher.

        Returns:
            List of expandable group-header rows.
        """
        if self.group_by_key == GROUP_BY_STATUS_KEY:
            return self._fetch_status_group_headers()
        if self.group_by_key == GROUP_BY_PRODUCT_TYPE_KEY:
            return self._fetch_product_type_group_headers()
        if self.group_by_key == GROUP_BY_PRODUCT_KEY:
            return self._fetch_product_group_headers()
        if self.group_by_key == GROUP_BY_TAGS_KEY:
            return self._fetch_tags_group_headers()
        if self.group_by_key == GROUP_BY_TASK_TYPE_KEY:
            return self._fetch_task_type_group_headers()
        if self.group_by.source == GroupBySource.ATTRIBUTE:
            return self._fetch_attribute_group_headers(self.group_by)
        self.log.warning(f"Unknown group-by key: {self.group_by_key}")
        return []

    def _fetch_status_group_headers(self) -> list[dict[str, Any]]:
        """Return one expandable row per status that has versions.

        Uses a single large-page fetch to discover which statuses
        actually contain versions for the current scope, then builds
        group-header rows only for those statuses.
        """
        all_statuses: dict[str, dict[str, Any]] = self._project_info.get(
            "by_name", {}
        ).get("statuses", {})
        if not all_statuses:
            return []

        if self._hide_empty_groups:
            present = self._get_distinct_field_values("status")
            status_names = [s for s in all_statuses if s in present]
        else:
            status_names = list(all_statuses)

        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_STATUS_KEY],
                name,
                icon=all_statuses[name].get("icon", "circle"),
                color=all_statuses[name].get("color"),
            )
            for name in status_names
        ]

    def _fetch_product_type_group_headers(self) -> list[dict[str, Any]]:
        """Return one expandable row per product type with versions."""
        present = self._get_distinct_field_values("productType")
        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_PRODUCT_TYPE_KEY],
                pt,
                icon=self._pinfo("productTypes", pt, "icon", "category"),
                color=self._pinfo("productTypes", pt, "color"),
            )
            for pt in sorted(present)
        ]

    def _fetch_tags_group_headers(self) -> list[dict[str, Any]]:
        self.log.warning("TODO: fetch tags group headers")
        return []

    def _fetch_task_type_group_headers(self) -> list[dict[str, Any]]:
        self.log.warning("TODO: fetch task type group headers")
        return []

    def _fetch_attribute_group_headers(
        self,
        group_option: GroupByOption,
    ) -> list[dict[str, Any]]:
        """Return one expandable row per used custom attribute value."""
        attr_name = group_option.attribute_name
        if not attr_name:
            return []

        values = self.get_used_attribute_values(attr_name)
        return [
            self._build_group_header_row(group_option, value)
            for value in sorted(values, key=str.casefold)
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
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch a single page of products via GraphQL.

        Only the fields needed for group-header rows (``id``,
        ``name``, ``productType``) are requested from the server.

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

        Returns:
            Tuple of (edges list, pageInfo dict).

        Raises:
            RuntimeError: If there is no server connection or the
                query returns errors.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")

        resolved_folder_ids: list[str] | None
        if folder_ids is not None:
            resolved_folder_ids = folder_ids
        elif folder_id is not None:
            resolved_folder_ids = [folder_id]
        else:
            resolved_folder_ids = None

        variables: dict[str, Any] = {
            "projectName": project_name,
            "productFilter": product_filter or "",
            "sortBy": sort_by,
            "folderIds": resolved_folder_ids,
            "featuredVersionOrder": ["latestDone", "latest", "hero"],
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
    ) -> list[tuple[str, str, str, dict[str, Any], int]]:
        """Transform raw product edges into structured tuples.

        Args:
            edges: List of GraphQL product edges from
                :meth:`_get_products_page`.

        Returns:
            List of ``(product_id, product_name, product_type,
            featured_version, num_versions)`` tuples.
        """
        result: list[tuple[str, str, str, dict[str, Any], int]] = []
        for edge in edges:
            node = edge.get("node", {})
            product_id = node.get("id", "")
            product_name = node.get("name", "")
            product_type = node.get("productType", "")
            featured_version = node.get("featuredVersion", {})
            num_versions = len(node.get("versions", []))
            if product_id and product_name:
                result.append(
                    (
                        product_id,
                        product_name,
                        product_type,
                        featured_version,
                        num_versions,
                    )
                )
        return result

    def _fetch_product_group_headers(self) -> list[dict[str, Any]]:
        """Return one expandable row per product in the current scope.

        Fetches products via :meth:`_get_products_page`, extracts
        structured tuples via :meth:`_extract_product_group_data`, then
        builds group-header rows using product ID as the group value and
        product name as the display label.

        Returns:
            List of expandable group-header rows keyed by product ID.
        """
        folder_id = self._selected_folder_id
        all_edges: list[dict[str, Any]] = []
        cursor: str | None = None

        for _page in range(_MAX_GROUP_PAGES):
            edges, page_info = self._get_products_page(
                self._current_project,
                folder_id=folder_id,
                page_size=1000,
                cursor=cursor,
                sort_by="path",
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
            tuple[str, str, str, dict[str, Any], int]
        ] = []
        for (
            product_id,
            product_name,
            product_type,
            featured_version,
            num_versions,
        ) in product_data:
            if product_id in seen_product_ids:
                continue
            seen_product_ids.add(product_id)
            unique_product_data.append(
                (
                    product_id,
                    product_name,
                    product_type,
                    featured_version,
                    num_versions,
                )
            )

        return [
            self._build_group_header_row(
                self._group_by_options[GROUP_BY_PRODUCT_KEY],
                value=p_id,
                label=p_name,
                icon=self._pinfo("productTypes", p_type, "icon", "view_in_ar"),
                color=self._pinfo("productTypes", p_type, "color"),
                product_type=p_type,
                featured_version=featured_v,
                num_versions=n_vers,
            )
            for p_id, p_name, p_type, featured_v, n_vers in unique_product_data
        ]

    def get_used_statuses(self) -> set[str]:
        """Fetch a list of statuses that have versions in the current scope.

        NOTE: it returns results for the entire project, not the current scope.

        Returns:
            Set of statuses that have versions in the current scope.
        """
        pld = ayon_api.get(
            f"projects/{self._current_project}/grouping/version/status",
            empty=True,
        )
        data = pld.data or {}
        used = [
            s.get("value")
            for s in data.get("groups", [])
            if s.get("count", 0) > 0
        ]
        return set(used)

    def get_used_product_types(self) -> set[str]:
        """Fetch a list of product types that have versions in the current
        scope.

        NOTE: it returns results for the entire project, not the current scope.

        Returns:
            Set of product types that have versions in the current scope.
        """
        pld = ayon_api.get(
            f"projects/{self._current_project}/grouping/version/productType",
            empty=True,
        )
        data = pld.data or {}
        used = [
            s.get("value")
            for s in data.get("groups", [])
            if s.get("count", 0) > 0
        ]
        return set(used)

    def get_used_attribute_values(self, attribute_name: str) -> set[str]:
        """Fetch distinct values for a version attribute in scope."""
        pld = ayon_api.get(
            f"projects/{self._current_project}/grouping/version/attrib.{attribute_name}",
            empty=True,
        )
        data = pld.data or {}
        used = [
            str(group.get("value"))
            for group in data.get("groups", [])
            if group.get("count", 0) > 0 and group.get("value") is not None
        ]
        return set(used)

    def _get_distinct_field_values(self, field: str) -> set[str]:
        """Fetch a  list of distinct values for a field.

        Args:
            field: One of ``"status"`` or ``"productType"``.

        Returns:
            Set of distinct values for that field among versions in the
            current scope.
        """

        if self._current_category == ReviewCategory.REVIEWS.value:
            if not self._review_session_version_ids:
                return set()

        if field == "status":
            return self.get_used_statuses()
        if field == "productType":
            return self.get_used_product_types()

        raise ValueError(f"Unknown field: {field}")

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
        elif group_key.startswith("attr:"):
            attribute_name = group_key.split(":", 1)[1]
            attr_type = self._version_attributes.get(attribute_name, {}).get("type")
            if attr_type == "integer":
                typed_value = int(group_value)
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
                            "value": [typed_value],
                            "operator": "in",
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
        list, eliminating the previous generator re-entrancy race.

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
        self.log.debug("Fetching product children for %s", parent_id)
        project = self._current_project
        if not project:
            return []

        parent_ids = [parent_id] if parent_id is not None else [None]
        folders = ayon_api.get_folders(
            project,
            parent_ids=parent_ids,  # type: ignore[arg-type]
            fields={
                "id",
                "name",
                "label",
                "folderType",
                "hasChildren",
                "hasTasks",
            },
        )
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
            "productTypes": {
                t["name"]: t
                for t in project_entity.get("config", {})
                .get("productBaseTypes", {})
                .get("definitions", [])
            }
            | {
                "default": (
                    project_entity.get("config", {})
                    .get("productBaseTypes", {})
                    .get("default", {})
                )
            },
        }
        self._version_attributes = ayon_api.get_attributes_for_type("version")
        # print(f"_version_attributes = {self._version_attributes}")
        self._rebuild_group_by_options()

    def _rebuild_group_by_options(self) -> None:
        """Recompute available group-by options from project metadata."""
        old_options = self._group_by_options.copy()
        options = list(BUILTIN_GROUPS)
        if self._version_attributes:
            options.extend(build_attribute_groups(self._version_attributes))
            # print(f"options; {options}")
        self._group_by_options = {option.key: option for option in options}
        if self._group_by_key not in self._group_by_options:
            self._group_by_key = GROUP_BY_NONE_KEY
        if old_options != self._group_by_options:
            self.group_by_options_changed.emit(self._group_by_options.copy())

    def _normalize_group_by_key(
        self,
        group_by: GroupByOption | str,
    ) -> str:
        """Normalize option/label input to a registered key."""
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

    def _pinfo(self, category: str, name: str, key: str, default=None) -> Any:
        """Get a project info value by category and key.

        Args:
            category: One of "folderTypes", "taskTypes", "linkTypes",
                "statuses", or "tags".
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
        include_folder_children: bool = True,
        folder_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
        version_filter: str = "",
        product_filter: str = "",
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
            folder_ids: When provided, filters by this explicit list of
                folder IDs instead of the single *folder_id*. Used by
                :meth:`fetch_versions_page_batch` to query multiple
                parents in one shot.
            product_ids: When provided, filters versions to only those
                belonging to these product IDs. Used when expanding a
                product group header.

        Returns:
            Tuple of (edges list, pageInfo dict).

        Raises:
            RuntimeError: If there is no server connection or the
                query returns errors.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")

        resolved_folder_ids: list[str] | None
        if folder_ids is not None:
            resolved_folder_ids = folder_ids
        elif folder_id is not None:
            resolved_folder_ids = [folder_id]
        else:
            resolved_folder_ids = None

        variables: dict[str, Any] = {
            "projectName": project_name,
            "versionFilter": version_filter or "",
            "productFilter": product_filter or "",
            "taskFilter": "",
            "sortBy": sort_by,
            "folderIds": resolved_folder_ids,
            "includeFolderChildren": include_folder_children,
            "versionIds": version_ids if version_ids else None,
            "productIds": product_ids if product_ids else None,
        }
        if descending:
            variables["last"] = page_size
            variables["before"] = cursor or None
        else:
            variables["first"] = page_size
            variables["after"] = cursor or None
        resp = con.query_graphql(GET_VERSIONS_QUERY, variables)
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
        all_attrib = json.loads(n.get("allAttrib", "{}"))
        product_folder_attrib = json.loads(
            n.get("product", {}).get("folder", {}).get("allAttrib", "{}")
        )
        status = n.get("status", "")
        return {
            "project_name": self._current_project,
            "thumbnail": n.get("thumbnailId") or "",
            "thumbnailId": n.get("thumbnailId") or "",
            "product/version": (
                f"{n.get('product', {}).get('name', '')} - {n.get('name', '')}"
                f"{'  ★' if n.get('heroVersionId') else ''}"
            ),
            "product/version__icon": "layers",
            "status": status,
            "status__color": self._pinfo("statuses", status, "color"),
            "status__icon": self._pinfo("statuses", status, "icon"),
            "entityType": n.get("entityType", "Version"),
            "entityType__icon": "layers",
            "productType": n.get("product", {}).get("productType", ""),
            "productType__icon": (
                self._pinfo(
                    "productTypes",
                    n.get("product", {}).get("productType", ""),
                    "icon",
                )
            ),
            "productType__color": (
                self._pinfo(
                    "productTypes",
                    n.get("product", {}).get("productType", ""),
                    "color",
                )
            ),
            "folderName": (
                n.get("product", {}).get("folder", {}).get("name", "")
            ),
            "author": n.get("author", ""),
            "version": n.get("name", ""),
            "productName": n.get("product", {}).get("name", ""),
            "taskType": (n.get("task", {}) or {}).get("taskType", ""),
            "task": (n.get("task", {}) or {}).get("name", ""),
            "tags": ", ".join(n.get("tags", [])),
            "createdAt": timestamp_to_date(n.get("createdAt", "")),
            "updatedAt": timestamp_to_date(n.get("updatedAt", "")),
            "fps": all_attrib.get("fps", ""),
            "width": product_folder_attrib.get("resolutionWidth", ""),
            "height": product_folder_attrib.get("resolutionHeight", ""),
            "pixelAspect": product_folder_attrib.get("pixelAspect", ""),
            "clipIn": product_folder_attrib.get("clipIn", ""),
            "clipOut": product_folder_attrib.get("clipOut", ""),
            "frameStart": product_folder_attrib.get("frameStart", ""),
            "frameEnd": product_folder_attrib.get("frameEnd", ""),
            "handleStart": all_attrib.get("handleStart", ""),
            "handleEnd": all_attrib.get("handleEnd", ""),
            "machine": all_attrib.get("machine", ""),
            "source": all_attrib.get("source", ""),
            "path": n.get("path", ""),
            "comment": all_attrib.get("comment", ""),
            "id": n.get("id", ""),
            "productId": n.get("product", {}).get("id", ""),
            "folderId": (n.get("product", {}).get("folder", {}).get("id", "")),
            "taskId": (n.get("task", {}) or {}).get("id", ""),
        }
