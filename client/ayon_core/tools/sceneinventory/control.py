import ayon_api

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.host import HostBase
from ayon_core.pipeline import (
    registered_host,
    get_current_context,
)
from ayon_core.tools.common_models import HierarchyModel, ProjectsModel

from .models import SiteSyncModel, ContainersModel


class SceneInventoryController:
    """This is a temporary controller for AYON.

    Goal of this controller is to provide a way to get current context.

    Also provides (hopefully) cleaner api for site sync.
    """

    def __init__(self, host=None):
        if host is None:
            host = registered_host()
        self._host = host
        self._current_context = None
        self._current_project = None
        self._current_folder_id = None
        self._current_folder_set = False

        self._containers_model = ContainersModel(self)
        self._sitesync_model = SiteSyncModel(self)
        # Switch dialog requirements
        self._hierarchy_model = HierarchyModel(self)
        self._projects_model = ProjectsModel(self)
        self._event_system = self._create_event_system()

    def get_host(self) -> HostBase:
        return self._host

    def emit_event(self, topic, data=None, source=None):
        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def reset(self):
        self._current_context = None
        self._current_project = None
        self._current_folder_id = None
        self._current_folder_set = False

        self._containers_model.reset()
        self._sitesync_model.reset()
        self._hierarchy_model.reset()

    def get_current_context(self):
        if self._current_context is None:
            if hasattr(self._host, "get_current_context"):
                self._current_context = self._host.get_current_context()
            else:
                self._current_context = get_current_context()
        return self._current_context

    def get_current_project_name(self):
        if self._current_project is None:
            self._current_project = self.get_current_context()["project_name"]
        return self._current_project

    def get_current_folder_id(self):
        if self._current_folder_set:
            return self._current_folder_id

        context = self.get_current_context()
        project_name = context["project_name"]
        folder_path = context.get("folder_path")
        folder_id = None
        if folder_path:
            folder = ayon_api.get_folder_by_path(project_name, folder_path)
            if folder:
                folder_id = folder["id"]

        self._current_folder_id = folder_id
        self._current_folder_set = True
        return self._current_folder_id

    def get_project_status_items(self):
        project_name = self.get_current_project_name()
        return self._projects_model.get_project_status_items(
            project_name, None
        )

    # Containers methods
    def get_containers(self):
        return self._containers_model.get_containers()

    def get_containers_by_item_ids(self, item_ids):
        return self._containers_model.get_containers_by_item_ids(item_ids)

    def get_container_items(self):
        return self._containers_model.get_container_items()

    def get_container_items_by_id(self, item_ids):
        return self._containers_model.get_container_items_by_id(item_ids)

    def get_representation_info_items(self, representation_ids):
        return self._containers_model.get_representation_info_items(
            representation_ids
        )

    def get_version_items(self, product_ids):
        return self._containers_model.get_version_items(product_ids)

    # Site Sync methods
    def is_sitesync_enabled(self):
        return self._sitesync_model.is_sitesync_enabled()

    def get_sites_information(self):
        return self._sitesync_model.get_sites_information()

    def get_site_provider_icons(self):
        return self._sitesync_model.get_site_provider_icons()

    def get_representations_site_progress(self, representation_ids):
        return self._sitesync_model.get_representations_site_progress(
            representation_ids
        )

    def resync_representations(self, representation_ids, site_type):
        return self._sitesync_model.resync_representations(
            representation_ids, site_type
        )

    # Switch dialog methods
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_folder_label(self, folder_id):
        if not folder_id:
            return None
        project_name = self.get_current_project_name()
        folder_item = self._hierarchy_model.get_folder_item(
            project_name, folder_id)
        if folder_item is None:
            return None
        return folder_item.label

    def _create_event_system(self):
        return QueuedEventSystem()
