"""Visibility-aware paginated table model for the reviews panel."""

from __future__ import annotations

from ayon_ui_qt.components.table_model import PaginatedTableModel
from ayon_ui_qt.components.table_view import AYTableView
from qtpy import QtCore

from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


class VisibilityAwarePaginatedTableModel(PaginatedTableModel):
    """Paginated table model that deprioritises off-screen page fetches.

    Overrides :meth:`_get_fetch_priority` so that page-fetch tasks for a
    parent node that is **not** currently visible in the table viewport
    are enqueued at priority **20** (background prefetch) instead of the
    default 0 (Critical) or 1 (High).  This keeps the task queue
    responsive for visible rows and thumbnail fetches (priority 2) when
    many nodes are expanded simultaneously.

    Priority scale:

    - ``0``  – Visible first-page fetches
    - ``1``  – Visible subsequent-page fetches
    - ``2``  – Thumbnail fetches
    - ``20`` – Off-screen page fetches

    Call :meth:`set_view` after construction to attach the view whose
    viewport is used for visibility checks.
    """

    _OFF_SCREEN_PRIORITY: int = 20

    def __init__(self, *args, **kwargs) -> None:
        self._view: AYTableView | None = None
        self._priority_cache: dict[tuple[int, int], int] = {}
        self._priority_cache_clear_scheduled: bool = False
        super().__init__(*args, **kwargs)

    def set_view(self, view: AYTableView) -> None:
        """Attach the view used for visibility checks.

        Args:
            view: The :class:`AYTableView` that displays this model.
        """
        self._view = view

    @property
    def request_id(self) -> str:
        """Return the current request context ID.

        Exposes the base-class ``_request_id`` as a public read-only
        property so external thumbnail fetchers can scope their
        :class:`AsyncTask` entries correctly.  The ID is regenerated on
        every :meth:`reset_data` call.

        Returns:
            UUID string identifying the current fetch context.
        """
        return self._request_id

    def _is_parent_visible(self, node: object) -> bool:
        """Return True when *node*'s row is within the viewport.

        Fails open (returns ``True``) in all ambiguous situations so
        that a fetch is never permanently starved.

        Args:
            node: A ``_TableNode`` instance from the base model.

        Returns:
            ``True`` if the parent row is visible or the check cannot
            be performed conclusively; ``False`` only when a valid
            visual rect lies entirely outside the viewport.
        """
        if getattr(node, "is_root", True) or self._view is None:
            return True

        src_idx = self._index_for_node(node)  # type: ignore[attr-defined]
        if not src_idx.isValid():
            return True

        proxy_model = self._view.model()
        if proxy_model is None:
            return True

        if isinstance(proxy_model, QtCore.QAbstractProxyModel):
            proxy_idx = proxy_model.mapFromSource(src_idx)
        else:
            proxy_idx = src_idx

        if not proxy_idx.isValid():
            return False

        vp_rect = self._view.viewport().rect()
        visual = self._view.visualRect(proxy_idx)
        return vp_rect.intersects(visual)

    def _get_fetch_priority(self, node: object, page: int) -> int:
        """Return fetch priority for the given *node* and *page*.

        Results are cached per event-loop tick to avoid redundant
        ``visualRect()`` calls for the same ``(node, page)`` pair.

        Args:
            node: The parent ``_TableNode`` whose children are fetched.
            page: Zero-based page number being requested.

        Returns:
            ``20`` when the parent row is off-screen; ``0`` for the
            first page of a visible parent; ``1`` for subsequent pages.
        """
        cache_key = (id(node), page)
        if cache_key in self._priority_cache:
            return self._priority_cache[cache_key]

        parent_is_visible = self._is_parent_visible(node)
        priority = (
            self._OFF_SCREEN_PRIORITY
            if not parent_is_visible
            else (0 if page == 0 else 1)
        )
        self._priority_cache[cache_key] = priority

        if not self._priority_cache_clear_scheduled:
            self._priority_cache_clear_scheduled = True
            QtCore.QTimer.singleShot(0, self._clear_priority_cache)

        return priority

    def _clear_priority_cache(self) -> None:
        """Clear the per-tick priority cache.

        Scheduled via ``QTimer.singleShot(0)`` after the first cache
        write so it fires at the next event-loop iteration.
        """
        self._priority_cache.clear()
        self._priority_cache_clear_scheduled = False
