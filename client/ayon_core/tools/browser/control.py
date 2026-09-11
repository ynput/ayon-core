from __future__ import annotations

import logging
import uuid
import typing
from typing import Optional, Any

import ayon_api

from ayon_core.addon import AddonsManager
from ayon_core.lib import (
    NestedCacheItem,
    CacheItem,
)
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.pipeline import Anatomy, get_current_context
from ayon_core.host import ILoadHost, AbstractHost
from ayon_core.tools.common_models import (
    SettingsModel,
    ProjectsModel,
    HierarchyModel,
    ThumbnailsModel,
    TagItem,
    ProductTypeIconMapping,
    UsersModel,
)

from .abstract import (
    AbstractBrowserController,
    ActionItem,
)
from .models import (
    ProductsModel,
    LoaderActionsModel,
    SiteSyncModel
)


if typing.TYPE_CHECKING:
    from ayon_core.tools.common_models.settings import TaskSortMode

NOT_SET = object()


class BrowserController(AbstractBrowserController):
    """

    Args:
        host (Optional[AbstractHost]): Host object. Defaults to None.
    """

    def __init__(self, host: Optional[AbstractHost] = None) -> None:
        self._log = None
        self._host = host

        self._event_system = self._create_event_system()

        self._project_settings = {}

        self._project_anatomy_cache = NestedCacheItem(
            levels=1, lifetime=60)
        self._loaded_products_cache = CacheItem(
            default_factory=set, lifetime=60)
        self._loaded_versions_cache = CacheItem(
            default_factory=set, lifetime=60)
        self._addons_manager = AddonsManager()

        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._products_model = ProductsModel(self)
        self._loader_actions_model = LoaderActionsModel(self)
        self._thumbnails_model = ThumbnailsModel()
        self._sitesync_model = SiteSyncModel(
            self._addons_manager,
        )
        self._users_model = UsersModel(self)
        self._settings_model = SettingsModel()

    @property
    def log(self):
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    @property
    def addons_manager(self) -> AddonsManager:
        """Return the shared initialized addon manager."""
        return self._addons_manager

    # ---------------------------------
    # Implementation of abstract methods
    # ---------------------------------
    def get_window_subtitle(self) -> Optional[str]:
        if self._host is None:
            return None
        return self._host.name

    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def reset(self):
        self._emit_event("controller.reset.started")

        self._project_settings = {}

        self._project_anatomy_cache.reset()
        self._loaded_products_cache.reset()
        self._loaded_versions_cache.reset()

        self._products_model.reset()
        self._hierarchy_model.reset()
        self._loader_actions_model.reset()
        self._projects_model.reset()
        self._thumbnails_model.reset()
        self._sitesync_model.reset()
        self._users_model.reset()
        self._settings_model.reset()

        self._projects_model.refresh()

        self._emit_event("controller.reset.finished")

    # Entity model wrappers
    def get_project_items(self, sender=None):
        return self._projects_model.get_project_items(sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

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
            output.extend(self._hierarchy_model.get_task_items(
                project_name, folder_id, sender
            ))
        return output

    def get_task_type_items(self, project_name, sender=None):
        return self._projects_model.get_task_type_items(
            project_name, sender
        )

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

    def get_available_tags_by_entity_type(
        self, project_name: str
    ) -> dict[str, list[str]]:
        return self._hierarchy_model.get_available_tags_by_entity_type(
            project_name
        )

    def get_project_settings(self, project_name: str | None) -> dict:
        return self._settings_model.get_settings(project_name)

    def get_task_sorting_mode(self, project_name: str | None) -> TaskSortMode:
        return self._settings_model.get_task_sorting_mode(project_name)

    def get_project_entity(
        self, project_name: str | None
    ) -> dict[str, Any] | None:
        return self._projects_model.get_project_entity(project_name)

    def get_project_anatomy_tags(self, project_name: str) -> list[TagItem]:
        return self._projects_model.get_project_anatomy_tags(project_name)

    def get_product_items(self, project_name, folder_ids, sender=None):
        return self._products_model.get_product_items(
            project_name, folder_ids, sender)

    def get_product_item(self, project_name, product_id):
        return self._products_model.get_product_item(
            project_name, product_id
        )

    def get_product_type_items(self, project_name):
        return self._products_model.get_product_type_items(project_name)

    def get_representation_items(
        self, project_name, version_ids, sender=None
    ):
        return self._products_model.get_repre_items(
            project_name, version_ids, sender
        )

    def get_versions_representation_count(
        self, project_name, version_ids, sender=None
    ):
        return self._products_model.get_versions_repre_count(
            project_name, version_ids, sender
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

    def set_selected_project(self, project_name):
        # ProjectsCombobox does require this method
        pass

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
        if self._loaded_products_cache.is_valid:
            return self._loaded_products_cache.get_data()

        project_name = self._get_current_project_name()
        if not project_name:
            return set()

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

    def get_loaded_version_ids(self):
        """Return version IDs represented by current scene containers."""
        if self._host is None:
            return set()
        if self._loaded_versions_cache.is_valid:
            return self._loaded_versions_cache.get_data()

        project_name = self._get_current_project_name()
        if not project_name:
            return set()

        try:
            if isinstance(self._host, ILoadHost):
                containers = self._host.get_containers()
            else:
                containers = self._host.ls()
        except BaseException:
            self.log.error(
                "Failed to collect loaded versions.", exc_info=True
            )
            containers = []

        repre_ids = set()
        for container in containers:
            repre_id = container.get("representation")
            try:
                uuid.UUID(repre_id)
            except (ValueError, TypeError, AttributeError):
                continue
            repre_ids.add(repre_id)

        version_ids = set()
        if repre_ids:
            representations = ayon_api.get_representations(
                project_name,
                repre_ids,
                fields=["versionId"],
            )
            version_ids = {
                representation["versionId"]
                for representation in representations
                if representation.get("versionId")
            }
        self._loaded_versions_cache.update_data(version_ids)

        return self._loaded_versions_cache.get_data()

    def invalidate_loaded_containers(self) -> None:
        """Invalidate cached scene-container product and version IDs."""
        self._loaded_products_cache.reset()
        self._loaded_versions_cache.reset()

    def _get_current_project_name(self) -> str | None:
        """Return the current project without resolving the folder."""
        if hasattr(self._host, "get_current_context"):
            context = self._host.get_current_context()
        else:
            context = get_current_context()
        return context.get("project_name")

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

    def is_loaded_products_supported(self):
        return self._host is not None

    def is_standard_projects_filter_enabled(self):
        return self._host is not None

    def _create_event_system(self):
        return QueuedEventSystem()

    def _emit_event(self, topic, data=None):
        self._event_system.emit(topic, data or {}, "controller")

    def _get_project_anatomy(self, project_name):
        if not project_name:
            return None
        cache = self._project_anatomy_cache[project_name]
        if not cache.is_valid:
            cache.update_data(Anatomy(project_name))
        return cache.get_data()
