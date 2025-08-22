from __future__ import annotations

import os
import collections
import copy
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any, Callable
from dataclasses import dataclass

import ayon_api

from ayon_core import AYON_CORE_ROOT
from ayon_core.host import AbstractHost
from ayon_core.lib import StrEnum, Logger, AbstractAttrDef
from ayon_core.addon import AddonsManager, IPluginPaths
from ayon_core.settings import get_studio_settings, get_project_settings
from ayon_core.pipeline import Anatomy, registered_host
from ayon_core.pipeline.plugin_discover import discover_plugins

_PLACEHOLDER = object()


class LoaderSelectedType(StrEnum):
    """Selected entity type."""
    # folder = "folder"
    # task = "task"
    version = "version"
    representation = "representation"


class SelectionEntitiesCache:
    def __init__(
        self,
        project_name: str,
        project_entity: Optional[dict[str, Any]] = None,
        folders_by_id: Optional[dict[str, dict[str, Any]]] = None,
        tasks_by_id: Optional[dict[str, dict[str, Any]]] = None,
        products_by_id: Optional[dict[str, dict[str, Any]]] = None,
        versions_by_id: Optional[dict[str, dict[str, Any]]] = None,
        representations_by_id: Optional[dict[str, dict[str, Any]]] = None,
        task_ids_by_folder_id: Optional[dict[str, str]] = None,
        product_ids_by_folder_id: Optional[dict[str, str]] = None,
        version_ids_by_product_id: Optional[dict[str, str]] = None,
        version_id_by_task_id: Optional[dict[str, str]] = None,
        representation_id_by_version_id: Optional[dict[str, str]] = None,
    ):
        self._project_name = project_name
        self._project_entity = project_entity
        self._folders_by_id = folders_by_id or {}
        self._tasks_by_id = tasks_by_id or {}
        self._products_by_id = products_by_id or {}
        self._versions_by_id = versions_by_id or {}
        self._representations_by_id = representations_by_id or {}

        self._task_ids_by_folder_id = task_ids_by_folder_id or {}
        self._product_ids_by_folder_id = product_ids_by_folder_id or {}
        self._version_ids_by_product_id = version_ids_by_product_id or {}
        self._version_id_by_task_id = version_id_by_task_id or {}
        self._representation_id_by_version_id = (
            representation_id_by_version_id or {}
        )

    def get_project(self) -> dict[str, Any]:
        if self._project_entity is None:
            self._project_entity = ayon_api.get_project(self._project_name)
        return copy.deepcopy(self._project_entity)

    def get_folders(
        self, folder_ids: set[str]
    ) -> list[dict[str, Any]]:
        return self._get_entities(
            folder_ids,
            self._folders_by_id,
            "folder_ids",
            ayon_api.get_folders,
        )

    def get_tasks(
        self, task_ids: set[str]
    ) -> list[dict[str, Any]]:
        return self._get_entities(
            task_ids,
            self._tasks_by_id,
            "task_ids",
            ayon_api.get_tasks,
        )

    def get_products(
        self, product_ids: set[str]
    ) -> list[dict[str, Any]]:
        return self._get_entities(
            product_ids,
            self._products_by_id,
            "product_ids",
            ayon_api.get_products,
        )

    def get_versions(
        self, version_ids: set[str]
    ) -> list[dict[str, Any]]:
        return self._get_entities(
            version_ids,
            self._versions_by_id,
            "version_ids",
            ayon_api.get_versions,
        )

    def get_representations(
        self, representation_ids: set[str]
    ) -> list[dict[str, Any]]:
        return self._get_entities(
            representation_ids,
            self._representations_by_id,
            "representation_ids",
            ayon_api.get_representations,
        )

    def get_folders_tasks(
        self, folder_ids: set[str]
    ) -> list[dict[str, Any]]:
        task_ids = self._fill_parent_children_ids(
            folder_ids,
            "folderId",
            "folder_ids",
            self._task_ids_by_folder_id,
            ayon_api.get_tasks,
        )
        return self.get_tasks(task_ids)

    def get_folders_products(
        self, folder_ids: set[str]
    ) -> list[dict[str, Any]]:
        product_ids = self._get_folders_products_ids(folder_ids)
        return self.get_products(product_ids)

    def get_tasks_versions(
        self, task_ids: set[str]
    ) -> list[dict[str, Any]]:
        folder_ids = {
            task["folderId"]
            for task in self.get_tasks(task_ids)
        }
        product_ids = self._get_folders_products_ids(folder_ids)
        output = []
        for version in self.get_products_versions(product_ids):
            task_id = version["taskId"]
            if task_id in task_ids:
                output.append(version)
        return output

    def get_products_versions(
        self, product_ids: set[str]
    ) -> list[dict[str, Any]]:
        version_ids = self._fill_parent_children_ids(
            product_ids,
            "productId",
            "product_ids",
            self._version_ids_by_product_id,
            ayon_api.get_versions,
        )
        return self.get_versions(version_ids)

    def get_versions_representations(
        self, version_ids: set[str]
    ) -> list[dict[str, Any]]:
        repre_ids = self._fill_parent_children_ids(
            version_ids,
            "versionId",
            "version_ids",
            self._representation_id_by_version_id,
            ayon_api.get_representations,
        )
        return self.get_representations(repre_ids)

    def get_tasks_folders(self, task_ids: set[str]) -> list[dict[str, Any]]:
        folder_ids = {
            task["folderId"]
            for task in self.get_tasks(task_ids)
        }
        return self.get_folders(folder_ids)

    def get_products_folders(
        self, product_ids: set[str]
    ) -> list[dict[str, Any]]:
        folder_ids = {
            product["folderId"]
            for product in self.get_products(product_ids)
        }
        return self.get_folders(folder_ids)

    def get_versions_products(
        self, version_ids: set[str]
    ) -> list[dict[str, Any]]:
        product_ids = {
            version["productId"]
            for version in self.get_versions(version_ids)
        }
        return self.get_products(product_ids)

    def get_versions_tasks(
        self, version_ids: set[str]
    ) -> list[dict[str, Any]]:
        task_ids = {
            version["taskId"]
            for version in self.get_versions(version_ids)
            if version["taskId"]
        }
        return self.get_tasks(task_ids)

    def get_representations_versions(
        self, representation_ids: set[str]
    ) -> list[dict[str, Any]]:
        version_ids = {
            repre["versionId"]
            for repre in self.get_representations(representation_ids)
        }
        return self.get_versions(version_ids)

    def _get_folders_products_ids(self, folder_ids: set[str]) -> set[str]:
        return self._fill_parent_children_ids(
            folder_ids,
            "folderId",
            "folder_ids",
            self._product_ids_by_folder_id,
            ayon_api.get_products,
        )

    def _fill_parent_children_ids(
        self,
        entity_ids: set[str],
        parent_key: str,
        filter_attr: str,
        parent_mapping: dict[str, set[str]],
        getter: Callable,
    ) -> set[str]:
        if not entity_ids:
            return set()
        children_ids = set()
        missing_ids = set()
        for entity_id in entity_ids:
            _children_ids = parent_mapping.get(entity_id)
            if _children_ids is None:
                missing_ids.add(entity_id)
            else:
                children_ids.update(_children_ids)
        if missing_ids:
            entities_by_parent_id = collections.defaultdict(set)
            for entity in getter(
                self._project_name,
                fields={"id", parent_key},
                **{filter_attr: missing_ids},
            ):
                child_id = entity["id"]
                children_ids.add(child_id)
                entities_by_parent_id[entity[parent_key]].add(child_id)

            for entity_id in missing_ids:
                parent_mapping[entity_id] = entities_by_parent_id[entity_id]

        return children_ids

    def _get_entities(
        self,
        entity_ids: set[str],
        cache_var: dict[str, Any],
        filter_arg: str,
        getter: Callable,
    ) -> list[dict[str, Any]]:
        if not entity_ids:
            return []

        output = []
        missing_ids: set[str] = set()
        for entity_id in entity_ids:
            entity = cache_var.get(entity_id)
            if entity_id not in cache_var:
                missing_ids.add(entity_id)
                cache_var[entity_id] = None
            elif entity:
                output.append(entity)

        if missing_ids:
            for entity in getter(
                self._project_name,
                **{filter_arg: missing_ids}
            ):
                output.append(entity)
                cache_var[entity["id"]] = entity
        return output


