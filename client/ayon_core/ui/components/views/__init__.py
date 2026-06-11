"""AYON Views subpackage.

Saved configurations (columns, sort, filter, grouping…) that can be
applied to a :class:`PaginatedTableModel` + :class:`AYTableView` /
:class:`AYCardView` setup.

Phase 1 ships the data model and storage backend only.  The
:class:`AYViewSelector` / :class:`AYViewEditor` widgets are added in
Phase 2.
"""

from __future__ import annotations

from .data_models import (
    DEFAULT_ACCESS_LEVEL,
    ColumnState,
    FilterDef,
    GroupingDef,
    Scope,
    View,
    ViewSettings,
    Visibility,
)
from .view_manager import InMemoryViewManager, ViewManager

__all__ = (
    "ColumnState",
    "DEFAULT_ACCESS_LEVEL",
    "FilterDef",
    "GroupingDef",
    "InMemoryViewManager",
    "Scope",
    "View",
    "ViewManager",
    "ViewSettings",
    "Visibility",
)
