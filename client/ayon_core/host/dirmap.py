"""Dirmap functionality used in host integrations inside DCCs.

Idea for current dirmap implementation was used from Maya where is possible to
enter source and destination roots and maya will try each found source
in referenced file replace with each destination paths. First path which
exists is used.
"""

import os
from abc import ABCMeta, abstractmethod
import platform

import six

from ayon_core.lib import Logger
from ayon_core.addon import AddonsManager
from ayon_core.settings import get_project_settings
from ayon_core.settings.lib import get_site_local_overrides


@six.add_metaclass(ABCMeta)
class HostDirmap(object):
    """Abstract class for running dirmap on a workfile in a host.

    Dirmap is used to translate paths inside of host workfile from one
    OS to another. (Eg. arstist created workfile on Win, different artists
    opens same file on Linux.)

    Expects methods to be implemented inside of host:
        on_dirmap_enabled: run host code for enabling dirmap
        do_dirmap: run host code to do actual remapping
    """

    def __init__(
        self,
        host_name,
        project_name,
        project_settings=None,
        sitesync_addon=None
    ):
        self.host_name = host_name
        self.project_name = project_name
        self._project_settings = project_settings
        self._sitesync_addon = sitesync_addon
        # to limit reinit of Modules
        self._sitesync_addon_discovered = sitesync_addon is not None
        self._log = None

    @property
    def sitesync_addon(self):
        if not self._sitesync_addon_discovered:
            self._sitesync_addon_discovered = True
            manager = AddonsManager()
            self._sitesync_addon = manager.get("sitesync")
        return self._sitesync_addon

    @property
    def project_settings(self):
        if self._project_settings is None:
            self._project_settings = get_project_settings(self.project_name)
        return self._project_settings

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @abstractmethod
    def on_enable_dirmap(self):
        """Run host dependent operation for enabling dirmap if necessary."""
        pass

    @abstractmethod
    def dirmap_routine(self, source_path, destination_path):
        """Run host dependent remapping from source_path to destination_path"""
        pass

    def process_dirmap(self, mapping=None):
        # type: (dict) -> None
        """Go through all paths in Settings and set them using `dirmap`.

            If artists has Site Sync enabled, take dirmap mapping directly from
            Local Settings when artist is syncing workfile locally.

        """

        if not mapping:
            mapping = self.get_mappings()
        if not mapping:
            return

        self.on_enable_dirmap()

        for k, sp in enumerate(mapping["source_path"]):
            dst = mapping["destination_path"][k]
            try:
                # add trailing slash if missing
                sp = os.path.join(sp, '')
                dst = os.path.join(dst, '')
                print("{} -> {}".format(sp, dst))
                self.dirmap_routine(sp, dst)
            except IndexError:
                # missing corresponding destination path
                self.log.error((
                    "invalid dirmap mapping, missing corresponding"
                    " destination directory."
                ))
                break
            except RuntimeError:
                self.log.error(
                    "invalid path {} -> {}, mapping not registered".format(
                        sp, dst
                    )
                )
                continue

    def get_mappings(self):
        """Get translation from source_path to destination_path.

            It checks if Site Sync is enabled and user chose to use local
            site, in that case configuration in Local Settings takes precedence
        """

        dirmap_label = "{}-dirmap".format(self.host_name)
        mapping_sett = self.project_settings[self.host_name].get(dirmap_label,
                                                                 {})
        local_mapping = self._get_local_sync_dirmap()
        mapping_enabled = mapping_sett.get("enabled") or bool(local_mapping)
        if not mapping_enabled:
            return {}

        mapping = (
            local_mapping
            or mapping_sett["paths"]
            or {}
        )

        if (
            not mapping
            or not mapping.get("destination_path")
            or not mapping.get("source_path")
        ):
            return {}
        self.log.info("Processing directory mapping ...")
        self.log.info("mapping:: {}".format(mapping))
        return mapping

    def _get_local_sync_dirmap(self):
        """
            Returns dirmap if synch to local project is enabled.

            Only valid mapping is from roots of remote site to local site set
            in Local Settings.

            Returns:
                dict : { "source_path": [XXX], "destination_path": [YYYY]}
        """
        project_name = self.project_name

        sitesync_addon = self.sitesync_addon
        mapping = {}
        if (
            sitesync_addon is None
            or not sitesync_addon.enabled
            or project_name not in sitesync_addon.get_enabled_projects()
        ):
            return mapping

        active_site = sitesync_addon.get_local_normalized_site(
            sitesync_addon.get_active_site(project_name))
        remote_site = sitesync_addon.get_local_normalized_site(
            sitesync_addon.get_remote_site(project_name))
        self.log.debug(
            "active {} - remote {}".format(active_site, remote_site)
        )

        if active_site == "local" and active_site != remote_site:
            sync_settings = sitesync_addon.get_sync_project_setting(
                project_name,
                exclude_locals=False,
                cached=False)

            # TODO implement
            # Dirmap is dependent on 'get_site_local_overrides' which
            #   is not implemented in AYON. The mapping should be received
            #   from sitesync addon.
            active_overrides = get_site_local_overrides(
                project_name, active_site)
            remote_overrides = get_site_local_overrides(
                project_name, remote_site)

            self.log.debug("local overrides {}".format(active_overrides))
            self.log.debug("remote overrides {}".format(remote_overrides))

            current_platform = platform.system().lower()
            remote_provider = sitesync_addon.get_provider_for_site(
                project_name, remote_site
            )
            # dirmap has sense only with regular disk provider, in the workfile
            # won't be root on cloud or sftp provider
            if remote_provider != "local_drive":
                remote_site = "studio"
            for root_name, active_site_dir in active_overrides.items():
                remote_site_dir = (
                    remote_overrides.get(root_name)
                    or sync_settings["sites"][remote_site]["root"][root_name]
                )

                if isinstance(remote_site_dir, dict):
                    remote_site_dir = remote_site_dir.get(current_platform)

                if not remote_site_dir:
                    continue

                if os.path.isdir(active_site_dir):
                    if "destination_path" not in mapping:
                        mapping["destination_path"] = []
                    mapping["destination_path"].append(active_site_dir)

                    if "source_path" not in mapping:
                        mapping["source_path"] = []
                    mapping["source_path"].append(remote_site_dir)

            self.log.debug("local sync mapping:: {}".format(mapping))
        return mapping
