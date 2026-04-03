from __future__ import annotations

import datetime
import json
from typing import Any

import ayon_api
from ayon_api.graphql_queries import projects_graphql_query
from ayon_ui_qt.components.tree_model import TreeNode
from qtpy import QtCore

from ayon_core.lib import Logger
from ayon_core.tools.utils.user_prefs import UserPreferences

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

    project_changed = QtCore.Signal(str)  # type: ignore
    project_info_changed = QtCore.Signal()  # type: ignore
    category_changed = QtCore.Signal(str)  # type: ignore
    tree_reset_requested = QtCore.Signal()  # type: ignore
    selection_changed = QtCore.Signal(str, str)  # type: ignore

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._current_project: str = ""
        self._current_category: str = "Hierarchy"
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

        if self._current_category == "Reviews" and id:
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
        if self._current_category == "Hierarchy":
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

        # Tree root: return folder rows so the model has expandable nodes.
        if (
            parent_id is None
            and self._tree_mode
            and self._current_category == "Hierarchy"
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
        if self._current_category == "Reviews":
            folder_id = None
            version_ids = self._review_session_version_ids  # None = no filter
            if version_ids is None:
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
        return {
            "id": folder.get("id", ""),
            "has_children": True,
            "product/version": label,
            "product/version__icon": icon,
            "folderName": label,
            "entityType": "Folder",
            "entityType__icon": "folder",
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
            project_name=self._current_project, list_ids=[session_id]
        )
        items = next(versions_gen).get("items", []) if versions_gen else []
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
            "versionFilter": "",
            "productFilter": "",
            "taskFilter": "",
            "sortBy": sort_by,
            "folderIds": resolved_folder_ids,
            "includeFolderChildren": include_folder_children,
            "versionIds": version_ids if version_ids else None,
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
