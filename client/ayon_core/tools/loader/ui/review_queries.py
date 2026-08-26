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
