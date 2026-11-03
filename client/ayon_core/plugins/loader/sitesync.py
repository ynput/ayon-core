"""Site Sync actions to download, upload or remove local representations.

Todos:
    This should move to the Site Sync addon.

"""
from __future__ import annotations

from typing import Any, Optional

import ayon_api

from ayon_core.lib import NestedCacheItem
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    LoaderActionItem,
    LoaderActionPlugin,
    LoaderActionResult,
    LoaderActionSelection,
)

DOWNLOAD_ACTION = "download"
UPLOAD_ACTION = "upload"
REMOVE_ACTION = "remove"


class SiteSyncActionPlugin(LoaderActionPlugin):
    """Mark representations to be synced to the active or remote site."""

    identifier = "core.sitesync"

    def __init__(self, context) -> None:
        super().__init__(context)
        self._sitesync_addon = None
        self._addon_resolved = False
        # Active and remote site by project name, 'None' if disabled
        self._sites_cache = NestedCacheItem(levels=1, lifetime=60)

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        if not selection.representations_selected():
            return []

        project_name = selection.project_name
        sites = self._get_project_sites(project_name)
        if sites is None:
            return []
        active_site, remote_site = sites

        repre_ids = selection.selected_ids
        status_by_repre_id = (
            self._get_sitesync_addon().get_representations_sync_state(
                project_name, list(repre_ids), active_site, remote_site
            )
        )
        download_ids = set()
        local_ids = set()
        for repre_id in repre_ids:
            local_status, remote_status = status_by_repre_id.get(
                repre_id, (0, 0)
            )
            if local_status:
                local_ids.add(repre_id)
            if remote_status:
                download_ids.add(repre_id)

        output = []
        if download_ids:
            output.append(self._create_action_item(
                "Download", "download", DOWNLOAD_ACTION, download_ids
            ))
        if local_ids:
            output.append(self._create_action_item(
                "Upload", "upload", UPLOAD_ACTION, local_ids
            ))
            output.append(self._create_action_item(
                "Remove from local", "delete", REMOVE_ACTION, local_ids
            ))
        return output

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        project_name = selection.project_name
        sites = self._get_project_sites(project_name)
        if sites is None:
            return LoaderActionResult(
                message="Site Sync is not enabled for the project.",
                success=False,
            )
        active_site, remote_site = sites
        addon = self._get_sitesync_addon()

        action = data["action"]
        repre_ids = set(data["representation_ids"])
        if action == REMOVE_ACTION:
            for repre_id in repre_ids:
                addon.remove_site(
                    project_name,
                    repre_id,
                    active_site,
                    remove_local_files=True,
                )
            return LoaderActionResult(
                message=(
                    f"Removed {len(repre_ids)} representation(s)"
                    f" from '{active_site}'."
                )
            )

        site_name = active_site
        if action == UPLOAD_ACTION:
            site_name = remote_site

        repre_entities = selection.entities.get_representations(repre_ids)
        workfile_repre_ids = self._get_workfile_repre_ids(
            selection, repre_entities
        )
        for repre_entity in repre_entities:
            repre_id = repre_entity["id"]
            addon.add_site(project_name, repre_id, site_name, force=True)
            if repre_id in workfile_repre_ids:
                self._add_site_to_linked_representations(
                    project_name, repre_entity, site_name
                )

        verb = "download" if action == DOWNLOAD_ACTION else "upload"
        return LoaderActionResult(
            message=(
                f"Marked {len(repre_entities)} representation(s)"
                f" for {verb} to '{site_name}'."
            )
        )

    def _create_action_item(
        self,
        label: str,
        icon_name: str,
        action: str,
        repre_ids: set[str],
    ) -> LoaderActionItem:
        return LoaderActionItem(
            label=label,
            order=1,
            icon=MaterialSymbolsIcon(icon_name, color="#999999"),
            data={
                "action": action,
                "representation_ids": list(repre_ids),
            },
        )

    def _get_sitesync_addon(self):
        if not self._addon_resolved:
            self._addon_resolved = True
            addons_manager = self._context.get_addons_manager()
            addon = addons_manager.get("sitesync")
            if addon is not None and addon.enabled:
                self._sitesync_addon = addon
        return self._sitesync_addon

    def _get_project_sites(
        self, project_name: str
    ) -> Optional[tuple[str, str]]:
        """Active and remote site of a project.

        Returns:
            Optional[tuple[str, str]]: Active and remote site names, or
                'None' if Site Sync is not enabled for the project.

        """
        cache = self._sites_cache[project_name]
        if not cache.is_valid:
            sites = None
            addon = self._get_sitesync_addon()
            if (
                addon is not None
                and addon.is_project_enabled(project_name, single=True)
            ):
                sites = (
                    addon.get_active_site(project_name),
                    addon.get_remote_site(project_name),
                )
            cache.update_data(sites)
        return cache.get_data()

    def _get_workfile_repre_ids(
        self,
        selection: LoaderActionSelection,
        repre_entities: list[dict[str, Any]],
    ) -> set[str]:
        """Representation ids that belong to 'workfile' products."""
        version_ids = {
            repre_entity["versionId"] for repre_entity in repre_entities
        }
        versions = selection.entities.get_versions(version_ids)
        products = selection.entities.get_products({
            version["productId"] for version in versions
        })
        workfile_product_ids = {
            product["id"]
            for product in products
            if product["productType"] == "workfile"
        }
        workfile_version_ids = {
            version["id"]
            for version in versions
            if version["productId"] in workfile_product_ids
        }
        return {
            repre_entity["id"]
            for repre_entity in repre_entities
            if repre_entity["versionId"] in workfile_version_ids
        }

    def _add_site_to_linked_representations(
        self,
        project_name: str,
        repre_entity: dict[str, Any],
        site_name: str,
    ) -> None:
        """Sync representations referenced by a workfile too.

        Todos:
            This should happen in the Site Sync addon.

        """
        addon = self._get_sitesync_addon()
        for link_repre_id in self._get_linked_representation_ids(
            project_name, repre_entity["versionId"], "reference"
        ):
            if addon.is_representation_on_site(
                project_name, link_repre_id, site_name
            ):
                continue
            self.log.info(
                f"Adding {site_name} to linked representation:"
                f" {link_repre_id}"
            )
            addon.add_site(
                project_name, link_repre_id, site_name, force=True
            )

    def _get_linked_representation_ids(
        self,
        project_name: str,
        version_id: str,
        link_type: str,
    ) -> list[str]:
        """Ids of representations of versions linked as inputs."""
        versions_links = ayon_api.get_versions_links(
            project_name,
            {version_id},
            link_types=[link_type],
            link_direction="in",
        )
        linked_version_ids = {
            link["entityId"]
            for links in versions_links.values()
            for link in links
            if link["entityType"] == "version"
        }
        linked_version_ids.discard(version_id)
        if not linked_version_ids:
            return []
        return [
            repre["id"]
            for repre in ayon_api.get_representations(
                project_name,
                version_ids=linked_version_ids,
                fields={"id"},
            )
        ]
