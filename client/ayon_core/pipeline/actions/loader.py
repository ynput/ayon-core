"""API for actions for loader tool.

Even though the api is meant for the loader tool, the api should be possible
    to use in a standalone way out of the loader tool.

To use add actions, make sure your addon does inherit from
    'IPluginPaths' and implements 'get_loader_action_plugin_paths' which
    returns paths to python files with loader actions.

The plugin is used to collect available actions for the given context and to
    execute them. Selection is defined with 'LoaderActionSelection' object
    that also contains a cache of entities and project anatomy.

Implementing 'get_action_items' allows the plugin to define what actions
    are shown and available for the selection. Because for a single selection
    can be shown multiple actions with the same action identifier, the action
    items also have 'data' attribute which can be used to store additional
    data for the action (they have to be json-serializable).

The action is triggered by calling the 'execute_action' method. Which takes
    the action identifier, the selection, the additional data from the action
    item and form values from the form if any.

Using 'LoaderActionResult' as the output of 'execute_action' can trigger to
    show a message in UI or to show an additional form ('LoaderActionForm')
    which would retrigger the action with the values from the form on
    submitting. That allows handling of multistep actions.

It is also recommended that the plugin does override the 'identifier'
    attribute. The identifier has to be unique across all plugins.
    Class name is used by default.

The selection wrapper currently supports the following types of entity types:
    - version
    - representation
It is planned to add 'folder' and 'task' selection in the future.

NOTE: It is possible to trigger 'execute_action' without ever calling
    'get_action_items', that can be handy in automations.

The whole logic is wrapped into 'LoaderActionsContext'. It takes care of
    the discovery of plugins and wraps the collection and execution of
    action items. Method 'execute_action' on context also requires plugin
    identifier.

The flow of the logic is (in the loader tool):
    1. User selects entities in the UI.
    2. Right-click the selected entities.
    3. Use 'LoaderActionsContext' to collect items using 'get_action_items'.
    4. Show a menu (with submenus) in the UI.
    5. If a user selects an action, the action is triggered using
        'execute_action'.
    5a. If the action returns 'LoaderActionResult', show a 'message' if it is
        filled and show a form dialog if 'form' is filled.
    5b. If the user submitted the form, trigger the action again with the
        values from the form and repeat from 5a.

"""
from __future__ import annotations

import os
import collections
import copy
import logging
from abc import ABC, abstractmethod
import typing
from typing import Optional, Any, Callable
from dataclasses import dataclass

import ayon_api

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import StrEnum, Logger
from ayon_core.lib.attribute_definitions import (
    AbstractAttrDef,
    serialize_attr_defs,
    deserialize_attr_defs,
)
from ayon_core.host import AbstractHost
from ayon_core.addon import AddonsManager, IPluginPaths
from ayon_core.settings import get_studio_settings, get_project_settings
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.plugin_discover import discover_plugins

if typing.TYPE_CHECKING:
    from typing import Union

    DataBaseType = Union[str, int, float, bool]
    DataType = dict[str, Union[DataBaseType, list[DataBaseType]]]

_PLACEHOLDER = object()


class LoaderSelectedType(StrEnum):
    """Selected entity type."""
    # folder = "folder"
    # task = "task"
    version = "version"
    representation = "representation"