class LoaderActionSelection:
    def __init__(
        self,
        project_name: str,
        selected_ids: set[str],
        selected_type: LoaderSelectedType,
        *,
        project_anatomy: Optional[Anatomy] = None,
        project_settings: Optional[dict[str, Any]] = None,
        entities_cache: Optional[SelectionEntitiesCache] = None,
    ):
        self._project_name = project_name
        self._selected_ids = selected_ids
        self._selected_type = selected_type

        self._project_anatomy = project_anatomy
        self._project_settings = project_settings

        if entities_cache is None:
            entities_cache = SelectionEntitiesCache(project_name)
        self._entities_cache = entities_cache

    def get_entities_cache(self) -> SelectionEntitiesCache:
        return self._entities_cache

    def get_project_name(self) -> str:
        return self._project_name

    def get_selected_ids(self) -> set[str]:
        return set(self._selected_ids)

    def get_selected_type(self) -> str:
        return self._selected_type

    def get_project_settings(self) -> dict[str, Any]:
        if self._project_settings is None:
            self._project_settings = get_project_settings(self._project_name)
        return copy.deepcopy(self._project_settings)

    def get_project_anatomy(self) -> Anatomy:
        if self._project_anatomy is None:
            self._project_anatomy = Anatomy(
                self._project_name,
                project_entity=self.get_entities_cache().get_project(),
            )
        return self._project_anatomy

    project_name = property(get_project_name)
    selected_ids = property(get_selected_ids)
    selected_type = property(get_selected_type)
    project_settings = property(get_project_settings)
    project_anatomy = property(get_project_anatomy)
    entities = property(get_entities_cache)


