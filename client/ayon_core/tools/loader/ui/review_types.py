"""Type definitions and enums for the review widget."""

from __future__ import annotations

from enum import Enum


class ReviewCategory(Enum):
    """Categories for organizing versions in the review widget."""

    HIERARCHY = "Hierarchy"
    REVIEWS = "Reviews"
