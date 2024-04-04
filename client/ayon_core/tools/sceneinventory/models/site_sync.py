import ayon_api

from ayon_core.addon import AddonsManager

NOT_SET = object()


class SiteSyncModel:
    def __init__(self, controller):
        self._controller = controller

        self._sitesync_addon = NOT_SET
        self._sitesync_enabled = None
        self._active_site = NOT_SET
        self._remote_site = NOT_SET
        self._active_site_provider = NOT_SET
        self._remote_site_provider = NOT_SET

    def reset(self):
        self._sitesync_addon = NOT_SET
        self._sitesync_enabled = None
        self._active_site = NOT_SET
        self._remote_site = NOT_SET
        self._active_site_provider = NOT_SET
        self._remote_site_provider = NOT_SET

    def is_sitesync_enabled(self):
        """Site sync is enabled.

        Returns:
            bool: Is enabled or not.
        """

        self._cache_sitesync_addon()
        return self._sitesync_enabled

    def get_site_provider_icons(self):
        """Icon paths per provider.

        Returns:
            dict[str, str]: Path by provider name.
        """

        if not self.is_sitesync_enabled():
            return {}
        site_sync_addon = self._get_sitesync_addon()
        return site_sync_addon.get_site_icons()

    def get_sites_information(self):
        return {
            "active_site": self._get_active_site(),
            "active_site_provider": self._get_active_site_provider(),
            "remote_site": self._get_remote_site(),
            "remote_site_provider": self._get_remote_site_provider()
        }

    def get_representations_site_progress(self, representation_ids):
        """Get progress of representations sync."""

        representation_ids = set(representation_ids)
        output = {
            repre_id: {
                "active_site": 0,
                "remote_site": 0,
            }
            for repre_id in representation_ids
        }
        if not self.is_sitesync_enabled():
            return output

        project_name = self._controller.get_current_project_name()
        site_sync = self._get_sitesync_addon()
        repre_entities = ayon_api.get_representations(
            project_name, representation_ids
        )
        active_site = self._get_active_site()
        remote_site = self._get_remote_site()

        for repre_entity in repre_entities:
            repre_output = output[repre_entity["id"]]
            result = site_sync.get_progress_for_repre(
                repre_entity, active_site, remote_site
            )
            repre_output["active_site"] = result[active_site]
            repre_output["remote_site"] = result[remote_site]

        return output

    def resync_representations(self, representation_ids, site_type):
        """

        Args:
            representation_ids (Iterable[str]): Representation ids.
            site_type (Literal[active_site, remote_site]): Site type.
        """

        project_name = self._controller.get_current_project_name()
        site_sync = self._get_sitesync_addon()
        active_site = self._get_active_site()
        remote_site = self._get_remote_site()
        progress = self.get_representations_site_progress(
            representation_ids
        )
        for repre_id in representation_ids:
            repre_progress = progress.get(repre_id)
            if not repre_progress:
                continue

            if site_type == "active_site":
                # check opposite from added site, must be 1 or unable to sync
                check_progress = repre_progress["remote_site"]
                site = active_site
            else:
                check_progress = repre_progress["active_site"]
                site = remote_site

            if check_progress == 1:
                site_sync.add_site(
                    project_name, repre_id, site, force=True
                )

    def _get_sitesync_addon(self):
        self._cache_sitesync_addon()
        return self._sitesync_addon

    def _cache_sitesync_addon(self):
        if self._sitesync_addon is not NOT_SET:
            return self._sitesync_addon
        manager = AddonsManager()
        site_sync = manager.get("sitesync")
        sync_enabled = site_sync is not None and site_sync.enabled
        self._sitesync_addon = site_sync
        self._sitesync_enabled = sync_enabled

    def _get_active_site(self):
        if self._active_site is NOT_SET:
            self._cache_sites()
        return self._active_site

    def _get_remote_site(self):
        if self._remote_site is NOT_SET:
            self._cache_sites()
        return self._remote_site

    def _get_active_site_provider(self):
        if self._active_site_provider is NOT_SET:
            self._cache_sites()
        return self._active_site_provider

    def _get_remote_site_provider(self):
        if self._remote_site_provider is NOT_SET:
            self._cache_sites()
        return self._remote_site_provider

    def _cache_sites(self):
        active_site = None
        remote_site = None
        active_site_provider = None
        remote_site_provider = None
        if self.is_sitesync_enabled():
            site_sync = self._get_sitesync_addon()
            project_name = self._controller.get_current_project_name()
            active_site = site_sync.get_active_site(project_name)
            remote_site = site_sync.get_remote_site(project_name)
            active_site_provider = "studio"
            remote_site_provider = "studio"
            if active_site != "studio":
                active_site_provider = site_sync.get_provider_for_site(
                    project_name, active_site
                )
            if remote_site != "studio":
                remote_site_provider = site_sync.get_provider_for_site(
                    project_name, remote_site
                )

        self._active_site = active_site
        self._remote_site = remote_site
        self._active_site_provider = active_site_provider
        self._remote_site_provider = remote_site_provider
