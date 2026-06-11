"""Data models for AYON Views.

A *View* is a server-stored, shareable preset that captures everything
the user tweaked in the browser UI (columns, sort, filter, grouping…)
and can be re-applied with a single click.

These dataclasses are purely descriptive: they round-trip to/from the
server payload format (``from_payload`` / ``to_payload``) and know
nothing about Qt models or widgets.  The widget bindings live in
:mod:`ayon_core.ui.components.views.view_bindings`.

Round-trip is **lossless**: any keys that the current ``ayon-core``
version does not understand are preserved verbatim in
:attr:`ViewSettings.extra` (settings-level) or :attr:`View.access`
(view-level), so two app versions can share Views safely.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

log = logging.getLogger(__name__)


# Settings keys that are first-class fields on ViewSettings.
# Any other key found in the payload's "settings" dict is round-tripped
# inside ``ViewSettings.extra`` so newer app versions can still emit
# settings unknown to this codebase without losing them.
_KNOWN_SETTINGS_KEYS: frozenset[str] = frozenset(
    {
        "columns",
        "sortBy",
        "sortDesc",
        "rowHeight",
        "filter",
        "groupBy",
        "groupSortByDesc",
        "showEmptyGroups",
    }
)

# View-level (top-level payload) keys that are first-class fields on View.
_KNOWN_VIEW_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "label",
        "viewType",
        "settings",
        "owner",
        "scope",
        "visibility",
        "working",
        "position",
        "accessLevel",
        "access",
    }
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Visibility(str, Enum):
    """Whether a view is owner-only or shared with others.

    Subclasses ``str`` so it serialises naturally to JSON.
    """

    PRIVATE = "private"
    SHARED = "shared"

    @classmethod
    def _missing_(cls, value: Any) -> "Visibility":
        """Fall back to ``PRIVATE`` when the payload uses an unknown value.

        Args:
            value: Raw value found in the payload.

        Returns:
            The matching enum member, or ``PRIVATE`` if unknown.
        """
        log.debug("Unknown Visibility value %r, defaulting to PRIVATE", value)
        return cls.PRIVATE


class Scope(str, Enum):
    """The level at which a view is stored on the server."""

    PROJECT = "project"
    STUDIO = "studio"

    @classmethod
    def _missing_(cls, value: Any) -> "Scope":
        """Fall back to ``PROJECT`` for unknown values.

        Args:
            value: Raw value found in the payload.

        Returns:
            The matching enum member, or ``PROJECT`` if unknown.
        """
        log.debug("Unknown Scope value %r, defaulting to PROJECT", value)
        return cls.PROJECT


# ---------------------------------------------------------------------------
# Settings sub-dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ColumnState:
    """State of a single column inside a View.

    Attributes:
        name: Column key, matches :attr:`TableColumn.key`.
        visible: Whether the column is currently shown.
        pinned: Whether the column is pinned to the left (Phase 3 polish;
            stored but not visually frozen in Phase 1).
        width: Pixel width override, or ``None`` to use the column's
            default / auto width.  Note that
            :class:`~ayon_core.ui.components.table_model.TableColumn`
            uses ``0`` to mean *auto*; the mapping is handled by
            ``PaginatedTableModel.apply_settings``.
    """

    name: str
    visible: bool = True
    pinned: bool = False
    width: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ColumnState":
        """Build a ColumnState from a single payload column dict.

        Args:
            payload: Dict like ``{"name": "...", "visible": True, ...}``.

        Returns:
            A new ColumnState instance.
        """
        width = payload.get("width")
        if width is not None:
            try:
                width = int(width)
            except (TypeError, ValueError):
                width = None
        return cls(
            name=str(payload.get("name", "")),
            visible=bool(payload.get("visible", True)),
            pinned=bool(payload.get("pinned", False)),
            width=width,
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialise this column state to the payload format.

        Returns:
            A new dict with payload-friendly keys.
        """
        out: dict[str, Any] = {
            "name": self.name,
            "visible": self.visible,
            "pinned": self.pinned,
        }
        if self.width is not None:
            out["width"] = self.width
        return out


