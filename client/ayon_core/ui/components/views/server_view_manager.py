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
from ayon_core.addon import get_bundle_information
from qtpy.QtCore import QObject  # type: ignore[attr-defined]

from .data_models import View, Scope, Visibility
from .view_manager import ViewManager

log = logging.getLogger(__name__)

_POWERPACK_ADDON_NAME = "powerpack"


class ServerViewManager(ViewManager):
    """ViewManager backed by AYON server REST endpoints.

    Endpoints (project-scoped, all take ``?project_name=<p>``):

    * ``GET    /api/views/{view_type}``
    * ``GET    /api/views/{view_type}/working``
    * ``POST   /api/views/{view_type}``
    * ``PATCH  /api/views/{view_type}/{view_id}``
    * ``POST   /api/addons/powerpack/{version}/views/{view_type}/{view_id}/share``
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
        # view_id -> Scope (used by delete_view to decide whether to pass
        # project_name; studio-scoped views must NOT include it).
        self._id_to_scope: dict[str, Scope] = {}
        self._powerpack_version: str | None = None

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
        self._id_to_scope.clear()
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

    def get_working_view(self, view_type: str) -> View | None:
        """Return the working view for *view_type* using the direct endpoint.

        Uses ``GET /api/views/{view_type}/working`` for faster lookup than
        scanning ``list_views``.

        Args:
            view_type: View-type identifier.

        Returns:
            Parsed working :class:`View`, or ``None`` when not found.
        """
        self._known_types.add(view_type)

        if not self._project_name:
            return None

        try:
            resp = ayon_api.get(
                f"views/{view_type}/working",
                project_name=self._project_name,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to fetch working view for %s", view_type)
            self.error.emit(f"Failed to fetch working view: {exc}")
            return None

        payload = self._extract_data(resp)
        view_payload = self._extract_view_dict(payload)
        if not isinstance(view_payload, dict) or not view_payload:
            return None

        candidate = dict(view_payload)
        candidate["viewType"] = str(candidate.get("viewType") or view_type)

        try:
            parsed = View.from_payload(candidate)
        except Exception:  # noqa: BLE001
            log.exception(
                "Malformed working view payload for %s: %r",
                view_type,
                payload,
            )
            return None

        if parsed.id:
            self._id_to_type[parsed.id] = parsed.view_type
            self._id_to_scope[parsed.id] = parsed.scope
        self._upsert_cache(parsed)
        return parsed

    def get_default_project_view(self, view_type: str) -> View | None:
        """Return project default view using the dedicated ``/base`` endpoint."""
        self._known_types.add(view_type)

        if not self._project_name:
            return None

        try:
            resp = ayon_api.get(
                f"views/{view_type}/base",
                project_name=self._project_name,
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to fetch project default view for %s", view_type)
            self.error.emit(f"Failed to fetch project default view: {exc}")
            return None

        payload = self._extract_data(resp)
        return self._parse_default_view_payload(payload, view_type, Scope.PROJECT)

    def get_default_studio_view(self, view_type: str) -> View | None:
        """Return studio default view using the dedicated ``/base`` endpoint."""
        self._known_types.add(view_type)

        try:
            resp = ayon_api.get(f"views/{view_type}/base")
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to fetch studio default view for %s", view_type)
            self.error.emit(f"Failed to fetch studio default view: {exc}")
            return None

        payload = self._extract_data(resp)
        return self._parse_default_view_payload(payload, view_type, Scope.STUDIO)

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
        payload = self._extract_data(resp)
        if isinstance(payload, dict):
            items = payload.get("views", payload)
        else:
            items = payload
        if not isinstance(items, list):
            items = []

        views: list[View] = []
        for item in items:
            try:
                if not isinstance(item, dict):
                    continue

                view_id = str(item.get("id") or "").strip()
                if not view_id:
                    continue

                candidate: dict[str, Any] = dict(item)
                is_default_candidate = (
                    str(candidate.get("label") or "") == "__base__"
                )
                try:
                    resp = ayon_api.get(
                        f"views/{view_type}/{view_id}",
                        project_name=self._project_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    log.exception("Failed to fetch view %s", view_id)
                    self.error.emit(f"Failed to fetch view: {exc}")
                    continue

                raw_detail = self._extract_data(resp)
                detail_payload = self._extract_view_dict(raw_detail)

                # Do not let blank detail values overwrite valid
                # summary values from the list response.
                for key, value in detail_payload.items():
                    if key == "settings" and not value:
                        continue
                    if (
                        key in {"id", "label", "viewType"}
                        and (value is None or value == "")
                    ):
                        continue
                    candidate[key] = value

                candidate["viewType"] = str(
                    candidate.get("viewType") or view_type
                )

                parsed = View.from_payload(candidate)
                views.append(parsed)
            except Exception:  # noqa: BLE001
                log.exception("Skipping malformed view payload: %r", item)

        views.sort(key=lambda v: (v.position, v.label.lower()))
        self._cache[view_type] = views
        # Populate id-map for delete_view lookups.
        for v in views:
            if v.id:
                self._id_to_type[v.id] = view_type
                self._id_to_scope[v.id] = v.scope
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
        access_data = self._normalize_access_payload(payload.get("access"))
        should_share_access = self._has_positive_access(access_data)

        is_update = bool(view.id)
        if not is_update:
            payload.pop("id", None)

        try:
            # Use studio or project endpoints based on view scope
            if view.scope == Scope.STUDIO:
                # Studio-scoped views use studio endpoints
                if is_update:
                    endpoint = f"views/{view.view_type}/{view.id}"
                    resp = ayon_api.patch(endpoint, **payload)
                else:
                    endpoint = f"views/{view.view_type}"
                    resp = ayon_api.post(endpoint, **payload)
            else:
                # Project-scoped views use project-specific endpoints
                if is_update:
                    endpoint = self._endpoint(f"views/{view.view_type}/{view.id}")
                    resp = ayon_api.patch(endpoint, **payload)
                else:
                    endpoint = self._endpoint(f"views/{view.view_type}")
                    resp = ayon_api.post(endpoint, **payload)
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
            self._id_to_scope[saved.id] = saved.scope
        self._upsert_cache(saved)

        # Access grants are managed by the dedicated share endpoint.
        self.patch_view_access(saved.id, access_data, should_share_access)

        self.view_saved.emit(saved.id)
        self.views_changed.emit(saved.view_type)
        return saved

    def patch_view_access(self, view_id: str, access_data: dict[str, Any], should_share_access) -> None:
        """Patch per-view access data via the share endpoint.

        Args:
            view_id: Existing view identifier.
            access_data: Access mapping (e.g. ``{"__everyone__": 20}``).
            should_share_access: Whether to set the view visibility to
                public (True) or private (False).
        """
        if not view_id:
            return
        if not self._project_name:
            self.error.emit("Cannot patch view access without project name")
            return

        view_type = self._id_to_type.get(view_id)
        if not view_type:
            self.error.emit(f"Unknown view id for access patch: {view_id}")
            return

        payload_access = self._normalize_access_payload(access_data)
        if not payload_access:
            return

        powerpack_version = self._get_powerpack_version()
        if not powerpack_version:
            self.error.emit("Could not resolve powerpack addon version")
            return
        visibility = Visibility.PUBLIC.value if should_share_access else Visibility.PRIVATE.value
        try:
            con = ayon_api.get_server_api_connection()
            con.raw_post(
                "addons/"
                f"{_POWERPACK_ADDON_NAME}/{powerpack_version}"
                f"/views/{view_type}/{view_id}/share",
                params={"project_name": self._project_name},
                json={
                    "visibility": visibility,
                    "access": payload_access,
                },
            )
            # Update cache with new visibility
            view_list = self._cache.get(view_type)
            if view_list is not None:
                for view in view_list:
                    if view.id == view_id:
                        view.visibility = Visibility(visibility)
                        break
        except Exception as exc:  # noqa: BLE001
            log.exception("Failed to patch view access for %s", view_id)
            self.error.emit(f"Failed to patch view access: {exc}")

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

        view_scope = self._id_to_scope.get(view_id, Scope.PROJECT)
        is_studio = view_scope == Scope.STUDIO

        try:
            if is_studio:
                ayon_api.delete(f"views/{view_type}/{view_id}")
            else:
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
        self._id_to_scope.pop(view_id, None)
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

    @staticmethod
    def _extract_view_dict(payload: Any) -> dict[str, Any] | None:
        """Return a single-view dict from common detail response shapes."""
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("view"), dict):
            return payload["view"]
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        return payload

    def _parse_default_view_payload(
        self,
        payload: Any,
        view_type: str,
        scope: Scope,
    ) -> View | None:
        """Parse default view payload returned by ``/base`` endpoint."""
        view_payload = self._extract_view_dict(payload)
        if not isinstance(view_payload, dict) or not view_payload:
            return None

        # Error payloads can still be dicts; ignore them.
        if "id" not in view_payload and "detail" in view_payload:
            log.debug(
                "Default %s view for %s is unavailable: %s",
                scope.value,
                view_type,
                view_payload.get("detail"),
            )
            return None

        candidate = dict(view_payload)
        candidate["viewType"] = str(candidate.get("viewType") or view_type)
        candidate["scope"] = str(candidate.get("scope") or scope.value)
        candidate["label"] = str(candidate.get("label") or "__base__")
        candidate["working"] = False

        try:
            parsed = View.from_payload(candidate)
        except Exception:  # noqa: BLE001
            log.exception(
                "Malformed default %s payload for %s: %r",
                scope.value,
                view_type,
                payload,
            )
            return None

        if parsed.id:
            self._id_to_type[parsed.id] = parsed.view_type
            self._id_to_scope[parsed.id] = parsed.scope
        self._upsert_cache(parsed)
        return parsed

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

    @staticmethod
    def _normalize_access_payload(raw_access: Any) -> dict[str, int]:
        """Return a normalized ``access`` payload with integer values."""
        if not isinstance(raw_access, dict):
            return {}
        normalized: dict[str, int] = {}
        for key, value in raw_access.items():
            name = str(key).strip()
            if not name:
                continue
            try:
                normalized[name] = int(value)
            except (TypeError, ValueError):
                continue
        return normalized

    @staticmethod
    def _has_positive_access(access_data: dict[str, int]) -> bool:
        """Return True when any access level is above zero."""
        return any(level > 0 for level in access_data.values())

    def _get_powerpack_version(self) -> str | None:
        """Return powerpack version from the current session bundle."""
        if self._powerpack_version:
            return self._powerpack_version

        try:
            bundle_info = get_bundle_information()
        except Exception:  # noqa: BLE001
            log.exception("Failed to query bundle information")
            return None

        for addon in bundle_info.addons:
            if addon.name != _POWERPACK_ADDON_NAME:
                continue
            if addon.version:
                self._powerpack_version = addon.version
                return self._powerpack_version

        return None

