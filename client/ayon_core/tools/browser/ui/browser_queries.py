"""GraphQL query strings and column-sort mapping for the review widget."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from ayon_core.tools.browser.server_capabilities import (
    get_server_products_sort_options,
    get_server_versions_sort_options,
    server_supports_representation_filter,
)


GET_VERSIONS_QUERY = """
query GetVersions(
  $projectName: String!,
  $productIds: [String!],
  $versionIds: [String!],
  $versionFilter: String,
  $productFilter: String,
  $taskFilter: String,
  $folderFilter: String,
  __REPRESENTATION_FILTER_VARIABLE__
  $featuredOnly: [String!],
  $latestPerFolder: Boolean,
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
      folderFilter: $folderFilter
      __REPRESENTATION_FILTER_ARGUMENT__
      featuredOnly: $featuredOnly
      latestPerFolder: $latestPerFolder
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
          __VERSION_FIELDS__
          task {
            __TASK_FIELDS__
          }
          product {
            __PRODUCT_FIELDS__
            folder {
              __FOLDER_FIELDS__
            }
          }
        }
      }
    }
  }
}
"""

GET_VERSION_GROUP_COUNTS_QUERY = """
query GetVersionGroupCounts(
  $projectName: String!,
  $versionFilter: String,
  $productFilter: String,
  $taskFilter: String,
  $folderFilter: String,
  __REPRESENTATION_FILTER_VARIABLE__
  $folderIds: [String!],
  $versionIds: [String!],
  $includeFolderChildren: Boolean,
  $featuredOnly: [String!],
  $latestPerFolder: Boolean,
  $hasReviewables: Boolean,
  $search: String,
  $targets: [MetricTargetInput!]
) {
  project(name: $projectName) {
    versions(
      calculateSpecificStatistics: $targets
      ids: $versionIds
      filter: $versionFilter
      productFilter: $productFilter
      taskFilter: $taskFilter
      folderFilter: $folderFilter
      __REPRESENTATION_FILTER_ARGUMENT__
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      featuredOnly: $featuredOnly
      latestPerFolder: $latestPerFolder
      hasReviewables: $hasReviewables
      search: $search
    ) {
      fieldStats {
        columnName
        valueFilledCount
        valueNotFilledCount
        distribution
      }
    }
  }
}
"""


def _resolve_representation_filter(query: str) -> str:
    """Add or strip the ``representationFilter`` query argument.

    Servers up to 1.16.6 reject the argument outright, even when its
    value is empty, so it is only part of the query on servers whose
    versions resolver has it. A ``representationFilter`` variable sent
    along with a query that does not declare it is ignored.

    Args:
        query: Query template containing the representation markers.

    Returns:
        The query with the markers resolved.
    """
    if server_supports_representation_filter():
        variable = "  $representationFilter: String,\n"
        argument = "      representationFilter: $representationFilter\n"
    else:
        variable = argument = ""
    query = query.replace(
        "  __REPRESENTATION_FILTER_VARIABLE__\n", variable
    )
    return query.replace(
        "      __REPRESENTATION_FILTER_ARGUMENT__\n", argument
    )


def get_version_group_counts_query() -> str:
    """Build the version group counts query."""
    return _resolve_representation_filter(GET_VERSION_GROUP_COUNTS_QUERY)


def get_versions_query(column_keys: set[str] | None = None) -> str:
    """Build the version query selection for the requested columns."""
    keys = column_keys or set()
    version_fields = ["name", "id", "version", "heroVersionId"]
    task_fields = ["id", "name"]
    product_fields = ["id", "name"]
    folder_fields = ["id", "name"]

    if "thumb" in keys:
        version_fields.append("thumbnailId")
    if "status" in keys:
        version_fields.append("status")
    if "author" in keys:
        version_fields.append("author")
    if "createdAt" in keys:
        version_fields.append("createdAt")
    if "updatedAt" in keys:
        version_fields.append("updatedAt")
    if "tags" in keys:
        version_fields.append("tags")
    if "featuredVersionType" in keys:
        version_fields.append("featuredVersionType")
    if "productType" in keys:
        product_fields.append("productType")
    if "productBaseType" in keys:
        product_fields.append("productBaseType")
    if "productStatus" in keys:
        product_fields.append("status")
    if keys.intersection({"task", "taskType"}):
        # The Task column paints a task-type colored icon, so the type is
        # needed even when the Task Type column itself is hidden.
        task_fields.append("taskType")
    if "taskStatus" in keys:
        task_fields.append("status")
    if "taskTags" in keys:
        task_fields.append("tags")
    if "folderName" in keys:
        # the Folder Name column paints a folder-type colored icon next to the
        # label.
        folder_fields.extend(("label", "folderType"))
    if "folderStatus" in keys:
        folder_fields.append("status")

    if keys.intersection({"product/version", "path"}):
        version_fields.append("path")

    # The complete JSON blob is returned for entities with custom filters or
    # attribute-backed columns.  Keep this scoped: a product attribute must
    # not accidentally cause the version blob to be selected.
    scopes = {
        "version": version_fields,
        "product": product_fields,
        "task": task_fields,
        "folder": folder_fields,
    }
    for key in keys:
        if not key.startswith("attr:"):
            continue
        try:
            _, scope, _ = key.split(":", 2)
        except ValueError:
            continue
        fields = scopes.get(scope)
        if fields is not None and "allAttrib" not in fields:
            fields.append("allAttrib")

    if keys.intersection({
        "fps", "frameStart", "frameEnd", "handleStart", "handleEnd",
        "step", "machine", "source", "comment",
    }) and "allAttrib" not in version_fields:
        version_fields.append("allAttrib")
    if "step" in keys:
        version_fields.append("data")
    if keys.intersection({
        "width", "height", "pixelAspect", "clipIn", "clipOut",
        "frameStart", "frameEnd",
    }) and "allAttrib" not in folder_fields:
        folder_fields.append("allAttrib")

    replacements = {
        "__VERSION_FIELDS__": "\n".join(
            f"          {field}" for field in version_fields
        ),
        "__TASK_FIELDS__": "\n".join(
            f"            {field}" for field in task_fields
        ),
        "__PRODUCT_FIELDS__": "\n".join(
            f"            {field}" for field in product_fields
        ),
        "__FOLDER_FIELDS__": "\n".join(
            f"              {field}" for field in folder_fields
        ),
    }
    query = GET_VERSIONS_QUERY
    for marker, value in replacements.items():
        query = query.replace(marker, value)
    return _resolve_representation_filter(query)


GET_PRODUCTS_QUERY = """
query GetProducts(
  $projectName: String!,
  $folderIds: [String!],
  $productFilter: String,
  $versionFilter: String,
  $taskFilter: String,
  $folderFilter: String,
  $search: String,
  $includeFolderChildren: Boolean,
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
      versionFilter: $versionFilter,
      taskFilter: $taskFilter,
      folderFilter: $folderFilter,
      search: $search,
      includeFolderChildren: $includeFolderChildren,
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
          productBaseType
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
        }
        cursor
      }
    }
  }
}
"""

#: Maps table column keys to valid GraphQL ``sortBy`` values accepted by
#: the AYON versions resolver.  The combined Product/Version column maps to
#: the version path, matching the frontend's ``name -> path`` sort mapping.
#: Columns that cannot be sorted server-side are intentionally absent.
COLUMN_TO_SORT_BY: dict[str, str] = {
    "product/version": "path",
    "version": "version",
    "status": "status",
    "createdAt": "createdAt",
    "updatedAt": "updatedAt",
    "fps": "attrib.fps",
    "frameStart": "attrib.frameStart",
    "frameEnd": "attrib.frameEnd",
    "handleStart": "attrib.handleStart",
    "handleEnd": "attrib.handleEnd",
    "step": "attrib.step",
    "machine": "attrib.machine",
    "source": "attrib.source",
    "comment": "attrib.comment",
}

#: Maps table column keys to ``sortBy`` values that only newer servers
#: accept (the server rejects unknown values), matching the frontend's
#: mapping. They are used only when the server lists them, see
#: :func:`get_sort_by`.
OPTIONAL_COLUMN_TO_SORT_BY: dict[str, str] = {
    "author": "author",
    "tags": "tags",
    "productName": "productName",
    "productType": "productType",
    "productBaseType": "productBaseType",
    "folderName": "folderName",
    "task": "taskName",
    "taskType": "taskType",
}

#: Prefix of version attribute column keys (``attr:version:<name>``).
_VERSION_ATTRIBUTE_COLUMN_PREFIX = "attr:version:"


def get_sort_by(
    sort_key: str | None,
    server_sort_options: frozenset[str] | None = None,
) -> str | None:
    """Return the GraphQL ``sortBy`` value for a table column.

    A sortable column without a ``sortBy`` value is listed in the
    server's default order (creation order), which is not the order
    the header claims. This shows the most when rows of several folders
    are listed together, e.g. sorting by Folder or Product.

    Args:
        sort_key: Key of the sorted table column, or ``None``.
        server_sort_options: ``sortBy`` values the server lists. Queried
            from the server when not passed.

    Returns:
        The ``sortBy`` value, or ``None`` when the column cannot be
        sorted server-side.
    """
    if not sort_key:
        return None
    sort_by = COLUMN_TO_SORT_BY.get(sort_key)
    if sort_by is not None:
        return sort_by
    if sort_key.startswith(_VERSION_ATTRIBUTE_COLUMN_PREFIX):
        attr_name = sort_key[len(_VERSION_ATTRIBUTE_COLUMN_PREFIX):]
        return f"attrib.{attr_name}" if attr_name else None
    sort_by = OPTIONAL_COLUMN_TO_SORT_BY.get(sort_key)
    if sort_by is None:
        return None
    if server_sort_options is None:
        server_sort_options = get_server_versions_sort_options()
    if sort_by in server_sort_options:
        return sort_by
    return None


#: Version ``sortBy`` values that the products resolver names
#: differently.
VERSION_TO_PRODUCT_SORT_BY: dict[str, str] = {
    "productName": "name",
}


def get_product_sort_by(
    version_sort_by: str | None,
    server_sort_options: frozenset[str] | None = None,
) -> str | None:
    """Return the products ``sortBy`` value for a versions ``sortBy``.

    Product rows (e.g. the Group By Product headers) are sorted by the
    same column as the versions, like the frontend's Products page does.
    Only values the server lists are returned - it rejects unknown ones
    and some version sorts (e.g. ``author``) have no product equivalent.

    Args:
        version_sort_by: ``sortBy`` value used for the versions.
        server_sort_options: ``sortBy`` values the products resolver
            lists. Queried from the server when not passed.

    Returns:
        The products ``sortBy`` value, or ``None`` when products cannot
        be sorted by it.
    """
    if not version_sort_by:
        return None
    sort_by = VERSION_TO_PRODUCT_SORT_BY.get(
        version_sort_by, version_sort_by
    )
    if sort_by.startswith("attrib."):
        return sort_by
    if server_sort_options is None:
        server_sort_options = get_server_products_sort_options()
    if sort_by in server_sort_options:
        return sort_by
    return None


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
        "productStatus": "",
        "folderStatus": "",
        "taskStatus": "",
        "productType": "",
        "author": "",
        "version": "",
        "productName": "",
        "taskType": "",
        "task": "",
        "taskTags": "",
        "tags": "",
        "createdAt": "",
        "updatedAt": "",
    }
)