@dataclass
class LoaderActionItem:
    identifier: str
    entity_ids: set[str]
    entity_type: str
    label: str
    order: int = 0
    group_label: Optional[str] = None
    icon: Optional[dict[str, Any]] = None
    # Is filled automatically
    plugin_identifier: str = None


@dataclass
class LoaderActionForm:
    title: str
    fields: list[AbstractAttrDef]
    submit_label: Optional[str] = "Submit"
    submit_icon: Optional[str] = None
    cancel_label: Optional[str] = "Cancel"
    cancel_icon: Optional[str] = None


@dataclass
class LoaderActionResult:
    message: Optional[str] = None
    success: bool = True
    form: Optional[LoaderActionForm] = None
    form_values: Optional[dict[str, Any]] = None


class LoaderActionPlugin(ABC):
    """Plugin for loader actions.

    Plugin is responsible for getting action items and executing actions.


    """
    _log: Optional[logging.Logger] = None
    enabled: bool = True

    def __init__(self, context: "LoaderActionsContext") -> None:
        self._context = context
        self.apply_settings(context.get_studio_settings())

    def apply_settings(self, studio_settings: dict[str, Any]) -> None:
        """Apply studio settings to the plugin.

        Args:
            studio_settings (dict[str, Any]): Studio settings.

        """
        pass

    @property
    def log(self) -> logging.Logger:
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def identifier(self) -> str:
        """Identifier of the plugin.

        Returns:
            str: Plugin identifier.

        """
        return self.__class__.__name__

    @property
    def host_name(self) -> Optional[str]:
        """Name of the current host."""
        return self._context.get_host_name()

    @abstractmethod
    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        """Action items for the selection.

        Args:
            selection (LoaderActionSelection): Selection.

        Returns:
            list[LoaderActionItem]: Action items.

        """
        pass

    @abstractmethod
    def execute_action(
        self,
        identifier: str,
        entity_ids: set[str],
        entity_type: str,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        """Execute an action.

        Args:
            identifier (str): Action identifier.
            entity_ids: (set[str]): Entity ids stored on action item.
            entity_type: (str): Entity type stored on action item.
            selection (LoaderActionSelection): Selection wrapper. Can be used
                to get entities or get context of original selection.
            form_values (dict[str, Any]): Attribute values.

        Returns:
            Optional[LoaderActionResult]: Result of the action execution.

        """
        pass


class LoaderActionsContext:
    def __init__(
        self,
        studio_settings: Optional[dict[str, Any]] = None,
        addons_manager: Optional[AddonsManager] = None,
        host: Optional[AbstractHost] = _PLACEHOLDER,
    ) -> None:
        self._log = Logger.get_logger(self.__class__.__name__)

        self._addons_manager = addons_manager
        self._host = host

        # Attributes that are re-cached on reset
        self._studio_settings = studio_settings
        self._plugins = None

    def reset(
        self, studio_settings: Optional[dict[str, Any]] = None
    ) -> None:
        self._studio_settings = studio_settings
        self._plugins = None

    def get_addons_manager(self) -> AddonsManager:
        if self._addons_manager is None:
            self._addons_manager = AddonsManager(
                settings=self.get_studio_settings()
            )
        return self._addons_manager

    def get_host(self) -> Optional[AbstractHost]:
        if self._host is _PLACEHOLDER:
            self._host = registered_host()
        return self._host

    def get_host_name(self) -> Optional[str]:
        host = self.get_host()
        if host is None:
            return None
        return host.name

    def get_studio_settings(self) -> dict[str, Any]:
        if self._studio_settings is None:
            self._studio_settings = get_studio_settings()
        return copy.deepcopy(self._studio_settings)

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        output = []
        for plugin_id, plugin in self._get_plugins().items():
            try:
                for action_item in plugin.get_action_items(selection):
                    if action_item.plugin_identifier is None:
                        action_item.plugin_identifier = plugin_id
                    output.append(action_item)

            except Exception:
                self._log.warning(
                    "Failed to get action items for"
                    f" plugin '{plugin.identifier}'",
                    exc_info=True,
                )
        return output

    def execute_action(
        self,
        plugin_identifier: str,
        action_identifier: str,
        entity_ids: set[str],
        entity_type: LoaderSelectedType,
        selection: LoaderActionSelection,
        attribute_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        plugins_by_id = self._get_plugins()
        plugin = plugins_by_id[plugin_identifier]
        return plugin.execute_action(
            action_identifier,
            entity_ids,
            entity_type,
            selection,
            attribute_values,
        )

    def _get_plugins(self) -> dict[str, LoaderActionPlugin]:
        if self._plugins is None:
            addons_manager = self.get_addons_manager()
            all_paths = [
                os.path.join(AYON_CORE_ROOT, "plugins", "loader")
            ]
            for addon in addons_manager.addons:
                if not isinstance(addon, IPluginPaths):
                    continue
                paths = addon.get_loader_action_plugin_paths()
                if paths:
                    all_paths.extend(paths)

            result = discover_plugins(LoaderActionPlugin, all_paths)
            result.log_report()
            plugins = {}
            for cls in result.plugins:
                try:
                    plugin = cls(self)
                    if not plugin.enabled:
                        continue

                    plugin_id = plugin.identifier
                    if plugin_id not in plugins:
                        plugins[plugin_id] = plugin
                        continue

                    self._log.warning(
                        f"Duplicated plugins identifier found '{plugin_id}'."
                    )

                except Exception:
                    self._log.warning(
                        f"Failed to initialize plugin '{cls.__name__}'",
                        exc_info=True,
                    )
            self._plugins = plugins
        return self._plugins
