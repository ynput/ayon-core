from __future__ import annotations

import json
import logging
import datetime
from typing import Any

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query
from ayon_ui_qt.components.tree_model import TreeNode
from qtpy import QtCore

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
      includeFolderChildren: true
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


class ReviewController(QtCore.QObject):
    """Controller for the Reviews widget.

    Centralises all business logic and data fetching for the reviews
    UI. Emits signals when state changes so that widgets can react.
    """

    project_changed = QtCore.Signal(str)
    project_info_changed = QtCore.Signal()
    category_changed = QtCore.Signal(str)
    tree_reset_requested = QtCore.Signal()
    selection_changed = QtCore.Signal(str, str)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._current_project: str = ""
        self._current_category: str = "Hierarchy"
        self._project_info: dict[str, Any] = {}
        self._folder_type_icons: dict[str, str] = {}
        self._review_data: Any = None  # generator or None if not fetched
        self._graphql_has_next_page: bool = False
        self._graphql_after: str = ""
        self._selected_folder_id: str | None = None
        self.log = logging.getLogger(
            "ayon_core.tools.loader.review_controller"
        )

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
    def folder_type_icons(self) -> dict[str, str]:
        """Return mapping of folder type name to icon name."""
        return self._folder_type_icons

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def set_project(self, project_name: str) -> None:
        """Set the active project and refresh data.

        Args:
            project_name: AYON project name to activate.
        """
        self._current_project = project_name
        self._review_data = None
        self._graphql_after = ""
        self._graphql_has_next_page = False
        self._selected_folder_id = None
        self._build_project_info()
        self._get_reviews()
        self.project_changed.emit(project_name)
        self.project_info_changed.emit()
        self.tree_reset_requested.emit()

    def set_category(self, category: str) -> None:
        """Set the active slicer category.

        Args:
            category: Category name, e.g. ``"Hierarchy"`` or
                ``"Reviews"``.
        """
        self._current_category = category
        self._selected_folder_id = None
        self._graphql_after = ""
        self._graphql_has_next_page = False
        self.category_changed.emit(category)
        self.tree_reset_requested.emit()

    def on_tree_selection_changed(self, id: str, name: str) -> None:
        """Handle a selection change in the tree view.

        Args:
            id: ID of the selected entity, or empty string when
                deselected.
            name: Name of the selected entity.
        """
        self._selected_folder_id = id if id else None
        self._graphql_after = ""
        self._graphql_has_next_page = False
        self.selection_changed.emit(id, name)

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
        if not self._folder_type_icons:
            self._build_project_info()
        if self._current_category == "Hierarchy":
            return self._fetch_products(parent_id)
        return self._fetch_reviews(parent_id)

    def fetch_versions_page(
        self,
        page_number: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
    ) -> list[dict[str, Any]]:
        """Fetch a page of version rows for the table.

        Args:
            page_number: Zero-based page index (used to determine
                whether to reset the cursor).
            page_size: Number of rows per page.
            sort_key: Column key to sort by, or ``None``.
            descending: Whether to sort in descending order.

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
        edges, page_info = self._get_versions_page(
            self._current_project,
            self._selected_folder_id,
            page_size,
            self._graphql_after,
        )
        self.log.debug(
            "Received %d edges, page info: %s", len(edges), page_info
        )
        page = [self._transform_version_edge(e) for e in edges]
        self._graphql_has_next_page = page_info["hasNextPage"]
        self._graphql_after = page_info["endCursor"]
        return page

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

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _fetch_reviews(self, parent_id: str | None) -> list[TreeNode]:
        """Return tree nodes for review sessions.

        Args:
            parent_id: Parent entity ID. Only root (``None``) returns
                review session nodes; children are always empty.

        Returns:
            List of :class:`TreeNode` instances.
        """
        self.log.debug("Fetching review children for %s", parent_id)
        if self._review_data is None:
            self._get_reviews()
        if parent_id is None:
            nodes = []
            for r in self._review_data:
                if r.get("entityListType") != "review-session":
                    continue
                nodes.append(
                    TreeNode(
                        id=r.get("id", "no id"),
                        label=r.get("label", "no label"),
                        has_children=False,
                        icon="subscriptions",
                        data=r,
                    )
                )
            self._review_data = nodes
            return nodes
        return []

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
        type_icons = self._folder_type_icons
        return [
            TreeNode(
                id=f["id"],
                label=f.get("label") or f["name"],
                has_children=f.get("hasChildren", False),
                icon=type_icons.get(f.get("folderType", ""), "folder"),
                data=f,
            )
            for f in folders
        ]

    def _get_reviews(self) -> None:
        """Refresh review data from the server."""
        project = self._current_project
        self.log.info("Getting reviews for project %s", project)
        self._review_data = ayon_api.get_entity_lists(project_name=project)
        self.log.debug("Review data generator ready for project %s", project)

    def _build_project_info(self, project_name: str | None = None) -> None:
        """Populate project info and folder type icon mapping.

        Sets :attr:`_project_info` and :attr:`_folder_type_icons`
        in place.

        Args:
            project_name: Override for the project to query. Defaults
                to :attr:`_current_project`.
        """
        name = project_name or self._current_project
        if not name:
            return
        project_entity = ayon_api.get_project(name)
        # print(f"Project entity: {json.dumps(project_entity, indent=4)}")
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
        self._folder_type_icons = {
            ft["name"]: ft["icon"]
            for ft in project_entity.get("folderTypes", [])
        }

    def _pinfo(self, category: str, name: str, key: str, default=None) -> Any:
        """Get a project info value by category and key.

        Args:
            category: One of "folderTypes", "taskTypes", "linkTypes",
                "statuses", or "tags".
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
        after: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch a single page of versions via GraphQL.

        Args:
            project_name: AYON project name.
            folder_id: Filter by folder ID, or ``None`` for all.
            page_size: Maximum number of edges to return.
            after: GraphQL cursor for pagination.

        Returns:
            Tuple of (edges list, pageInfo dict).

        Raises:
            RuntimeError: If there is no server connection or the
                query returns errors.
        """
        con = ayon_api.get_server_api_connection()
        if not con:
            raise RuntimeError("No server connection")
        variables: dict[str, Any] = {
            "projectName": project_name,
            "versionFilter": "",
            "productFilter": "",
            "taskFilter": "",
            "sortBy": "path",
            "first": page_size,
            "folderIds": [folder_id] if folder_id else None,
            "after": after,
        }
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
        product_attrib = json.loads(
            n.get("product", {}).get("allAttrib", "{}")
        )
        product_folder_attrib = json.loads(
            n.get("product", {}).get("folder", {}).get("allAttrib", "{}")
        )
        status = n.get("status", "")
        by_name = self._project_info.get("by_name", {})
        return {
            "thumbnail": "",
            "product/version": (
                f"{n.get('product', {}).get('name', '')} - {n.get('name', '')}"
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
