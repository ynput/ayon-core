import ayon_api

from ayon_core.addon import AddonsManager

NOT_SET = object()


class SiteSyncModel:
    def __init__(self, controller):
        self._controller = controller

        self._sitesync_addon = NOT_SET
        self._sitesync_enabled = None
        self._active_site = {}
        self._remote_site = {}
        self._active_site_provider = {}
        self._remote_site_provider = {}

    def reset(self):
        self._sitesync_addon = NOT_SET
        self._sitesync_enabled = None
        self._active_site = {}
        self._remote_site = {}
        self._active_site_provider = {}
        self._remote_site_provider = {}

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
        sitesync_addon = self._get_sitesync_addon()
        return sitesync_addon.get_site_icons()

    def get_sites_information(self, project_name):
        return {
            "active_site": self._get_active_site(project_name),
            "remote_site": self._get_remote_site(project_name),
            "active_site_provider": self._get_active_site_provider(
                project_name
            ),
            "remote_site_provider": self._get_remote_site_provider(
                project_name
            )
        }

    def get_representations_site_progress(
        self, project_name, representation_ids
    ):
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

        sitesync_addon = self._get_sitesync_addon()
        repre_entities = ayon_api.get_representations(
            project_name, representation_ids
        )
        active_site = self._get_active_site(project_name)
        remote_site = self._get_remote_site(project_name)

        for repre_entity in repre_entities:
            repre_output = output[repre_entity["id"]]
            result = sitesync_addon.get_progress_for_repre(
                repre_entity, active_site, remote_site
            )
            repre_output["active_site"] = result[active_site]
            repre_output["remote_site"] = result[remote_site]

        return output

    def resync_representations(
        self, project_name, representation_ids, site_type
    ):
        """

        Args:
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.
            site_type (Literal[active_site, remote_site]): Site type.
        """
        sitesync_addon = self._get_sitesync_addon()
        active_site = self._get_active_site(project_name)
        remote_site = self._get_remote_site(project_name)
        progress = self.get_representations_site_progress(
            project_name, representation_ids
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
                sitesync_addon.add_site(
                    project_name, repre_id, site, force=True
                )

    def _get_sitesync_addon(self):
        self._cache_sitesync_addon()
        return self._sitesync_addon

    def _cache_sitesync_addon(self):
        if self._sitesync_addon is not NOT_SET:
            return self._sitesync_addon
        manager = AddonsManager()
        sitesync_addon = manager.get("sitesync")
        sync_enabled = sitesync_addon is not None and sitesync_addon.enabled
        self._sitesync_addon = sitesync_addon
        self._sitesync_enabled = sync_enabled

    def _get_active_site(self, project_name):
        if project_name not in self._active_site:
            self._cache_sites(project_name)
        return self._active_site[project_name]

    def _get_remote_site(self, project_name):
        if project_name not in self._remote_site:
            self._cache_sites(project_name)
        return self._remote_site[project_name]

    def _get_active_site_provider(self, project_name):
        if project_name not in self._active_site_provider:
            self._cache_sites(project_name)
        return self._active_site_provider[project_name]

    def _get_remote_site_provider(self, project_name):
        if project_name not in self._remote_site_provider:
            self._cache_sites(project_name)
        return self._remote_site_provider[project_name]

    def _cache_sites(self, project_name):
        self._active_site[project_name] = None
        self._remote_site[project_name] = None
        self._active_site_provider[project_name] = None
        self._remote_site_provider[project_name] = None
        if not self.is_sitesync_enabled():
            return

        sitesync_addon = self._get_sitesync_addon()
        active_site = sitesync_addon.get_active_site(project_name)
        remote_site = sitesync_addon.get_remote_site(project_name)
        active_site_provider = "studio"
        remote_site_provider = "studio"
        if active_site != "studio":
            active_site_provider = sitesync_addon.get_provider_for_site(
                project_name, active_site
            )
        if remote_site != "studio":
            remote_site_provider = sitesync_addon.get_provider_for_site(
                project_name, remote_site
            )

        self._active_site[project_name] = active_site
        self._remote_site[project_name] = remote_site
        self._active_site_provider[project_name] = active_site_provider
        self._remote_site_provider[project_name] = remote_site_provider
