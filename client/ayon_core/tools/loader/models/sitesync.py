from __future__ import annotations

import collections

from ayon_api import (
    get_representations,
    get_versions_links,
)

from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.addon import AddonsManager
from ayon_core.tools.loader.abstract import ActionItem

DOWNLOAD_IDENTIFIER = "sitesync.download"
UPLOAD_IDENTIFIER = "sitesync.upload"
REMOVE_IDENTIFIER = "sitesync.remove"

log = Logger.get_logger(__name__)


def _default_version_availability():
    return 0, 0


def _default_repre_status():
    return 0.0, 0.0


class SiteSyncModel:
    """Model handling site sync logic.

    Model cares about handling of site sync functionality. All public
    functions should be possible to call even if site sync is not available.
    """

    lifetime = 60  # In seconds (minute by default)
    status_lifetime = 20

    def __init__(self, controller):
        self._controller = controller

        self._site_icons = None
        self._sitesync_enabled_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._active_site_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._remote_site_cache = NestedCacheItem(
            levels=1, lifetime=self.lifetime
        )
        self._version_availability_cache = NestedCacheItem(
            levels=2,
            default_factory=_default_version_availability,
            lifetime=self.status_lifetime
        )
        self._repre_status_cache = NestedCacheItem(
            levels=2,
            default_factory=_default_repre_status,
            lifetime=self.status_lifetime
        )

        manager = AddonsManager()
        self._sitesync_addon = manager.get("sitesync")

    def reset(self):
        self._site_icons = None
        self._sitesync_enabled_cache.reset()
        self._active_site_cache.reset()
        self._remote_site_cache.reset()
        self._version_availability_cache.reset()
        self._repre_status_cache.reset()

    def is_sitesync_enabled(self, project_name=None):
        """Site sync is enabled for a project.

        Returns false if site sync addon is not available or enabled
            or project has disabled it.

        Args:
            project_name (Union[str, None]): Project name. If project name
                is 'None', True is returned if site sync addon
                is available and enabled.

        Returns:
            bool: Site sync is enabled.
        """

        if not self._is_sitesync_addon_enabled():
            return False
        cache = self._sitesync_enabled_cache[project_name]
        if not cache.is_valid:
            enabled = True
            if project_name:
                enabled = self._sitesync_addon.is_project_enabled(
                    project_name, single=True
                )
            cache.update_data(enabled)
        return cache.get_data()

    def get_active_site(self, project_name):
        """Active site name for a project.

        Args:
            project_name (str): Project name.

        Returns:
            Union[str, None]: Remote site name.
        """

        cache = self._active_site_cache[project_name]
        if not cache.is_valid:
            site_name = None
            if project_name and self._is_sitesync_addon_enabled():
                site_name = self._sitesync_addon.get_active_site(project_name)
            cache.update_data(site_name)
        return cache.get_data()

    def get_remote_site(self, project_name):
        """Remote site name for a project.

        Args:
            project_name (str): Project name.

        Returns:
            Union[str, None]: Remote site name.
        """

        cache = self._remote_site_cache[project_name]
        if not cache.is_valid:
            site_name = None
            if project_name and self._is_sitesync_addon_enabled():
                site_name = self._sitesync_addon.get_remote_site(project_name)
            cache.update_data(site_name)
        return cache.get_data()

    def get_active_site_icon_def(self, project_name):
        """Active site icon definition.

        Args:
            project_name (Union[str, None]): Name of project.

        Returns:
            Union[dict[str, Any], None]: Site icon definition.
        """

        if not project_name or not self.is_sitesync_enabled(project_name):
            return None
        active_site = self.get_active_site(project_name)
        return self._get_site_icon_def(project_name, active_site)

    def get_remote_site_icon_def(self, project_name):
        """Remote site icon definition.

        Args:
            project_name (Union[str, None]): Name of project.

        Returns:
            Union[dict[str, Any], None]: Site icon definition.
        """

        if not project_name or not self.is_sitesync_enabled(project_name):
            return None
        remote_site = self.get_remote_site(project_name)
        return self._get_site_icon_def(project_name, remote_site)

    def _get_site_icon_def(self, project_name, site_name):
        # use different icon for studio even if provider is 'local_drive'
        if site_name == self._sitesync_addon.DEFAULT_SITE:
            provider = "studio"
        else:
            provider = self._get_provider_for_site(project_name, site_name)
        return self._get_provider_icon(provider)

    def get_version_sync_availability(self, project_name, version_ids):
        """Returns how many representations are available on sites.

        Returned value `{version_id: (4, 6)}` denotes that locally are
            available 4 and remotely 6 representation.
        NOTE: Available means they were synced to site.

        Returns:
            dict[str, tuple[int, int]]
        """

        if not self.is_sitesync_enabled(project_name):
            return {
                version_id: _default_version_availability()
                for version_id in version_ids
            }

        output = {}
        project_cache = self._version_availability_cache[project_name]
        invalid_ids = set()
        for version_id in version_ids:
            repre_cache = project_cache[version_id]
            if repre_cache.is_valid:
                output[version_id] = repre_cache.get_data()
            else:
                invalid_ids.add(version_id)

        if invalid_ids:
            self._refresh_version_availability(
                project_name, invalid_ids
            )
            for version_id in invalid_ids:
                version_cache = project_cache[version_id]
                output[version_id] = version_cache.get_data()
        return output

    def get_representations_sync_status(
        self, project_name, representation_ids
    ):
        """

        Args:
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.

        Returns:
            dict[str, tuple[float, float]]
        """

        if not self.is_sitesync_enabled(project_name):
            return {
                repre_id: _default_repre_status()
                for repre_id in representation_ids
            }

        output = {}
        project_cache = self._repre_status_cache[project_name]
        invalid_ids = set()
        for repre_id in representation_ids:
            repre_cache = project_cache[repre_id]
            if repre_cache.is_valid:
                output[repre_id] = repre_cache.get_data()
            else:
                invalid_ids.add(repre_id)

        if invalid_ids:
            self._refresh_representations_sync_status(
                project_name, invalid_ids
            )
            for repre_id in invalid_ids:
                repre_cache = project_cache[repre_id]
                output[repre_id] = repre_cache.get_data()
        return output

    def get_sitesync_action_items(
        self, project_name, entity_ids, entity_type
    ):
        """

        Args:
             project_name (str): Project name.
             entity_ids (set[str]): Selected entity ids.
             entity_type (str): Selected entity type.

        Returns:
            list[ActionItem]: Actions that can be shown in loader.

        """
        if entity_type != "representation":
            return []

        if not self.is_sitesync_enabled(project_name):
            return []

        repres_status = self.get_representations_sync_status(
            project_name, entity_ids
        )

        repre_ids_per_identifier = collections.defaultdict(set)
        for repre_id in entity_ids:
            repre_status = repres_status[repre_id]
            local_status, remote_status = repre_status

            if local_status:
                repre_ids_per_identifier[UPLOAD_IDENTIFIER].add(repre_id)
                repre_ids_per_identifier[REMOVE_IDENTIFIER].add(repre_id)

            if remote_status:
                repre_ids_per_identifier[DOWNLOAD_IDENTIFIER].add(repre_id)

        action_items = []
        for identifier, repre_ids in repre_ids_per_identifier.items():
            if identifier == DOWNLOAD_IDENTIFIER:
                action_items.append(self._create_download_action_item(
                    project_name, repre_ids
                ))
            elif identifier == UPLOAD_IDENTIFIER:
                action_items.append(self._create_upload_action_item(
                    project_name, repre_ids
                ))
            elif identifier == REMOVE_IDENTIFIER:
                action_items.append(self._create_delete_action_item(
                    project_name, repre_ids
                ))

        return action_items

    def is_sitesync_action(self, plugin_identifier: str) -> bool:
        """Should be `identifier` handled by SiteSync.

        Args:
            plugin_identifier (str): Plugin identifier.

        Returns:
            bool: Should action be handled by SiteSync.

        """
        return plugin_identifier == "sitesync.loader.action"

    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        representation_ids: set[str],
    ):
        """Resets status for site_name or remove local files.

        Args:
            identifier (str): Action identifier.
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.

        """
        active_site = self.get_active_site(project_name)
        remote_site = self.get_remote_site(project_name)

        repre_entities_by_id = {
            repre_entity["id"]: repre_entity
            for repre_entity in get_representations(
                project_name, representation_ids=representation_ids
            )
        }
        # TODO get product type from product entity instead of 'context'
        #   on representation
        product_type_by_repre_id = {}
        for repre_id, repre_entity in repre_entities_by_id.items():
            repre_context = repre_entity["context"]
            product_type = repre_context.get("product", {}).get("type")
            if not product_type:
                product_type = repre_context.get("family")

            product_type_by_repre_id[repre_id] = product_type

        for repre_id in representation_ids:
            repre_entity = repre_entities_by_id.get(repre_id)
            product_type = product_type_by_repre_id[repre_id]
            if identifier == DOWNLOAD_IDENTIFIER:
                self._add_site(
                    project_name, repre_entity, active_site, product_type
                )

            elif identifier == UPLOAD_IDENTIFIER:
                self._add_site(
                    project_name, repre_entity, remote_site, product_type
                )

            elif identifier == REMOVE_IDENTIFIER:
                self._sitesync_addon.remove_site(
                    project_name,
                    repre_id,
                    active_site,
                    remove_local_files=True
                )

    def _is_sitesync_addon_enabled(self):
        """
        Returns:
            bool: Site sync addon is enabled.
        """

        if self._sitesync_addon is None:
            return False
        return self._sitesync_addon.enabled

    def _get_provider_for_site(self, project_name, site_name):
        """Provider for a site.

        Args:
            project_name (str): Project name.
            site_name (str): Site name.

        Returns:
            Union[str, None]: Provider name.
        """

        if not self._is_sitesync_addon_enabled():
            return None
        return self._sitesync_addon.get_provider_for_site(
            project_name, site_name
        )

    def _get_provider_icon(self, provider):
        """site provider icons.

        Returns:
            Union[dict[str, Any], None]: Icon of site provider.
        """

        if not provider:
            return None

        if self._site_icons is None:
            self._site_icons = self._sitesync_addon.get_site_icons()
        return self._site_icons.get(provider)

    def _refresh_version_availability(self, project_name, version_ids):
        if not project_name or not version_ids:
            return
        project_cache = self._version_availability_cache[project_name]

        avail_by_id = self._sitesync_addon.get_version_availability(
            project_name,
            version_ids,
            self.get_active_site(project_name),
            self.get_remote_site(project_name),
        )
        for version_id in version_ids:
            status = avail_by_id.get(version_id)
            if status is None:
                status = _default_version_availability()
            project_cache[version_id].update_data(status)

    def _refresh_representations_sync_status(
        self, project_name, representation_ids
    ):
        if not project_name or not representation_ids:
            return
        project_cache = self._repre_status_cache[project_name]
        status_by_repre_id = (
            self._sitesync_addon.get_representations_sync_state(
                project_name,
                representation_ids,
                self.get_active_site(project_name),
                self.get_remote_site(project_name),
            )
        )
        for repre_id in representation_ids:
            status = status_by_repre_id.get(repre_id)
            if status is None:
                status = _default_repre_status()
            project_cache[repre_id].update_data(status)

    def _create_download_action_item(self, project_name, representation_ids):
        return self._create_action_item(
            project_name,
            representation_ids,
            DOWNLOAD_IDENTIFIER,
            "Download",
            "Mark representation for download locally",
            "fa.download"
        )

    def _create_upload_action_item(self, project_name, representation_ids):
        return self._create_action_item(
            project_name,
            representation_ids,
            UPLOAD_IDENTIFIER,
            "Upload",
            "Mark representation for upload remotely",
            "fa.upload"
        )

    def _create_delete_action_item(self, project_name, representation_ids):
        return self._create_action_item(
            project_name,
            representation_ids,
            REMOVE_IDENTIFIER,
            "Remove from local",
            "Remove local synchronization",
            "fa.trash"
        )

    def _create_action_item(
        self,
        project_name,
        representation_ids,
        identifier,
        label,
        tooltip,
        icon_name
    ):
        return ActionItem(
            "sitesync.loader.action",
            identifier=identifier,
            label=label,
            icon={
                "type": "awesome-font",
                "name": icon_name,
                "color": "#999999"
            },
            tooltip=tooltip,
            options={},
            order=1,
            entity_ids=representation_ids,
            entity_type="representation",
        )

    def _add_site(self, project_name, repre_entity, site_name, product_type):
        self._sitesync_addon.add_site(
            project_name, repre_entity["id"], site_name, force=True
        )

        # TODO this should happen in site sync addon
        if product_type != "workfile":
            return

        links = self._get_linked_representation_id(
            project_name,
            repre_entity,
            "reference"
        )
        for link_repre_id in links:
            if not self._sitesync_addon.is_representation_on_site(
                project_name,
                link_repre_id,
                site_name
            ):
                print("Adding {} to linked representation: {}".format(
                    site_name, link_repre_id))
                self._sitesync_addon.add_site(
                    project_name,
                    link_repre_id,
                    site_name,
                    force=True
                )

    def _get_linked_representation_id(
        self,
        project_name,
        repre_entity,
        link_type,
        max_depth=None
    ):
        """Returns list of linked ids of particular type (if provided).

        One of representation document or representation id must be passed.
        Note:
            Representation links now works only from representation through
                version back to representations.

        Todos:
            Missing depth query. Not sure how it did find more representations
                in depth, probably links to version?
            This function should probably live in sitesync addon?

        Args:
            project_name (str): Name of project where look for links.
            repre_entity (dict[str, Any]): Representation entity.
            link_type (str): Type of link (e.g. 'reference', ...).
            max_depth (int): Limit recursion level. Default: 0

        Returns:
            List[ObjectId] Linked representation ids.
        """

        if not repre_entity:
            return []

        version_id = repre_entity["versionId"]
        if max_depth is None or max_depth == 0:
            max_depth = 1

        link_types = None
        if link_type:
            link_types = [link_type]

        # Store already found version ids to avoid recursion, and also to store
        #   output -> Don't forget to remove 'version_id' at the end!!!
        linked_version_ids = {version_id}
        # Each loop of depth will reset this variable
        versions_to_check = {version_id}
        for _ in range(max_depth):
            if not versions_to_check:
                break

            versions_links = get_versions_links(
                project_name,
                versions_to_check,
                link_types=link_types,
                link_direction="in")  # looking for 'in'puts for version

            versions_to_check = set()
            for links in versions_links.values():
                for link in links:
                    # Care only about version links
                    if link["entityType"] != "version":
                        continue
                    entity_id = link["entityId"]
                    linked_version_ids.add(entity_id)
                    versions_to_check.add(entity_id)

        linked_version_ids.remove(version_id)
        if not linked_version_ids:
            return []
        representations = get_representations(
            project_name,
            version_ids=linked_version_ids,
            fields=["id"])
        return [
            repre["id"]
            for repre in representations
        ]
