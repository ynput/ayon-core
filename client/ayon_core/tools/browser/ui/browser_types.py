"""Type definitions and enums for the review widget."""

from __future__ import annotations

from enum import Enum


class BrowserSlicerCategory(Enum):
    """Categories for organizing versions in the review widget."""

    HIERARCHY = "Hierarchy"
    REVIEWS = "Reviews"
    LISTS = "Lists"


#: Slicer categories whose tree holds entity lists instead of folders.
ENTITY_LIST_CATEGORIES = frozenset({
    BrowserSlicerCategory.REVIEWS.value,
    BrowserSlicerCategory.LISTS.value,
})

#: Slicer categories that can narrow the versions by folders, for which
#: including the versions of their child folders applies.
FOLDER_SLICER_CATEGORIES = frozenset({
    BrowserSlicerCategory.HIERARCHY.value,
    BrowserSlicerCategory.LISTS.value,
})
