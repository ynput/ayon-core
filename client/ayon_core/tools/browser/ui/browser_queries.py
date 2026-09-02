"""GraphQL query strings and column-sort mapping for the review widget."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

GET_VERSIONS_QUERY = """
query GetVersions(
  $projectName: String!,
  $productIds: [String!],
  $versionIds: [String!],
  $versionFilter: String,
  $productFilter: String,
  $taskFilter: String,
  $folderFilter: String,
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
  $folderIds: [String!],
  $versionIds: [String!],
  $includeFolderChildren: Boolean,
  $featuredOnly: [String!],
  $latestPerFolder: Boolean,
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
      folderIds: $folderIds
      includeFolderChildren: $includeFolderChildren
      featuredOnly: $featuredOnly
      latestPerFolder: $latestPerFolder
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
    if "taskType" in keys:
        task_fields.append("taskType")
    if "taskStatus" in keys:
        task_fields.append("status")
    if "taskTags" in keys:
        task_fields.append("tags")
    if "folderName" in keys:
        folder_fields.append("label")
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
    return query


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
#: Columns that originate from related entities cannot be sorted
#: server-side and are intentionally absent.
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
