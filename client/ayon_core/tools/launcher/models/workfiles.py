import os
from typing import Optional, Any

import ayon_api

from ayon_core.lib import (
    Logger,
    NestedCacheItem,
)
from ayon_core.pipeline import Anatomy
from ayon_core.tools.launcher.abstract import (
    WorkfileItem,
    AbstractLauncherBackend,
)


class WorkfilesModel:
    def __init__(self, controller: AbstractLauncherBackend):
        self._controller = controller

        self._log = Logger.get_logger(self.__class__.__name__)

        self._host_icons = None
        self._workfile_items = NestedCacheItem(
            levels=2, default_factory=list, lifetime=60,
        )

    def reset(self) -> None:
        self._workfile_items.reset()

    def get_workfile_items(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        if not project_name or not task_id:
            return []

        cache = self._workfile_items[project_name][task_id]
        if cache.is_valid:
            return cache.get_data()

        project_entity = self._controller.get_project_entity(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)
        items = []
        for workfile_entity in ayon_api.get_workfiles_info(
            project_name, task_ids={task_id}, fields={"id", "path", "data"}
        ):
            rootless_path = workfile_entity["path"]
            exists = False
            try:
                path = anatomy.fill_root(rootless_path)
                exists = os.path.exists(path)
            except Exception:
                self._log.warning(
                    "Failed to fill root for workfile path",
                    exc_info=True,
                )
            workfile_data = workfile_entity["data"]
            host_name = workfile_data.get("host_name")
            version = workfile_data.get("version")

            items.append(WorkfileItem(
                workfile_id=workfile_entity["id"],
                filename=os.path.basename(rootless_path),
                exists=exists,
                icon=self._get_host_icon(host_name),
                version=version,
            ))
        cache.update_data(items)
        return items

    def _get_host_icon(
        self, host_name: Optional[str]
    ) -> Optional[dict[str, Any]]:
        if self._host_icons is None:
            host_icons = {}
            try:
                host_icons = self._get_host_icons()
            except Exception:
                self._log.warning(
                    "Failed to get host icons",
                    exc_info=True,
                )
            self._host_icons = host_icons
        return self._host_icons.get(host_name)

    def _get_host_icons(self) -> dict[str, Any]:
        addons_manager = self._controller.get_addons_manager()
        applications_addon = addons_manager["applications"]
        apps_manager = applications_addon.get_applications_manager()
        output = {}
        for app_group in apps_manager.app_groups.values():
            host_name = app_group.host_name
            icon_filename = app_group.icon
            if not host_name or not icon_filename:
                continue
            icon_url = applications_addon.get_app_icon_url(
                icon_filename, server=True
            )
            output[host_name] = icon_url
        return output
