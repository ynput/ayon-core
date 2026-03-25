from pathlib import Path
from typing import Optional, Any

import ayon_api

from ayon_core.addon import IHostAddon
from ayon_core.lib import (
    Logger,
    NestedCacheItem,
)
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.tools.launcher.abstract import (
    WorkfileItem,
    AbstractLauncherBackend,
)


class WorkfilesModel:
    """Model collecting launcher workfiles for the current context."""

    def __init__(self, controller: AbstractLauncherBackend) -> None:
        self._controller = controller

        self._log = Logger.get_logger(self.__class__.__name__)

        self._host_icons: Optional[dict[str, str]] = None
        self._workfile_extensions: Optional[set[str]] = None
        self._extension_to_host_name: Optional[dict[str, str]] = None
        self._workfile_items = NestedCacheItem(
            levels=2, default_factory=list, lifetime=60,
        )
        self._published_workfile_items = NestedCacheItem(
            levels=3, default_factory=list, lifetime=60,
        )

    def reset(self) -> None:
        """Reset cached workfile and host-extension mappings."""
        self._workfile_items.reset()
        self._published_workfile_items.reset()
        self._extension_to_host_name = None

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
                exists = Path(path).exists()
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
                filename=Path(rootless_path).name,
                exists=exists,
                icon=self._get_host_icon(host_name),
                version=version,
            ))
        cache.update_data(items)
        return items

    def get_published_workfile_items(
        self,
        project_name: Optional[str],
        folder_id: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        if not project_name or not folder_id or not task_id:
            return []

        cache = self._published_workfile_items[project_name][folder_id][
            task_id
        ]
        if cache.is_valid:
            items = cache.get_data()
        else:
            project_entity = self._controller.get_project_entity(project_name)
            anatomy = Anatomy(project_name, project_entity=project_entity)
            items = []

            product_ids = {
                product_entity["id"]
                for product_entity in ayon_api.get_products(
                    project_name,
                    folder_ids={folder_id},
                    product_types={"workfile"},
                    fields={"id"},
                )
            }
            if product_ids:
                version_entities = list(
                    ayon_api.get_versions(
                        project_name,
                        product_ids=product_ids,
                        fields={"id", "version", "taskId"},
                    )
                )
                version_ids = {
                    version_entity["id"] for version_entity in version_entities
                }
                version_by_id = {
                    version_entity["id"]: version_entity
                    for version_entity in version_entities
                }
                if version_ids:
                    for repre_entity in ayon_api.get_representations(
                        project_name,
                        version_ids=version_ids,
                        fields={
                            "id",
                            "versionId",
                            "attrib",
                            "context",
                            "files",
                        },
                    ):
                        version_entity = version_by_id.get(
                            repre_entity["versionId"]
                        )
                        if version_entity is None:
                            continue
                        if task_id and version_entity.get("taskId") != task_id:
                            continue
                        if not self._is_supported_workfile_representation(
                            repre_entity
                        ):
                            continue
                        try:
                            path = get_representation_path_with_anatomy(
                                repre_entity, anatomy
                            )
                        except Exception:
                            self._log.warning(
                                "Failed to get published workfile path",
                                exc_info=True,
                            )
                            continue

                        path_obj = Path(path)
                        ext = path_obj.suffix.lower().lstrip(".")
                        host_name = self._get_host_name_for_extension(ext)
                        items.append(
                            WorkfileItem(
                                workfile_id=repre_entity["id"],
                                filename=path_obj.name,
                                exists=path_obj.exists(),
                                icon=self._get_host_icon(host_name),
                                version=version_entity["version"],
                                published=True,
                            )
                        )

            cache.update_data(items)

        return items

    def _is_supported_workfile_representation(
        self,
        repre_entity: dict[str, Any],
    ) -> bool:
        """Return whether representation contains a supported workfile file."""
        extensions = self._get_workfile_extensions()
        if not extensions:
            return True

        for repre_file in repre_entity.get("files") or []:
            filename = repre_file.get("name") or ""
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext in extensions:
                return True
        return False

    def _get_workfile_extensions(self) -> set[str]:
        """Collect all known workfile extensions from enabled host addons."""
        if self._workfile_extensions is None:
            extensions = set()
            addons_manager = self._controller.get_addons_manager()
            for addon in addons_manager.get_enabled_addons():
                if not isinstance(addon, IHostAddon):
                    continue
                for ext in addon.get_workfile_extensions():
                    ext = ext.lower().lstrip(".")
                    if ext:
                        extensions.add(ext)
            self._workfile_extensions = extensions
        return self._workfile_extensions

    def _get_extension_to_host_name(self) -> dict[str, str]:
        """Build deterministic extension->host_name mapping for host icons."""
        if self._extension_to_host_name is None:
            mapping: dict[str, str] = {}
            addons_manager = self._controller.get_addons_manager()
            host_addons: list[tuple[str, IHostAddon]] = []
            for addon in addons_manager.get_enabled_addons():
                if not isinstance(addon, IHostAddon):
                    continue
                hn = addon.host_name
                if not hn:
                    continue
                host_addons.append((hn, addon))
            for host_name, addon in sorted(host_addons, key=lambda t: t[0]):
                for raw_ext in addon.get_workfile_extensions():
                    ext = raw_ext.lower().lstrip(".")
                    if ext and ext not in mapping:
                        mapping[ext] = host_name
            self._extension_to_host_name = mapping
        return self._extension_to_host_name

    def _get_host_name_for_extension(self, ext: str) -> Optional[str]:
        """Get host name for a normalized extension without leading dot."""
        if not ext:
            return None
        return self._get_extension_to_host_name().get(ext)

    def _get_host_icon(
        self, host_name: Optional[str]
    ) -> Optional[str]:
        """Return host icon url for a host name."""
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
        """Collect host icon urls from applications addon app groups."""
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
