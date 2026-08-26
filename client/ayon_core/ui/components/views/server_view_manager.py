"""Server-backed implementation of :class:`ViewManager`.

Talks to the AYON server's ``/api/views/{view_type}`` endpoints via
:mod:`ayon_api`.  All calls are project-scoped — switch projects with
:meth:`ServerViewManager.set_project`.

The manager keeps a per-view-type list cache and a flat ``id → type``
map.  The id-map is populated on every successful ``list_views``,
``save_view``, and is the source of truth for ``delete_view`` — so
delete works even after the per-type cache is cleared (e.g. after a
project switch).

Cache strategy on mutation:

* ``save_view`` — updates the cache entry **in place** (replace on
  update, append-and-sort on insert) so that the subsequent
  ``views_changed`` emission costs nothing extra.
* ``delete_view`` — removes the entry from the cached list in place.
* ``set_project`` — clears both the per-type cache and the id-map;
  emits ``views_changed`` once per previously-known view type so
  listeners can refresh.

``ayon_api`` exceptions are caught, logged, and surfaced through the
inherited :attr:`error` signal.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlencode

import ayon_api
from qtpy.QtCore import QObject  # type: ignore[attr-defined]

from .data_models import View
from .view_manager import ViewManager

log = logging.getLogger(__name__)


class ServerViewManager(ViewManager):
    """ViewManager backed by AYON server REST endpoints.

    Endpoints (project-scoped, all take ``?project_name=<p>``):

    * ``GET    /api/views/{view_type}``
    * ``POST   /api/views/{view_type}``
    * ``PATCH  /api/views/{view_type}/{view_id}``
    * ``DELETE /api/views/{view_type}/{view_id}``

    Attributes:
        project_name: Name of the project all calls are scoped to.
    """

    def __init__(
        self,
        project_name: str,
        parent: QObject | None = None,
    ) -> None:
        """Initialise the manager.

        Args:
            project_name: Initial project the manager is scoped to.
                May be empty when the loader has no project yet.
            parent: Optional parent QObject.
        """
        super().__init__(parent=parent)
        self._project_name = project_name
        # view_type -> sorted list of views (per-type list cache)
        self._cache: dict[str, list[View]] = {}
        # All view_types ever requested via list_views (retained after
        # cache clear so set_project can emit per-known-type).
        self._known_types: set[str] = set()
        # view_id -> view_type (survives list_views; used by delete_view
        # so it doesn't require a populated per-type cache).
        self._id_to_type: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Project scope
    # ------------------------------------------------------------------

    @property
    def project_name(self) -> str:
        """Current project the manager is scoped to."""
        return self._project_name

    def set_project(self, project_name: str) -> None:
        """Rebind the manager to a different project.

        Clears both caches and emits :attr:`views_changed` for every
        previously-known view type so listeners can refetch.  When no
        types are known yet, emits ``""`` as a sentinel.

        Args:
            project_name: Target project name.  No-op when the same as
                the current project.
        """
        if project_name == self._project_name:
            return
        self._project_name = project_name
        self._id_to_type.clear()
        self._cache.clear()
        if self._known_types:
            for vt in sorted(self._known_types):
                self.views_changed.emit(vt)
        else:
            # No view types have been requested yet; emit the sentinel
            # so consumers that listen for "" can still react.
            self.views_changed.emit("")

    # ------------------------------------------------------------------
    # ViewManager API
    # ------------------------------------------------------------------

    def list_views(self, view_type: str) -> list[View]:
        """Return views for *view_type*, fetching from server on miss.

        Returns an empty list (without emitting :attr:`error`) when the
        project name is empty — callers should wait for
        ``project_changed`` before listing.

        Args:
            view_type: View-type identifier (e.g. ``"versions"``).

        Returns:
            Sorted list of :class:`View` instances.  Empty list on
            network or parse error.
        """
        self._known_types.add(view_type)

        # Skip the network call when no project is set.
        if not self._project_name:
            return []

        if view_type in self._cache:
            return list(self._cache[view_type])

        try:
            resp = ayon_api.get(
                f"views/{view_type}",
                project_name=self._project_name,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to list views for %s", view_type)
            self.error.emit(f"Failed to list views: {exc}")
            return []

        payload = getattr(resp, "data", None)
        if isinstance(payload, dict):
            items = payload.get("views", payload)
        else:
            items = payload
        if not isinstance(items, list):
            items = []

        views: list[View] = []
        for item in items:
            try:
                try:
                    resp = ayon_api.get(
                        f"views/{view_type}/{item.get('id')}",
                        project_name=self._project_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception("Failed to fetch view %s", item.get("id"))
                    self.error.emit(f"Failed to fetch view: {exc}")
                    continue
                full_item = resp.data
                views.append(View.from_payload(full_item))
            except Exception:  # noqa: BLE001
                log.exception("Skipping malformed view payload: %r", item)

        views.sort(key=lambda v: (v.position, v.label.lower()))
        self._cache[view_type] = views
        # Populate id-map for delete_view lookups.
        for v in views:
            if v.id:
                self._id_to_type[v.id] = view_type
        return list(views)

    def save_view(self, view: View) -> View:
        """POST a new view or PATCH an existing one.

        The new-vs-update decision is based solely on whether
        :attr:`View.id` is non-empty.  A view with a non-empty id is
        PATCHed; an empty id results in a POST.  This is correct because
        ids are server-assigned — clients never mint them — so a
        non-empty id means the view was previously persisted.

        The per-type cache is updated in-place (rather than invalidated)
        so the subsequent :attr:`views_changed` emission does not
        trigger an extra round-trip.

        Args:
            view: The view to save.

        Returns:
            The saved view, rebuilt from the server response when
            the response includes data, otherwise the input view.

        Raises:
            Exception: Re-raises any ``ayon_api`` failure after
                emitting :attr:`error`.
        """
        payload = view.to_payload()
        is_update = bool(view.id)

        try:
            if is_update:
                endpoint = self._endpoint(f"views/{view.view_type}/{view.id}")
                resp = ayon_api.get_server_api_connection().raw_patch(
                    endpoint, json=payload
                )
            else:
                endpoint = self._endpoint(f"views/{view.view_type}")
                resp = ayon_api.get_server_api_connection().raw_post(
                    endpoint, json=payload
                )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to save view %s", view.id)
            self.error.emit(f"Failed to save view: {exc}")
            raise

        data = self._extract_data(resp)
        if isinstance(data, dict) and data:
            merged = {**payload, **data}
            try:
                saved = View.from_payload(merged)
            except Exception:  # noqa: BLE001
                log.exception(
                    "Server returned malformed view payload: %r", data
                )
                saved = view
        else:
            saved = view

        # Update the id-map and per-type cache in-place.
        if saved.id:
            self._id_to_type[saved.id] = saved.view_type
        self._upsert_cache(saved)

        self.view_saved.emit(saved.id)
        self.views_changed.emit(saved.view_type)
        return saved

    def delete_view(self, view_id: str) -> None:
        """Delete *view_id* on the server.

        The view type is resolved via the id-map (populated by
        :meth:`list_views` and :meth:`save_view`), so this works even
        when the per-type list cache has been cleared by
        :meth:`set_project`.  Unknown ids emit an :attr:`error` signal.

        Does nothing (without emitting :attr:`error`) when no project
        is set.

        Args:
            view_id: Identifier of the view to delete.
        """
        if not self._project_name:
            return

        view_type = self._id_to_type.get(view_id)
        if view_type is None:
            self.error.emit(f"Unknown view id: {view_id}")
            return

        try:
            ayon_api.delete(
                f"views/{view_type}/{view_id}",
                project_name=self._project_name,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to delete view %s", view_id)
            self.error.emit(f"Failed to delete view: {exc}")
            return

        # Remove in-place from the per-type cache if populated.
        self._id_to_type.pop(view_id, None)
        view_list = self._cache.get(view_type)
        if view_list is not None:
            self._cache[view_type] = [v for v in view_list if v.id != view_id]

        self.view_deleted.emit(view_id)
        self.views_changed.emit(view_type)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _endpoint(self, path: str) -> str:
        """Return *path* with ``project_name`` query string appended.

        Used for POST / PATCH which must send the body as JSON; the
        kwargs-as-body convention of :func:`ayon_api.post` clashes with
        the project_name-as-query-param requirement of the endpoint.

        Args:
            path: Endpoint path without leading slash.

        Returns:
            ``"{path}?project_name=<p>"`` when a project is set,
            otherwise *path* unchanged.
        """
        if not self._project_name:
            return path
        query = urlencode({"project_name": self._project_name})
        sep = "&" if "?" in path else "?"
        return f"{path}{sep}{query}"

    @staticmethod
    def _extract_data(resp: Any) -> Any:
        """Best-effort extraction of the JSON body from a response."""
        data = getattr(resp, "data", None)
        if data is not None:
            return data
        # Fall back to .json() for raw requests.Response-like objects.
        json_fn = getattr(resp, "json", None)
        if callable(json_fn):
            try:
                return json_fn()
            except Exception:  # noqa: BLE001
                return None
        return None

    def _upsert_cache(self, view: View) -> None:
        """Insert or replace *view* in the per-type cache in place.

        Does nothing if the type is not yet in the cache (the next
        ``list_views`` call will fetch a fresh list anyway).

        Args:
            view: The view to upsert.
        """
        view_list = self._cache.get(view.view_type)
        if view_list is None:
            return
        for i, v in enumerate(view_list):
            if v.id == view.id:
                view_list[i] = view
                break
        else:
            view_list.append(view)
        view_list.sort(key=lambda v: (v.position, v.label.lower()))