@dataclass
class FilterDef:
    """Server-side filter configuration captured in a View.

    The condition dicts are opaque to ``ayon-core``: they are passed
    through to the filter proxy untouched.  The proxy converts them
    to :class:`FilterCriterion` via
    :meth:`FilterCriterion.from_def` / :meth:`to_def`.

    Attributes:
        conditions: List of condition dicts.  Each dict has at least a
            ``key`` and ``values`` field.
        operator: How conditions combine — ``"and"`` or ``"or"``.
    """

    conditions: list[dict[str, Any]] = field(default_factory=list)
    operator: str = "and"

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "FilterDef":
        """Build a FilterDef from the payload's ``filter`` dict.

        Args:
            payload: Filter sub-dict, or ``None`` for an empty filter.

        Returns:
            A new FilterDef.
        """
        if not payload:
            return cls()
        raw_conds = payload.get("conditions") or []
        operator = str(payload.get("operator", "and")).lower()
        if operator not in ("and", "or"):
            operator = "and"
        return cls(
            conditions=[
                copy.deepcopy(c) for c in raw_conds if isinstance(c, dict)
            ],
            operator=operator,
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialise this filter to a payload dict.

        Returns:
            A dict with ``conditions`` and ``operator`` keys.
        """
        return {
            "conditions": [copy.deepcopy(c) for c in self.conditions],
            "operator": self.operator,
        }

    def is_empty(self) -> bool:
        """Return True when there are no filter conditions.

        Returns:
            True when there are no conditions configured.
        """
        return not self.conditions


@dataclass
class GroupingDef:
    """Grouping configuration captured in a View.

    Attributes:
        group_by: Column key to group rows by, or ``None`` for no
            grouping.
        group_sort_desc: Whether the group ordering is descending.
        show_empty_groups: Whether groups with no visible rows are
            rendered or hidden.
    """

    group_by: str | None = None
    group_sort_desc: bool = False
    show_empty_groups: bool = False

    def is_empty(self) -> bool:
        """Return True when no grouping is configured.

        Returns:
            True when ``group_by`` is ``None``.
        """
        return self.group_by is None


# ---------------------------------------------------------------------------
# ViewSettings
# ---------------------------------------------------------------------------


@dataclass
class ViewSettings:
    """The actual user-visible configuration of a View.

    All "generic" knobs (columns, sort, row height, filter, grouping)
    are first-class fields.  Anything else (``showProducts``,
    ``gridHeight``, ``featuredVersionOrder``, ``slicerType``, …) is
    stashed verbatim in :attr:`extra` so the payload roundtrips
    losslessly across app versions.

    Attributes:
        columns: Ordered list of column states.
        sort_by: Column key to sort by, or ``None`` for no sort.
        sort_desc: Whether the sort is descending.
        row_height: Row height in pixels (also used to map to card size
            in card views).
        grouping: Grouping configuration.
        filter: Filter configuration.
        extra: All other settings keys, preserved untouched.
    """

    columns: list[ColumnState] = field(default_factory=list)
    sort_by: str | None = None
    sort_desc: bool = False
    row_height: int = 32
    grouping: GroupingDef = field(default_factory=GroupingDef)
    filter: FilterDef = field(default_factory=FilterDef)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ViewSettings":
        """Build ViewSettings from the payload's ``settings`` sub-dict.

        Unknown keys are preserved verbatim in :attr:`extra`.

        Args:
            payload: Settings sub-dict, or ``None`` for defaults.

        Returns:
            A new ViewSettings instance.
        """
        if not payload:
            return cls()

        raw_cols = payload.get("columns") or []
        columns = [
            ColumnState.from_payload(c)
            for c in raw_cols
            if isinstance(c, dict)
        ]

        sort_by = payload.get("sortBy")
        if sort_by is not None:
            sort_by = str(sort_by) or None

        row_height_raw = payload.get("rowHeight", 32)
        try:
            row_height = int(row_height_raw)
        except (TypeError, ValueError):
            row_height = 32

        grouping = GroupingDef(
            group_by=(
                str(payload["groupBy"]) if payload.get("groupBy") else None
            ),
            group_sort_desc=bool(payload.get("groupSortByDesc", False)),
            show_empty_groups=bool(payload.get("showEmptyGroups", False)),
        )

        filter_def = FilterDef.from_payload(payload.get("filter"))

        extra = {
            k: v for k, v in payload.items() if k not in _KNOWN_SETTINGS_KEYS
        }

        return cls(
            columns=columns,
            sort_by=sort_by,
            sort_desc=bool(payload.get("sortDesc", False)),
            row_height=row_height,
            grouping=grouping,
            filter=filter_def,
            extra=extra,
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialise these settings to a payload dict.

        Unknown keys from :attr:`extra` are merged back in.  Known keys
        in ``extra`` are ignored (first-class fields win) so accidental
        duplication can't corrupt a roundtrip.

        Returns:
            A dict suitable for embedding under ``"settings"`` in a
            View payload.
        """
        out: dict[str, Any] = {
            "columns": [c.to_payload() for c in self.columns],
            "sortDesc": self.sort_desc,
            "rowHeight": self.row_height,
            "groupSortByDesc": self.grouping.group_sort_desc,
            "showEmptyGroups": self.grouping.show_empty_groups,
            "filter": self.filter.to_payload(),
        }
        if self.sort_by is not None:
            out["sortBy"] = self.sort_by
        if self.grouping.group_by is not None:
            out["groupBy"] = self.grouping.group_by

        # Merge extras last but never let them override first-class keys.
        for k, v in self.extra.items():
            if k not in _KNOWN_SETTINGS_KEYS:
                out[k] = v
        return out


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


# Default access level used when a payload does not specify one.
# Scale is 0-50 step 10 — see plan documentation for semantics.
DEFAULT_ACCESS_LEVEL: int = 30


@dataclass
class View:
    """A saved configuration that can be applied to a table/card view.

    Attributes:
        id: Server-assigned identifier.  Empty string for views that
            have not been persisted yet.
        label: Human-readable name shown in the view selector.
        view_type: Identifier of the page/context the view belongs to
            (e.g. ``"versions"``, ``"review_sessions"``).
        settings: The actual UI configuration.
        owner: User name / id of the creator.
        scope: ``"project"`` or ``"studio"``.
        visibility: :class:`Visibility` enum.
        working: True for the per-user fallback view that captures
            ad-hoc tweaks.  At most one working view per (user,
            view_type) should be flagged.
        position: Sort order hint within the selector.
        access_level: Required access level (0–50, step 10) for editing
            shared views.  Components store the value and gate UI via
            :meth:`can_edit`.
        access: Free-form per-user/per-group access dict, preserved
            verbatim for the consumer to interpret.
    """

    id: str = ""
    label: str = ""
    view_type: str = ""
    settings: ViewSettings = field(default_factory=ViewSettings)
    owner: str = ""
    scope: Scope = Scope.PROJECT
    visibility: Visibility = Visibility.PRIVATE
    working: bool = False
    position: int = 0
    access_level: int = DEFAULT_ACCESS_LEVEL
    access: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "View":
        """Build a View from a raw server payload.

        Unknown top-level keys are preserved in :attr:`extra`.

        Args:
            payload: Raw server payload dict.

        Returns:
            A new View instance.
        """
        if not isinstance(payload, dict):
            raise TypeError(
                f"View payload must be a dict, got {type(payload).__name__}"
            )

        access_level_raw = payload.get("accessLevel", DEFAULT_ACCESS_LEVEL)
        try:
            access_level = int(access_level_raw)
        except (TypeError, ValueError):
            access_level = DEFAULT_ACCESS_LEVEL

        position_raw = payload.get("position", 0)
        try:
            position = int(position_raw)
        except (TypeError, ValueError):
            position = 0

        extra = {k: v for k, v in payload.items() if k not in _KNOWN_VIEW_KEYS}

        return cls(
            id=str(payload.get("id", "")),
            label=str(payload.get("label", "")),
            view_type=str(payload.get("viewType", "")),
            settings=ViewSettings.from_payload(payload.get("settings")),
            owner=str(payload.get("owner", "")),
            scope=Scope(payload.get("scope", Scope.PROJECT.value)),
            visibility=Visibility(
                payload.get("visibility", Visibility.PRIVATE.value)
            ),
            working=bool(payload.get("working", False)),
            position=position,
            access_level=access_level,
            access=dict(payload.get("access") or {}),
            extra=extra,
        )

    def to_payload(self) -> dict[str, Any]:
        """Serialise this view to a payload dict.

        Returns:
            A dict suitable for sending to the server.
        """
        out: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "viewType": self.view_type,
            "settings": self.settings.to_payload(),
            "owner": self.owner,
            "scope": self.scope.value,
            "visibility": self.visibility.value,
            "working": self.working,
            "position": self.position,
            "accessLevel": self.access_level,
            "access": dict(self.access),
        }
        for k, v in self.extra.items():
            if k not in _KNOWN_VIEW_KEYS:
                out[k] = v
        return out

    def can_edit(self, current_user: str, user_access_level: int = 50) -> bool:
        """Return True when *current_user* may edit this view.

        Args:
            current_user: The viewer's user name / id.
            user_access_level: The viewer's effective access level on
                the relevant scope (0–50).  Defaults to ``50`` (full
                access) so callers that don't know the user's level
                don't unexpectedly read-lock the editor.

        Returns:
            True when:

            - The view is private and the viewer owns it.
            - Or the view is shared and the viewer's access level is
              greater or equal to the view's required level.
        """
        if self.visibility == Visibility.PRIVATE:
            return bool(current_user) and current_user == self.owner
        return user_access_level >= self.access_level