class SelectionEntitiesCache:
    """Cache of entities used as helper in the selection wrapper.

    It is possible to get entities based on ids with helper methods to get
        entities, their parents or their children's entities.

    The goal is to avoid multiple API calls for the same entity in multiple
        action plugins.

    The cache is based on the selected project. Entities are fetched
        if are not in cache yet.
    """
    def __init__(
        self,
        project_name: str,
        project_entity: Optional[dict[str, Any]] = None,
        folders_by_id: Optional[dict[str, dict[str, Any]]] = None,
        tasks_by_id: Optional[dict[str, dict[str, Any]]] = None,
        products_by_id: Optional[dict[str, dict[str, Any]]] = None,
        versions_by_id: Optional[dict[str, dict[str, Any]]] = None,
        representations_by_id: Optional[dict[str, dict[str, Any]]] = None,
        task_ids_by_folder_id: Optional[dict[str, set[str]]] = None,
        product_ids_by_folder_id: Optional[dict[str, set[str]]] = None,
        version_ids_by_product_id: Optional[dict[str, set[str]]] = None,
        representation_ids_by_version_id: Optional[dict[str, set[str]]] = None,
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
        self._representation_ids_by_version_id = (
            representation_ids_by_version_id or {}
        )

    def get_project(self) -> dict[str, Any]:
        """Get project entity"""
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
            self._representation_ids_by_version_id,
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
    """Selection of entities for loader actions.

    Selection tells action plugins what exactly is selected in the tool and
        which ids.

    Contains entity cache which can be used to get entities by their ids. Or
        to get project settings and anatomy.

    """
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

    # --- Helper methods ---
    def versions_selected(self) -> bool:
        """Selected entity type is version.

        Returns:
            bool: True if selected entity type is version.

        """
        return self._selected_type == LoaderSelectedType.version

    def representations_selected(self) -> bool:
        """Selected entity type is representation.

        Returns:
            bool: True if selected entity type is representation.

        """
        return self._selected_type == LoaderSelectedType.representation

    def get_selected_version_entities(self) -> list[dict[str, Any]]:
        """Retrieve selected version entities.

        An empty list is returned if 'version' is not the selected
            entity type.

        Returns:
            list[dict[str, Any]]: List of selected version entities.

        """
        if self.versions_selected():
            return self.entities.get_versions(self.selected_ids)
        return []

    def get_selected_representation_entities(self) -> list[dict[str, Any]]:
        """Retrieve selected representation entities.

        An empty list is returned if 'representation' is not the selected
            entity type.

        Returns:
            list[dict[str, Any]]: List of selected representation entities.

        """
        if self.representations_selected():
            return self.entities.get_representations(self.selected_ids)
        return []


@dataclass
class LoaderActionItem:
    """Item of loader action.

    Action plugins return these items as possible actions to run for a given
        context.

    Because the action item can be related to a specific entity
        and not the whole selection, they also have to define the entity type
        and ids to be executed on.

    Attributes:
        label (str): Text shown in UI.
        order (int): Order of the action in UI.
        group_label (Optional[str]): Label of the group to which the action
            belongs.
        icon (Optional[dict[str, Any]): Icon definition.
        data (Optional[DataType]): Action item data.
        identifier (Optional[str]): Identifier of the plugin which
            created the action item. Is filled automatically. Is not changed
            if is filled -> can lead to different plugin.

    """
    label: str
    order: int = 0
    group_label: Optional[str] = None
    icon: Optional[dict[str, Any]] = None
    data: Optional[DataType] = None
    # Is filled automatically
    identifier: str = None


@dataclass
class LoaderActionForm:
    """Form for loader action.

    If an action needs to collect information from a user before or during of
        the action execution, it can return a response with a form. When the
        form is submitted, a new execution of the action is triggered.

    It is also possible to just show a label message without the submit
        button to make sure the user has seen the message.

    Attributes:
        title (str): Title of the form -> title of the window.
        fields (list[AbstractAttrDef]): Fields of the form.
        submit_label (Optional[str]): Label of the submit button. Is hidden
            if is set to None.
        submit_icon (Optional[dict[str, Any]]): Icon definition of the submit
            button.
        cancel_label (Optional[str]): Label of the cancel button. Is hidden
            if is set to None. User can still close the window tho.
        cancel_icon (Optional[dict[str, Any]]): Icon definition of the cancel
            button.

    """
    title: str
    fields: list[AbstractAttrDef]
    submit_label: Optional[str] = "Submit"
    submit_icon: Optional[dict[str, Any]] = None
    cancel_label: Optional[str] = "Cancel"
    cancel_icon: Optional[dict[str, Any]] = None

    def to_json_data(self) -> dict[str, Any]:
        fields = self.fields
        if fields is not None:
            fields = serialize_attr_defs(fields)
        return {
            "title": self.title,
            "fields": fields,
            "submit_label": self.submit_label,
            "submit_icon": self.submit_icon,
            "cancel_label": self.cancel_label,
            "cancel_icon": self.cancel_icon,
        }

    @classmethod
    def from_json_data(cls, data: dict[str, Any]) -> "LoaderActionForm":
        fields = data["fields"]
        if fields is not None:
            data["fields"] = deserialize_attr_defs(fields)
        return cls(**data)


@dataclass
class LoaderActionResult:
    """Result of loader action execution.

    Attributes:
        message (Optional[str]): Message to show in UI.
        success (bool): If the action was successful. Affects color of
            the message.
        form (Optional[LoaderActionForm]): Form to show in UI.
        form_values (Optional[dict[str, Any]]): Values for the form. Can be
            used if the same form is re-shown e.g. because a user forgot to
            fill a required field.

    """
    message: Optional[str] = None
    success: bool = True
    form: Optional[LoaderActionForm] = None
    form_values: Optional[dict[str, Any]] = None

    def to_json_data(self) -> dict[str, Any]:
        form = self.form
        if form is not None:
            form = form.to_json_data()
        return {
            "message": self.message,
            "success": self.success,
            "form": form,
            "form_values": self.form_values,
        }

    @classmethod
    def from_json_data(cls, data: dict[str, Any]) -> "LoaderActionResult":
        form = data["form"]
        if form is not None:
            data["form"] = LoaderActionForm.from_json_data(form)
        return LoaderActionResult(**data)


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
        selection: LoaderActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        """Execute an action.

        Args:
            selection (LoaderActionSelection): Selection wrapper. Can be used
                to get entities or get context of original selection.
            data (Optional[DataType]): Additional action item data.
            form_values (dict[str, Any]): Attribute values.

        Returns:
            Optional[LoaderActionResult]: Result of the action execution.

        """
        pass


class LoaderActionsContext:
    """Wrapper for loader actions and their logic.

    Takes care about the public api of loader actions and internal logic like
        discovery and initialization of plugins.

    """
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
        """Reset context cache.

        Reset plugins and studio settings to reload them.

        Notes:
             Does not reset the cache of AddonsManger because there should not
                be a reason to do so.

        """
        self._studio_settings = studio_settings
        self._plugins = None

    def get_addons_manager(self) -> AddonsManager:
        if self._addons_manager is None:
            self._addons_manager = AddonsManager(
                settings=self.get_studio_settings()
            )
        return self._addons_manager

    def get_host(self) -> Optional[AbstractHost]:
        """Get current host integration.

        Returns:
            Optional[AbstractHost]: Host integration. Can be None if host
                integration is not registered -> probably not used in the
                host integration process.

        """
        if self._host is _PLACEHOLDER:
            from ayon_core.pipeline import registered_host

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
        """Collect action items from all plugins for given selection.

        Args:
            selection (LoaderActionSelection): Selection wrapper.

        """
        output = []
        for plugin_id, plugin in self._get_plugins().items():
            try:
                for action_item in plugin.get_action_items(selection):
                    if action_item.identifier is None:
                        action_item.identifier = plugin_id
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
        identifier: str,
        selection: LoaderActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        """Trigger action execution.

        Args:
            identifier (str): Identifier of the plugin.
            selection (LoaderActionSelection): Selection wrapper. Can be used
                to get what is selected in UI and to get access to entity
                cache.
            data (Optional[DataType]): Additional action item data.
            form_values (dict[str, Any]): Form values related to action.
                Usually filled if action returned response with form.

        """
        plugins_by_id = self._get_plugins()
        plugin = plugins_by_id[identifier]
        return plugin.execute_action(
            selection,
            data,
            form_values,
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


class LoaderSimpleActionPlugin(LoaderActionPlugin):
    """Simple action plugin.

    This action will show exactly one action item defined by attributes
        on the class.

    Attributes:
        label: Label of the action item.
        order: Order of the action item.
        group_label: Label of the group to which the action belongs.
        icon: Icon definition shown next to label.

    """

    label: Optional[str] = None
    order: int = 0
    group_label: Optional[str] = None
    icon: Optional[dict[str, Any]] = None

    @abstractmethod
    def is_compatible(self, selection: LoaderActionSelection) -> bool:
        """Check if plugin is compatible with selection.

        Args:
            selection (LoaderActionSelection): Selection information.

        Returns:
            bool: True if plugin is compatible with selection.

        """
        pass

    @abstractmethod
    def process(
        self,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        """Process action based on selection.

        Args:
            selection (LoaderActionSelection): Selection information.
            form_values (dict[str, Any]): Values from a form if there are any.

        Returns:
            Optional[LoaderActionResult]: Result of the action.

        """
        pass

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        if self.is_compatible(selection):
            label = self.label or self.__class__.__name__
            return [
                LoaderActionItem(
                    label=label,
                    order=self.order,
                    group_label=self.group_label,
                    icon=self.icon,
                )
            ]
        return []

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: Optional[DataType],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        return self.process(selection, form_values)
