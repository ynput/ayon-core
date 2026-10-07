from typing import Optional

import ayon_api

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.host import ILoadHost
from ayon_core.pipeline import (
    registered_host,
    get_current_context,
)
from ayon_core.tools.common_models import (
    ActivitiesModel,
    HierarchyModel,
    ProjectsModel,
    ProductTypeIconMapping,
    ThumbnailsModel,
    UsersModel,
)

from .models import (
    SiteSyncModel,
    ContainersModel,
    VersionHistoryModel,
)


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
        self._version_history_model = VersionHistoryModel(self)
        self._activities_model = ActivitiesModel()
        self._users_model = UsersModel(self)
        self._thumbnails_model = ThumbnailsModel()
        # Switch dialog requirements
        self._hierarchy_model = HierarchyModel(self)
        self._projects_model = ProjectsModel(self)
        self._event_system = self._create_event_system()

    def get_window_subtitle(self) -> Optional[str]:
        if self._host is None:
            return None
        return self._host.name

    def get_host(self) -> ILoadHost:
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
        self._version_history_model.reset()
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

    def get_project_status_items(self, project_name=None):
        if project_name is None:
            project_name = self.get_current_project_name()
        return self._projects_model.get_project_status_items(
            project_name, None
        )

    def get_product_type_icons_mapping(
        self, project_name: Optional[str]
    ) -> ProductTypeIconMapping:
        return self._projects_model.get_product_type_icons_mapping(
            project_name
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

    def get_representation_info_items(self, project_name, representation_ids):
        return self._containers_model.get_representation_info_items(
            project_name, representation_ids
        )

    def get_version_items(self, project_name, product_ids):
        return self._containers_model.get_version_items(
            project_name, product_ids)

    # Version history methods
    def get_version_history_contexts(self, item_ids):
        """Products of containers with versions that are loaded.

        Args:
            item_ids (Iterable[str]): Ids of container items.

        Returns:
            list[VersionHistoryContext]: Contexts of valid containers.

        """
        return self._version_history_model.get_contexts(item_ids)

    def get_version_history_items(self, project_name, product_id):
        """Versions of a product, from the newest to the oldest.

        Args:
            project_name (str): Project name.
            product_id (str): Product id.

        Returns:
            list[VersionHistoryItem]: Versions of the product.

        """
        return self._version_history_model.get_items(
            project_name, product_id
        )

    def get_version_thumbnail_path(
        self, project_name, version_id, thumbnail_id
    ):
        """Path to a file with the thumbnail of a version.

        Args:
            project_name (str): Project name.
            version_id (str): Version id.
            thumbnail_id (str): Id of the version thumbnail.

        Returns:
            Optional[str]: Path to the image, None if there is none.

        """
        return self._thumbnails_model.get_thumbnail_path(
            project_name, "version", version_id, thumbnail_id
        )

    # Activity methods
    def get_activity_items(self, project_name, entity_ids, limit=50):
        """Latest activities of entities, e.g. of a version.

        Args:
            project_name (str): Project name.
            entity_ids (Union[list[str], set[str]]): Ids of entities.
            limit (int): Maximum number of activities.

        Returns:
            list[ActivityItem]: Activities from the newest to the oldest.

        """
        return self._activities_model.get_activity_items(
            project_name, entity_ids, limit
        )

    def get_user_items(self, project_name):
        """Users of a project.

        Args:
            project_name (Optional[str]): Project name.

        Returns:
            list[UserItem]: User items.

        """
        return self._users_model.get_user_items(project_name)

    def get_user_avatar_path(self, username):
        """Path to the avatar image of a user.

        Args:
            username (str): Name of the user.

        Returns:
            Optional[str]: Path to the image, None if the user has no
                avatar.

        """
        return self._users_model.get_user_avatar_path(username)

    # Site Sync methods
    def is_sitesync_enabled(self):
        return self._sitesync_model.is_sitesync_enabled()

    def get_sites_information(self, project_name):
        return self._sitesync_model.get_sites_information(project_name)

    def get_site_provider_icons(self):
        return self._sitesync_model.get_site_provider_icons()

    def get_representations_site_progress(
        self, project_name, representation_ids
    ):
        return self._sitesync_model.get_representations_site_progress(
            project_name, representation_ids
        )

    def resync_representations(
        self, project_name, representation_ids, site_type
    ):
        return self._sitesync_model.resync_representations(
            project_name,
            representation_ids,
            site_type
        )

    # Switch dialog methods
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def get_folder_label(self, project_name, folder_id):
        if not folder_id:
            return None
        folder_item = self._hierarchy_model.get_folder_item(
            project_name, folder_id)
        if folder_item is None:
            return None
        return folder_item.label

    def _create_event_system(self):
        return QueuedEventSystem()
