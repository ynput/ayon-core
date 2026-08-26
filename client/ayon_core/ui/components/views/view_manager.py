"""ViewManager interface and in-memory implementation.

The :class:`ViewManager` is intentionally **sync** — consumers using
``ayon_api`` are expected to wrap network calls themselves (e.g. via
:class:`ayon_core.ui.components.task_queue.AsyncTaskQueue`).  Keeping
the manager sync simplifies the widget code: it can list/save/delete
views without juggling futures or signals for every call.

The :class:`InMemoryViewManager` is the lightweight implementation
used by the tester / demos / unit tests.  Real consumer apps subclass
:class:`ViewManager` directly.
"""

from __future__ import annotations

import logging
import uuid
from abc import abstractmethod

from qtpy.QtCore import QObject, Signal  # type: ignore[attr-defined]

from .data_models import View

log = logging.getLogger(__name__)


class ViewManager(QObject):
    """Abstract storage backend for :class:`View` instances.

    Signals:
        views_changed(str): Emitted with ``view_type`` whenever the
            list of views for that type may have changed.
        view_saved(str): Emitted with the view id after a successful
            ``save_view``.
        view_deleted(str): Emitted with the view id after a successful
            ``delete_view``.
        error(str): Emitted with an error message when an operation
            fails (subclasses may emit this instead of raising).
    """

    views_changed = Signal(str)
    view_saved = Signal(str)
    view_deleted = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialise the manager.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)

    # -- abstract API -------------------------------------------------------

    @abstractmethod
    def list_views(self, view_type: str) -> list[View]:
        """Return the list of views for the given view type.

        Args:
            view_type: The view-type identifier (e.g. ``"versions"``).

        Returns:
            List of :class:`View` instances, sorted by
            :attr:`View.position` then :attr:`View.label`.
        """

    @abstractmethod
    def save_view(self, view: View) -> View:
        """Persist a new or updated view.

        Implementations must assign a non-empty :attr:`View.id` when
        creating a new view and return the (possibly modified) view.

        Args:
            view: The view to save.

        Returns:
            The saved view, with its assigned id.
        """

    @abstractmethod
    def delete_view(self, view_id: str) -> None:
        """Delete the view with the given id.

        Args:
            view_id: Identifier of the view to delete.
        """

    # -- optional helpers ---------------------------------------------------

    def get_working_view(self, view_type: str) -> View | None:
        """Return the working view for *view_type*, if any.

        Args:
            view_type: The view-type identifier.

        Returns:
            The view flagged with ``working=True`` for *view_type*, or
            ``None`` when no working view exists.
        """
        for view in self.list_views(view_type):
            if view.working:
                return view
        return None

    def set_working_view(self, view: View) -> None:
        """Mark *view* as the (sole) working view for its view type.

        The default implementation clears the ``working`` flag on every
        other view of the same type and saves them all.  Subclasses can
        override this with a bulk-update endpoint for efficiency.

        Args:
            view: The view to mark as working.
        """
        for other in self.list_views(view.view_type):
            if other.id == view.id:
                continue
            if other.working:
                other.working = False
                self.save_view(other)
        view.working = True
        self.save_view(view)


class InMemoryViewManager(ViewManager):
    """Lightweight in-process implementation used by tests / demos.

    Stores views in a dict keyed by ``view.id``.  Useful when the
    consumer app has not yet wired the real server backend, or when
    running the standalone tester harness.
    """

    def __init__(
        self,
        views: list[View] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Seed the manager with an optional initial set of views.

        Args:
            views: Initial views to register.  Each view must have a
                non-empty :attr:`View.id`; one will be assigned if
                missing.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._views: dict[str, View] = {}
        for view in views or []:
            if not view.id:
                view.id = self._new_id()
            self._views[view.id] = view

    # -- ViewManager API ---------------------------------------------------

    def list_views(self, view_type: str) -> list[View]:
        """Return views matching *view_type*, sorted for display.

        Args:
            view_type: The view-type identifier.

        Returns:
            Sorted list of views.
        """
        matching = [
            v for v in self._views.values() if v.view_type == view_type
        ]
        matching.sort(key=lambda v: (v.position, v.label))
        return matching

    def save_view(self, view: View) -> View:
        """Insert or replace *view* in the in-memory store.

        Args:
            view: The view to save.  An id is assigned if missing.

        Returns:
            The same view instance (with assigned id).
        """
        if not view.id:
            view.id = self._new_id()
        self._views[view.id] = view
        self.view_saved.emit(view.id)
        self.views_changed.emit(view.view_type)
        return view

    def delete_view(self, view_id: str) -> None:
        """Remove *view_id* from the store, if present.

        Args:
            view_id: Identifier of the view to remove.  Missing ids
                are silently ignored after a debug log entry.
        """
        existing = self._views.pop(view_id, None)
        if existing is None:
            log.debug("delete_view: no view with id %r", view_id)
            return
        self.view_deleted.emit(view_id)
        self.views_changed.emit(existing.view_type)

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _new_id() -> str:
        """Return a new unique view identifier.

        Returns:
            A short uuid4 hex string.
        """
        return uuid.uuid4().hex

    def clear(self) -> None:
        """Remove all stored views (intended for tests)."""
        types = {v.view_type for v in self._views.values()}
        self._views.clear()
        for view_type in types:
            self.views_changed.emit(view_type)

    def all_views(self) -> list[View]:
        """Return every stored view across all view types.

        Returns:
            A snapshot list of all stored views.
        """
        return list(self._views.values())
