from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, Optional

import ayon_api
from qtpy import QtCore

from ayon_core.pipeline import thumbnails_grid as thumbnails_grid_mod
from ayon_core.pipeline.load.reviewables import materialize_reviewable

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import get_current_host_name
from ayon_core.lib import NestedCacheItem, CacheItem, filter_profiles
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.lib.transcoding import VIDEO_EXTENSIONS
from ayon_core.pipeline import Anatomy, get_current_context
from ayon_core.host import ILoadHost
from ayon_core.tools.common_models import (
    ProjectsModel,
    HierarchyModel,
    ThumbnailsModel,
    TagItem,
    ProductTypeIconMapping,
    UsersModel,
)

from .abstract import (
    ActionItem,
    BackendLoaderController,
    FrontendLoaderController,
    ProductTypesFilter,
)
from .models import (
    SelectionModel,
    ProductsModel,
    LoaderActionsModel,
    SiteSyncModel,
)

GRID_THUMB_SENDER = "loader.grid_thumbnail"


class GridThumbnailEmitter(QtCore.QObject):
    """Qt signal holder; ``LoaderController`` is not a ``QObject``."""

    ready = QtCore.Signal(str, str, str)


class _GridThumbRunnable(QtCore.QRunnable):
    """Background downscale or ffmpeg frame for a grid tile."""

    def __init__(
        self,
        controller: "LoaderController",
        generation_snapshot: int,
        product_id: str,
        version_id: str,
        kind: str,
        src_path: str,
        cache_key: str,
        project_name: str,
        *,
        reviewable_file_id: Optional[str] = None,
        reviewable_label: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._generation_snapshot = generation_snapshot
        self._product_id = product_id
        self._version_id = version_id
        self._kind = kind
        self._src_path = src_path
        self._cache_key = cache_key
        self._project_name = project_name
        self._reviewable_file_id = reviewable_file_id
        self._reviewable_label = reviewable_label or ""

    def run(self) -> None:
        ctrl = self._controller
        inflight_key = (self._product_id, self._version_id)
        if ctrl._grid_thumb_generation != self._generation_snapshot:
            ctrl._grid_thumb_inflight.discard(inflight_key)
            return

        out_path = None
        try:
            if self._kind == "reviewable":
                fid = self._reviewable_file_id
                if fid:
                    mat = materialize_reviewable(
                        self._project_name,
                        self._version_id,
                        fid,
                        self._reviewable_label,
                    )
                    if mat and os.path.isfile(mat):
                        if thumbnails_grid_mod.is_image_file_path(mat):
                            key = thumbnails_grid_mod.cache_key_for_source(
                                self._version_id,
                                mat,
                            )
                            out_path = (
                                thumbnails_grid_mod.optimize_image_to_grid_cache(
                                    mat,
                                    self._project_name,
                                    key,
                                )
                            )
                        elif thumbnails_grid_mod.is_video_file_path(mat):
                            key = thumbnails_grid_mod.cache_key_for_source(
                                self._version_id,
                                mat,
                            )
                            out_path = (
                                thumbnails_grid_mod.extract_video_first_frame_to_cache(
                                    mat,
                                    self._project_name,
                                    key,
                                )
                            )
            elif self._kind == "image":
                out_path = thumbnails_grid_mod.optimize_image_to_grid_cache(
                    self._src_path,
                    self._project_name,
                    self._cache_key,
                )
            else:
                out_path = (
                    thumbnails_grid_mod.extract_video_first_frame_to_cache(
                        self._src_path,
                        self._project_name,
                        self._cache_key,
                    )
                )
        except Exception:
            ctrl.log.debug("Grid thumbnail job failed", exc_info=True)

        if (
            out_path
            and ctrl._grid_thumb_generation == self._generation_snapshot
        ):
            ctrl._grid_thumb_emitter.ready.emit(
                self._product_id, self._version_id, out_path
            )

        ctrl._grid_thumb_inflight.discard(inflight_key)


class ExpectedSelection:
    def __init__(self, controller):
        self._project_name = None
        self._folder_id = None

        self._project_selected = True
        self._folder_selected = True

        self._controller = controller

    def _emit_change(self):
        self._controller.emit_event(
            "expected_selection_changed",
            self.get_expected_selection_data(),
        )

    def set_expected_selection(self, project_name, folder_id):
        self._project_name = project_name
        self._folder_id = folder_id

        self._project_selected = False
        self._folder_selected = False
        self._emit_change()

    def get_expected_selection_data(self):
        project_current = False
        folder_current = False
        if not self._project_selected:
            project_current = True
        elif not self._folder_selected:
            folder_current = True
        return {
            "project": {
                "name": self._project_name,
                "current": project_current,
                "selected": self._project_selected,
            },
            "folder": {
                "id": self._folder_id,
                "current": folder_current,
                "selected": self._folder_selected,
            },
        }

    def is_expected_project_selected(self, project_name):
        return project_name == self._project_name and self._project_selected

    def is_expected_folder_selected(self, folder_id):
        return folder_id == self._folder_id and self._folder_selected

    def expected_project_selected(self, project_name):
        if project_name != self._project_name:
            return False
        self._project_selected = True
        self._emit_change()
        return True

    def expected_folder_selected(self, folder_id):
        if folder_id != self._folder_id:
            return False
        self._folder_selected = True
        self._emit_change()
        return True


class LoaderController(BackendLoaderController, FrontendLoaderController):
    """

    Args:
        host (Optional[AbstractHost]): Host object. Defaults to None.
    """

    def __init__(self, host=None):
        self._log = None
        self._host = host

        self._event_system = self._create_event_system()

        self._project_anatomy_cache = NestedCacheItem(levels=1, lifetime=60)
        self._loaded_products_cache = CacheItem(
            default_factory=set, lifetime=60
        )

        self._selection_model = SelectionModel(self)
        self._expected_selection = ExpectedSelection(self)
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._products_model = ProductsModel(self)
        self._loader_actions_model = LoaderActionsModel(self)
        self._thumbnails_model = ThumbnailsModel()
        self._sitesync_model = SiteSyncModel(self)
        self._users_model = UsersModel(self)

        self._grid_thumb_emitter = GridThumbnailEmitter()
        self._grid_thumb_generation = 0
        self._grid_thumb_inflight: set[str] = set()
        self._grid_image_pool = QtCore.QThreadPool()
        self._grid_image_pool.setMaxThreadCount(4)
        self._grid_video_pool = QtCore.QThreadPool()
        self._grid_video_pool.setMaxThreadCount(2)

    @property
    def log(self):
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    def get_window_subtitle(self) -> Optional[str]:
        if self._host is None:
            return None
        return self._host.name

    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        username = self._users_model.get_current_username()
        assignees = []
        if username:
            assignees.append(username)
        return self._hierarchy_model.get_entity_ids_for_assignees(
            project_name, assignees
        )

    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        action_items = self._loader_actions_model.get_action_items(
            project_name, entity_ids, entity_type
        )

        site_sync_items = self._sitesync_model.get_sitesync_action_items(
            project_name, entity_ids, entity_type
        )
        action_items.extend(site_sync_items)
        return action_items

    # ---------------------------------
    # Implementation of abstract methods
    # ---------------------------------
    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def reset(self):
        self.cancel_grid_thumbnail_resolve()
        self._emit_event("controller.reset.started")

        project_name = self.get_selected_project_name()
        folder_ids = self.get_selected_folder_ids()

        self._project_anatomy_cache.reset()
        self._loaded_products_cache.reset()

        self._products_model.reset()
        self._hierarchy_model.reset()
        self._loader_actions_model.reset()
        self._projects_model.reset()
        self._thumbnails_model.reset()
        self._sitesync_model.reset()
        self._users_model.reset()

        self._projects_model.refresh()

        if not project_name and not folder_ids:
            context = self.get_current_context()
            project_name = context["project_name"]
            folder_id = context["folder_id"]
            self.set_expected_selection(project_name, folder_id)

        self._emit_event("controller.reset.finished")

    # Expected selection helpers
    def get_expected_selection_data(self):
        return self._expected_selection.get_expected_selection_data()

    def set_expected_selection(self, project_name, folder_id):
        self._expected_selection.set_expected_selection(
            project_name, folder_id
        )

    def expected_project_selected(self, project_name):
        self._expected_selection.expected_project_selected(project_name)

    def expected_folder_selected(self, folder_id):
        self._expected_selection.expected_folder_selected(folder_id)

    # Entity model wrappers
    def get_project_items(self, sender=None):
        return self._projects_model.get_project_items(sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(project_name, sender)

    def get_project_status_items(self, project_name, sender=None):
        return self._projects_model.get_project_status_items(
            project_name, sender
        )

    def get_product_type_icons_mapping(
        self, project_name: Optional[str]
    ) -> ProductTypeIconMapping:
        return self._projects_model.get_product_type_icons_mapping(
            project_name
        )

    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_ids, sender=None):
        output = []
        for folder_id in folder_ids:
            output.extend(
                self._hierarchy_model.get_task_items(
                    project_name, folder_id, sender
                )
            )
        return output

    def get_task_type_items(self, project_name, sender=None):
        return self._projects_model.get_task_type_items(project_name, sender)

    def get_folder_labels(self, project_name, folder_ids):
        folder_items_by_id = self._hierarchy_model.get_folder_items_by_id(
            project_name, folder_ids
        )
        output = {}
        for folder_id, folder_item in folder_items_by_id.items():
            label = None
            if folder_item is not None:
                label = folder_item.label
            output[folder_id] = label
        return output

    def get_available_tags_by_entity_type(
        self, project_name: str
    ) -> dict[str, list[str]]:
        return self._hierarchy_model.get_available_tags_by_entity_type(
            project_name
        )

    def get_project_anatomy_tags(self, project_name: str) -> list[TagItem]:
        return self._projects_model.get_project_anatomy_tags(project_name)

    def get_product_items(self, project_name, folder_ids, sender=None):
        return self._products_model.get_product_items(
            project_name, folder_ids, sender
        )

    def get_product_item(self, project_name, product_id):
        return self._products_model.get_product_item(project_name, product_id)

    def get_product_type_items(self, project_name):
        return self._products_model.get_product_type_items(project_name)

    def get_representation_items(
        self,
        project_name,
        version_ids,
        sender=None,
        *,
        product_version_pairs=None,
    ):
        pairs = product_version_pairs
        if pairs is None:
            rows = self.get_selected_version_selection_rows()
            if rows:
                pairs = [
                    (r["product_id"], r["version_id"])
                    for r in rows
                    if r.get("product_id") and r.get("version_id")
                ]
        return self._products_model.get_repre_items(
            project_name,
            version_ids,
            sender,
            product_version_pairs=pairs,
        )

    def get_versions_representation_count(
        self,
        project_name,
        version_ids,
        sender=None,
        *,
        product_version_pairs=None,
    ):
        pairs = product_version_pairs
        if pairs is None:
            rows = self.get_selected_version_selection_rows()
            if rows:
                pairs = [
                    (r["product_id"], r["version_id"])
                    for r in rows
                    if r.get("product_id") and r.get("version_id")
                ]
        return self._products_model.get_versions_repre_count(
            project_name,
            version_ids,
            sender,
            product_version_pairs=pairs,
        )

    def get_folder_thumbnail_ids(self, project_name, folder_ids):
        return self._thumbnails_model.get_folder_thumbnail_ids(
            project_name, folder_ids
        )

    def get_version_thumbnail_ids(self, project_name, version_ids):
        return self._thumbnails_model.get_version_thumbnail_ids(
            project_name, version_ids
        )

    def get_thumbnail_paths(
        self,
        project_name,
        entity_type,
        entity_ids,
    ):
        return self._thumbnails_model.get_thumbnail_paths(
            project_name, entity_type, entity_ids
        )

    @property
    def grid_thumbnail_ready(self):
        """``Signal(product_id, version_id, path)`` for grid pixmap updates."""
        return self._grid_thumb_emitter.ready

    def cancel_grid_thumbnail_resolve(self) -> None:
        """Invalidate queued grid thumbnail jobs (model/project reset)."""
        self._grid_thumb_generation += 1
        self._grid_thumb_inflight.clear()

    def get_representation_items_grouped(
        self,
        project_name: str,
        version_ids: set[str],
        sender: Optional[str] = None,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ) -> dict[tuple[str, str], list]:
        pairs = product_version_pairs
        if pairs is None:
            rows = self.get_selected_version_selection_rows()
            if rows:
                pairs = [
                    (r["product_id"], r["version_id"])
                    for r in rows
                    if r.get("product_id") and r.get("version_id")
                ]
        return self._products_model.get_repre_items_grouped(
            project_name,
            version_ids,
            sender,
            product_version_pairs=pairs,
        )

    def resolve_grid_thumbnail_paths(
        self,
        project_name: str,
        version_ids: set[str],
        sender: Optional[str] = None,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ) -> dict[tuple[str, str], Optional[str]]:
        """Resolve pixmap-ready paths; queues derivatives when needed.

        Synchronous hits are returned in the dict; ``None`` means async
        processing may still deliver via :attr:`grid_thumbnail_ready`.
        Keys are ``(product_id, version_id)`` rows.
        """
        if not version_ids:
            return {}
        if not project_name:
            return {}

        pairs = product_version_pairs
        if not pairs:
            pairs = self._products_model._infer_product_version_pairs(
                project_name, version_ids
            )
        pairs = [(pid, vid) for pid, vid in pairs if vid in version_ids]
        if not pairs:
            return {}

        snd = sender if sender is not None else GRID_THUMB_SENDER
        grouped = self.get_representation_items_grouped(
            project_name, version_ids, snd, product_version_pairs=pairs
        )
        canonical = self._thumbnails_model.get_thumbnail_paths(
            project_name, "version", version_ids
        )
        gen_snapshot = self._grid_thumb_generation

        output: dict[tuple[str, str], Optional[str]] = {}
        for product_id, version_id in pairs:
            sync_path, jobs = (
                thumbnails_grid_mod.pick_grid_thumbnail_sync_and_jobs(
                    project_name,
                    version_id,
                    grouped.get((product_id, version_id), []),
                    canonical.get(version_id),
                )
            )
            key = (product_id, version_id)
            if sync_path:
                output[key] = sync_path
                continue

            output[key] = None
            if not jobs:
                continue
            job = jobs[0]
            kind = job[0]
            if key in self._grid_thumb_inflight:
                continue
            self._grid_thumb_inflight.add(key)
            if kind == "reviewable":
                _, fid, lab = job
                pool = self._grid_video_pool
                pool.start(
                    _GridThumbRunnable(
                        self,
                        gen_snapshot,
                        product_id,
                        version_id,
                        kind,
                        "",
                        "",
                        project_name,
                        reviewable_file_id=fid,
                        reviewable_label=lab,
                    )
                )
                continue

            _, src_path, cache_key = job
            pool = (
                self._grid_video_pool
                if kind == "video"
                else self._grid_image_pool
            )
            pool.start(
                _GridThumbRunnable(
                    self,
                    gen_snapshot,
                    product_id,
                    version_id,
                    kind,
                    src_path,
                    cache_key,
                    project_name,
                )
            )

        return output

    def change_products_group(self, project_name, product_ids, group_name):
        self._products_model.change_products_group(
            project_name, product_ids, group_name
        )

    def get_versions_action_items(self, project_name, version_ids):
        return self.get_action_items(project_name, version_ids, "version")

    def get_representations_action_items(
        self, project_name, representation_ids
    ):
        return self.get_action_items(
            project_name, representation_ids, "representation"
        )

    def get_drag_drop_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
        drop_context_id: Optional[str] = None,
    ) -> list[ActionItem]:
        """Action items eligible for drag-and-drop, optionally filtered by drop context."""
        items = self.get_action_items(project_name, entity_ids, entity_type)
        out = []
        for item in items:
            if not getattr(item, "drag_drop_enabled", True):
                continue
            if drop_context_id is not None:
                contexts = getattr(item, "drag_drop_contexts", None)
                if contexts is not None and drop_context_id not in contexts:
                    continue
            out.append(item)
        return out

    def get_drag_drop_file_paths(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[str]:
        """Resolve local file paths for drag-drop; used for OS file copy when dropping on Explorer/desktop."""
        anatomy = self._get_project_anatomy(project_name)
        if not anatomy:
            return []
        return self._loader_actions_model.get_representation_file_paths(
            project_name, entity_ids, entity_type, anatomy
        )

    def get_drag_drop_emit_file_uris(self) -> bool:
        """Whether to attach file URLs to drag MIME data (disable for lower latency)."""
        project_name = self.get_selected_project_name()
        if not project_name:
            return True
        settings = get_project_settings(project_name)
        return (
            settings.get("core", {})
            .get("tools", {})
            .get("loader", {})
            .get("drag_drop_emit_file_uris", True)
        )

    def resolve_drag_drop_representation_selection(
        self,
        project_name: str,
        version_ids: set[str],
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Map version ids to primary representation ids for Loader drag."""
        return self._loader_actions_model.resolve_drag_drop_representation_selection(
            project_name, version_ids
        )

    def collect_drag_drop_actions_for_version_resolution(
        self,
        project_name: str,
        version_ids: set[str],
        primary_by_vid: dict[str, str],
        candidates_by_vid: dict[str, list[str]],
    ) -> tuple[list[ActionItem], str, list[str], Dict[str, Any]]:
        """Merge loader ActionItems after per-version default representation resolution.

        Returns:
            action_items, effective_entity_type, flat_entity_ids, extras.
            extras may include needs_rep_choice, actions_by_repre_id, repre_names_by_id
            when one version has multiple representations (picker instead of fan-out).
        """
        extras: Dict[str, Any] = {}

        if len(version_ids) == 1:
            vid = next(iter(version_ids))
            cands = candidates_by_vid.get(vid) or []
            if len(cands) > 1:
                want = frozenset(str(x) for x in cands)
                repre_names_by_id: dict[str, str] = {}
                for r in ayon_api.get_representations(
                    project_name, version_ids={vid}
                ):
                    rid = str(r["id"])
                    if rid not in want:
                        continue
                    repre_names_by_id[rid] = str(r.get("name") or "")
                for rid in cands:
                    rs = str(rid)
                    repre_names_by_id.setdefault(rs, rs[:8])

                actions_by_repre_id: dict[str, list[ActionItem]] = {}
                for rid in cands:
                    rs = str(rid)
                    actions_by_repre_id[rs] = (
                        self.get_drag_drop_action_items(
                            project_name, {rs}, "representation"
                        )
                        or []
                    )
                extras["needs_rep_choice"] = True
                extras["actions_by_repre_id"] = actions_by_repre_id
                extras["repre_names_by_id"] = repre_names_by_id
                extras["ambiguous_version_id"] = vid
                return [], "version", [vid], extras

        merged: list[ActionItem] = []
        flat_entity_ids: list[str] = []

        for vid in version_ids:
            cands = candidates_by_vid.get(vid) or []
            prim = primary_by_vid.get(vid)
            if len(cands) <= 1:
                rid = prim or (cands[0] if cands else None)
                if not rid:
                    continue
                flat_entity_ids.append(rid)
                merged.extend(
                    self.get_drag_drop_action_items(
                        project_name, {rid}, "representation"
                    )
                    or []
                )
            else:
                seen_keys: set[tuple[str, str, str]] = set()
                for rid in cands:
                    flat_entity_ids.append(rid)
                    for it in (
                        self.get_drag_drop_action_items(
                            project_name, {rid}, "representation"
                        )
                        or []
                    ):
                        key = (it.identifier, it.label, str(it.data))
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        merged.append(it)

        deduped: list[ActionItem] = []
        seen_final: set[tuple[str, str, str]] = set()
        for it in merged:
            key = (it.identifier, it.label, str(it.data))
            if key in seen_final:
                continue
            seen_final.add(key)
            deduped.append(it)

        uniq_entity: list[str] = []
        seen_e: set[str] = set()
        for e in flat_entity_ids:
            if e not in seen_e:
                seen_e.add(e)
                uniq_entity.append(e)

        return deduped, "representation", uniq_entity, extras

    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: Optional[dict[str, Any]],
        options: dict[str, Any],
        form_values: dict[str, Any],
    ):
        if self._sitesync_model.is_sitesync_action(identifier):
            self._sitesync_model.trigger_action_item(
                project_name,
                data,
            )
            return

        self._loader_actions_model.trigger_action_item(
            identifier=identifier,
            project_name=project_name,
            selected_ids=selected_ids,
            selected_entity_type=selected_entity_type,
            data=data,
            options=options,
            form_values=form_values,
        )

    # Selection model wrappers
    def get_selected_project_name(self):
        return self._selection_model.get_selected_project_name()

    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)

    # Selection model wrappers
    def get_selected_folder_ids(self):
        return self._selection_model.get_selected_folder_ids()

    def set_selected_folders(self, folder_ids):
        self._selection_model.set_selected_folders(folder_ids)

    def get_selected_task_ids(self):
        return self._selection_model.get_selected_task_ids()

    def set_selected_tasks(self, task_ids):
        self._selection_model.set_selected_tasks(task_ids)

    def get_selected_version_ids(self):
        return self._selection_model.get_selected_version_ids()

    def set_selected_versions(self, version_ids, selection_rows=None):
        self._selection_model.set_selected_versions(version_ids, selection_rows)

    def get_selected_version_selection_rows(self):
        return self._selection_model.get_selected_version_selection_rows()

    def get_selected_representation_ids(self):
        return self._selection_model.get_selected_representation_ids()

    def set_selected_representations(self, repre_ids):
        self._selection_model.set_selected_representations(repre_ids)

    def fill_root_in_source(self, source):
        project_name = self.get_selected_project_name()
        anatomy = self._get_project_anatomy(project_name)
        if anatomy is None:
            return source

        try:
            return anatomy.fill_root(source)
        except Exception:
            return source

    def get_current_context(self):
        if self._host is None:
            return {
                "project_name": None,
                "folder_id": None,
                "task_name": None,
            }
        if hasattr(self._host, "get_current_context"):
            context = self._host.get_current_context()
        else:
            context = get_current_context()
        folder_id = None
        project_name = context.get("project_name")
        folder_path = context.get("folder_path")
        if project_name and folder_path:
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path, fields=["id"]
            )
            if folder_entity:
                folder_id = folder_entity["id"]
        return {
            "project_name": project_name,
            "folder_id": folder_id,
            "task_name": context.get("task_name"),
        }

    def get_loaded_product_ids(self):
        if self._host is None:
            return set()

        context = self.get_current_context()
        project_name = context["project_name"]
        if not project_name:
            return set()

        if not self._loaded_products_cache.is_valid:
            try:
                if isinstance(self._host, ILoadHost):
                    containers = self._host.get_containers()
                else:
                    containers = self._host.ls()

            except BaseException:
                self.log.error(
                    "Failed to collect loaded products.", exc_info=True
                )
                containers = []

            repre_ids = set()
            for container in containers:
                try:
                    repre_id = container.get("representation")
                    # Ignore invalid representation ids.
                    # - invalid representation ids may be available if e.g. is
                    #   opened scene from OpenPype whe 'ObjectId' was used
                    #   instead of 'uuid'.
                    # NOTE: Server call would crash if there is any invalid id.
                    #   That would cause crash we won't get any information.
                    uuid.UUID(repre_id)
                    repre_ids.add(repre_id)
                except (ValueError, TypeError, AttributeError):
                    pass

            product_ids = self._products_model.get_product_ids_by_repre_ids(
                project_name, repre_ids
            )
            self._loaded_products_cache.update_data(product_ids)
        return self._loaded_products_cache.get_data()

    def is_sitesync_enabled(self, project_name=None):
        return self._sitesync_model.is_sitesync_enabled(project_name)

    def get_active_site_icon_def(self, project_name):
        return self._sitesync_model.get_active_site_icon_def(project_name)

    def get_remote_site_icon_def(self, project_name):
        return self._sitesync_model.get_remote_site_icon_def(project_name)

    def get_active_site(self, project_name):
        return self._sitesync_model.get_active_site(project_name)

    def get_remote_site(self, project_name):
        return self._sitesync_model.get_remote_site(project_name)

    def get_version_sync_availability(self, project_name, version_ids):
        return self._sitesync_model.get_version_sync_availability(
            project_name, version_ids
        )

    def get_representations_sync_status(
        self, project_name, representation_ids
    ):
        return self._sitesync_model.get_representations_sync_status(
            project_name, representation_ids
        )

    def is_loaded_products_supported(self):
        return self._host is not None

    def is_standard_projects_filter_enabled(self):
        return self._host is not None

    def is_video_file(self, filepath):
        """Check if file is a video file based on extension.

        Args:
            filepath (str): Path to file to check.

        Returns:
            bool: True if file is a video file.
        """
        if not filepath:
            return False
        ext = os.path.splitext(filepath)[1].lower()
        return ext in VIDEO_EXTENSIONS

    def get_reviewable_path(self, project_name, version_ids):
        """Get reviewable video path using provider chain.

        Tries providers in priority order until one returns a path.
        This allows different sources (representations, activities,
        external trackers) to provide reviewable videos.

        Args:
            project_name (str): Project name
            version_ids (set[str]): Version IDs

        Returns:
            Optional[str]: Path to video or None
        """
        from ayon_core.tools.loader.providers import (
            discover_reviewable_providers,
        )

        if not version_ids or not project_name:
            return None

        providers = discover_reviewable_providers()

        for provider_cls in providers:
            provider = provider_cls()

            # Check if provider is available for this project
            try:
                if not provider.is_available(project_name, self):
                    self.log.debug(
                        f"Provider '{provider.label}' not available "
                        f"for {project_name}"
                    )
                    continue
            except Exception as e:
                self.log.warning(
                    f"Provider '{provider.label}' "
                    f"availability check failed: {e}"
                )
                continue

            # Try to get reviewable from this provider
            try:
                video_path = provider.get_reviewable_path(
                    project_name, version_ids, self
                )
                if video_path:
                    self.log.debug(
                        f"Found reviewable via '{provider.label}': "
                        f"{video_path}"
                    )
                    return video_path
            except Exception as e:
                self.log.warning(
                    f"Provider '{provider.label}' failed: {e}", exc_info=True
                )
                continue

        self.log.debug("No reviewable found via any provider")
        return None

    def extract_video_first_frame(self, video_path):
        """Extract first frame from video for preview.

        Uses persistent cache under thumbnails/grid_derivatives (Loader grid).

        Args:
            video_path (str): Path to video file.

        Returns:
            Optional[QtGui.QPixmap]: First frame as pixmap or None if failed.
        """
        try:
            project_name = self.get_selected_project_name() or "_"
            key = thumbnails_grid_mod.cache_key_for_source(
                "sidebar_preview", video_path
            )
            return thumbnails_grid_mod.pixmap_from_cached_video_preview(
                video_path, project_name, key
            )
        except Exception as e:
            self.log.warning(f"Failed to extract first frame: {e}")

        return None

    def _get_project_anatomy(self, project_name):
        if not project_name:
            return None
        cache = self._project_anatomy_cache[project_name]
        if not cache.is_valid:
            cache.update_data(Anatomy(project_name))
        return cache.get_data()

    def get_version_padding(self, project_name: Optional[str]) -> int:
        """Anatomy ``version_padding`` for ``project_name``, or 3 if missing."""
        if not project_name:
            return 3
        try:
            anatomy = self._get_project_anatomy(project_name)
            if anatomy is None:
                return 3
            return max(1, int(anatomy.templates_obj.version_padding))
        except Exception:
            return 3

    def _create_event_system(self):
        return QueuedEventSystem()

    def _emit_event(self, topic, data=None):
        self._event_system.emit(topic, data or {}, "controller")

    def get_product_types_filter(self):
        output = ProductTypesFilter(is_allow_list=False, product_types=[])
        # Without host is not determined context
        if self._host is None:
            return output

        context = self.get_current_context()
        project_name = context.get("project_name")
        if not project_name:
            return output
        settings = get_project_settings(project_name)
        profiles = settings["core"]["tools"]["loader"][
            "product_type_filter_profiles"
        ]
        if not profiles:
            return output

        folder_id = context.get("folder_id")
        task_name = context.get("task_name")
        task_type = None
        if folder_id and task_name:
            task_entity = ayon_api.get_task_by_name(
                project_name, folder_id, task_name, fields={"taskType"}
            )
            if task_entity:
                task_type = task_entity.get("taskType")

        host_name = getattr(self._host, "name", get_current_host_name())
        profile = filter_profiles(
            profiles,
            {
                "hosts": host_name,
                "task_types": task_type,
            },
        )
        if profile:
            # TODO remove 'is_include' after release '0.4.3'
            is_allow_list = profile.get("is_include")
            if is_allow_list is None:
                is_allow_list = profile["filter_type"] == "is_allow_list"
            output = ProductTypesFilter(
                is_allow_list=is_allow_list,
                product_types=profile["filter_product_types"],
            )
        return output
