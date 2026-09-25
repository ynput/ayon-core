"""AYON Views subpackage.

Saved configurations (columns, sort, filter, grouping…) that can be
applied to a :class:`PaginatedTableModel` + :class:`AYTableView` /
:class:`AYCardView` setup.

Phase 1 ships the data model and storage backend.  Phase 2 adds the
:class:`ViewBindings` adapter and the :class:`AYViewSelector` /
:class:`AYViewEditor` widgets.
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
from .view_bindings import ViewBindings
from .view_editor import AYViewEditor
from .server_view_manager import ServerViewManager
from .view_manager import InMemoryViewManager, ViewManager
from .view_selector import AYViewSelector

__all__ = (
    "AYViewEditor",
    "AYViewSelector",
    "ColumnState",
    "DEFAULT_ACCESS_LEVEL",
    "FilterDef",
    "GroupingDef",
    "InMemoryViewManager",
    "Scope",
    "ServerViewManager",
    "View",
    "ViewBindings",
    "ViewManager",
    "ViewSettings",
    "Visibility",
)
