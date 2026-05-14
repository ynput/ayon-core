from __future__ import annotations

import collections
import inspect
import os
import sys
import traceback
import uuid
from typing import Any, Callable, Optional

import ayon_api

from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.pipeline import get_current_host_name
from ayon_core.settings import get_project_settings
from ayon_core.pipeline.actions import (
    LoaderActionsContext,
    LoaderActionSelection,
    LoaderSelectedType,
    SelectionEntitiesCache,
)
from ayon_core.pipeline.load import (
    IncompatibleLoaderError,
    LoadError,
    ProductLoaderPlugin,
    discover_loader_plugins,
    filter_repre_contexts_by_loader,
    get_loader_identifier,
    get_representation_path_with_anatomy,
    load_with_product_context,
    load_with_product_contexts,
    load_with_repre_context,
)
from ayon_core.tools.loader.abstract import ActionItem

ACTIONS_MODEL_SENDER = "actions.model"
LOADER_PLUGIN_ID = "__loader_plugin__"
REPRESENTATION_PANEL_ONLY_ACTION_IDENTIFIERS = {
    "core.copy-action",
    "core.open-file",
    "core.open-folder",
}
REPRESENTATION_PANEL_ONLY_GROUP_LABELS = {
    "copy file",
    "copy file path",
    "open file",
    "open folder",
}
NOT_SET = object()


class LoaderActionsModel:
    """Model for loader actions.

    TODOs:
        Deprecate 'qargparse' usage in loaders and implement conversion
            of 'ActionItem' to data (and 'from_data').
        Use controller to get entities -> possible only when
            loaders are able to handle AYON vs. OpenPype logic.
        Add missing site sync logic, and if possible remove it from loaders.
        Implement loader actions to replace load plugins.
        Ask loader actions to return action items instead of guessing them.
    """

    # Cache loader plugins for some time
    # NOTE Set to '0' for development
    loaders_cache_lifetime = 30

    def __init__(self, controller):
        self._log = Logger.get_logger(self.__class__.__name__)
        self._controller = controller
        self._current_context_project = NOT_SET
        self._loaders_by_identifier = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime
        )
        self._product_loaders = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime
        )
        self._repre_loaders = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime
        )
        self._loader_actions = LoaderActionsContext()

        self._projects_cache = NestedCacheItem(levels=1, lifetime=60)
        self._folders_cache = NestedCacheItem(levels=2, lifetime=300)
        self._tasks_cache = NestedCacheItem(levels=2, lifetime=300)
        self._products_cache = NestedCacheItem(levels=2, lifetime=300)
        self._versions_cache = NestedCacheItem(levels=2, lifetime=1200)
        self._representations_cache = NestedCacheItem(
            levels=2, lifetime=1200
        )
        self._repre_parents_cache = NestedCacheItem(
            levels=2, lifetime=1200
        )

    def reset(self):
        """Reset the model with all cached items."""

        self._current_context_project = NOT_SET
        self._loaders_by_identifier.reset()
        self._product_loaders.reset()
        self._repre_loaders.reset()
        self._loader_actions.reset()

        self._folders_cache.reset()
        self._tasks_cache.reset()
        self._products_cache.reset()
        self._versions_cache.reset()
        self._representations_cache.reset()
        self._repre_parents_cache.reset()

    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        if entity_type == "folder":
            return self._get_loader_action_items(
                project_name,
                entity_ids,
                entity_type,
                {},
                {},
            )

        version_context_by_id = {}
        repre_context_by_id = {}
        if entity_type == "representation":
            (
                version_context_by_id,
                repre_context_by_id
            ) = self._contexts_for_representations(project_name, entity_ids)

        if entity_type == "version":
            (
                version_context_by_id,
                repre_context_by_id
            ) = self._contexts_for_versions(project_name, entity_ids)

        action_items = self._get_action_items_for_contexts(
            project_name,
            version_context_by_id,
            repre_context_by_id,
            entity_type,
        )
        action_items.extend(self._get_loader_action_items(
            project_name,
            entity_ids,
            entity_type,
            version_context_by_id,
            repre_context_by_id,
        ))
        return action_items

    def get_versions_action_items(self, project_name, version_ids):
        return self.get_action_items(project_name, version_ids, "version")

    def get_representations_action_items(
        self, project_name, representation_ids
    ):
        return self.get_action_items(
            project_name, representation_ids, "representation"
        )

    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: Optional[dict[str, Any]],
        options: dict[str, Any],
        form_values: dict[str, Any],
    ):
        """Trigger action by identifier.

        Triggers the action by identifier for given contexts.

        Triggers events "load.started" and "load.finished". Finished event
            also contains "error_info" key with error information if any
            happened.

        Args:
            identifier (str): Plugin identifier.
            project_name (str): Project name.
            selected_ids (set[str]): Selected entity ids.
            selected_entity_type (str): Selected entity type.
            data (Optional[dict[str, Any]]): Additional action item data.
            options (dict[str, Any]): Loader option values.
            form_values (dict[str, Any]): Form values.
        """
        event_data = {
            "identifier": identifier,
            "project_name": project_name,
            "selected_ids": list(selected_ids),
            "selected_entity_type": selected_entity_type,
            "data": data,
            "id": uuid.uuid4().hex,
        }
        if identifier != LOADER_PLUGIN_ID:
            result = None
            crashed = False
            try:
                entities_cache = None
                if selected_entity_type == "folder":
                    entities_cache = self._prepare_entities_cache(
                        project_name,
                        selected_entity_type,
                        {},
                        {},
                        folder_ids=selected_ids,
                    )
                selection_kwargs = {}
                if entities_cache is not None:
                    selection_kwargs["entities_cache"] = entities_cache
                result = self._loader_actions.execute_action(
                    identifier=identifier,
                    selection=LoaderActionSelection(
                        project_name,
                        selected_ids,
                        LoaderSelectedType(selected_entity_type),
                        **selection_kwargs,
                    ),
                    data=data,
                    form_values=form_values,
                )

            except Exception:
                crashed = True
                self._log.warning(
                    f"Failed to execute action '{identifier}'",
                    exc_info=True,
                )

            event_data["result"] = result
            event_data["crashed"] = crashed
            self._controller.emit_event(
                "loader.action.finished",
                event_data,
                ACTIONS_MODEL_SENDER,
            )
            return

        loader = self._get_loader_by_identifier(project_name, data["loader"])
        entity_type = data["entity_type"]
        entity_ids = data["entity_ids"]

        if (
            hasattr(loader, "loading_started_message")
            and loader.loading_started_message
        ):
            event_data["message"] = loader.loading_started_message

        self._controller.emit_event(
            "load.started",
            event_data,
            ACTIONS_MODEL_SENDER,
        )
        from qtpy import QtWidgets

        app = QtWidgets.QApplication.instance()
        if app:
            app.processEvents()

        if entity_type == "version":
            error_info = self._trigger_version_loader(
                loader,
                options,
                project_name,
                entity_ids,
                event_data["id"],
            )
        elif entity_type == "representation":
            error_info = self._trigger_representation_loader(
                loader,
                options,
                project_name,
                entity_ids,
                event_data["id"],
            )
        else:
            raise NotImplementedError(
                f"Entity type '{entity_type}' is not implemented."
            )

        event_data["error_info"] = error_info
        self._controller.emit_event(
            "load.finished",
            event_data,
            ACTIONS_MODEL_SENDER,
        )

    def _get_current_context_project(self):
        """Get current context project name.

        The value is based on controller (host) and cached.

        Returns:
            Union[str, None]: Current context project.
        """

        if self._current_context_project is NOT_SET:
            context = self._controller.get_current_context()
            self._current_context_project = context["project_name"]
        return self._current_context_project

    def _get_action_label(self, loader, representation=None):
        """Pull label info from loader class.

        Args:
            loader (LoaderPlugin): Plugin class.
            representation (Optional[dict[str, Any]]): Representation data.

        Returns:
            str: Action label.
        """

        label = getattr(loader, "label", None)
        if label is None:
            label = loader.__name__
        if representation:
            # Add the representation as suffix
            label = "{} ({})".format(label, representation["name"])
        return label

    def _get_action_icon(self, loader):
        """Pull icon info from loader class.

        Args:
            loader (LoaderPlugin): Plugin class.

        Returns:
            Union[dict[str, Any], None]: Icon definition based on
                loader plugin.
        """

        # Support font-awesome icons using the `.icon` and `.color`
        # attributes on plug-ins.
        icon = getattr(loader, "icon", None)
        if icon is not None and not isinstance(icon, dict):
            icon = {
                "type": "awesome-font",
                "name": icon,
                "color": getattr(loader, "color", None) or "white",
            }
        return icon

    def _get_action_tooltip(self, loader):
        """Pull tooltip info from loader class.

        Args:
            loader (LoaderPlugin): Plugin class.

        Returns:
            str: Action tooltip.
        """

        # Add tooltip and statustip from Loader docstring
        return inspect.getdoc(loader)

    def _filter_loaders_by_tool_name(self, project_name, loaders):
        """Filter loaders by tool name.

        Tool names are based on AYON tools loader tool and library
        loader tool. The new tool merged both into one tool and the difference
        is based only on current project name.

        Args:
            project_name (str): Project name.
            loaders (list[LoaderPlugin]): List of loader plugins.

        Returns:
            list[LoaderPlugin]: Filtered list of loader plugins.
        """

        # Keep filtering by tool name
        # - if current context project name is same as project name we do
        #   expect the tool is used as AYON loader tool, otherwise
        #   as library loader tool.
        if project_name == self._get_current_context_project():
            tool_name = "loader"
        else:
            tool_name = "library_loader"
        filtered_loaders = []
        for loader in loaders:
            tool_names = getattr(loader, "tool_names", None)
            if (
                tool_names is None
                or "*" in tool_names
                or tool_name in tool_names
            ):
                filtered_loaders.append(loader)
        return filtered_loaders

    def _create_loader_action_item(
        self,
        loader,
        contexts,
        entity_ids,
        entity_type,
        repre_name=None,
    ):
        label = self._get_action_label(loader)
        if repre_name:
            label = "{} ({})".format(label, repre_name)
        representation_ids = None
        if entity_type == "representation":
            representation_ids = entity_ids
        return ActionItem(
            LOADER_PLUGIN_ID,
            label=label,
            group_label=None,
            icon=self._get_action_icon(loader),
            tooltip=self._get_action_tooltip(loader),
            order=loader.order,
            data={
                "entity_ids": entity_ids,
                "entity_type": entity_type,
                "loader": get_loader_identifier(loader),
            },
            options=loader.get_options(contexts),
            representation_ids=representation_ids,
            show_in_context_menu=getattr(loader, "show_in_context_menu", True),
            drag_drop_enabled=getattr(loader, "drag_drop_enabled", True),
            default_for_drag_drop=getattr(loader, "default_for_drag_drop", False),
            drag_drop_contexts=getattr(loader, "drag_drop_contexts", None),
        )

    def _get_loaders(self, project_name):
        """Loaders with loaded settings for a project.

        Questions:
            Project name is required because of settings. Should we actually
                pass in current project name instead of project name where
                we want to show loaders for?

        Returns:
            tuple[list[ProductLoaderPlugin], list[LoaderPlugin]]: Discovered
                loader plugins.
        """

        loaders_by_identifier_c = self._loaders_by_identifier[project_name]
        product_loaders_c = self._product_loaders[project_name]
        repre_loaders_c = self._repre_loaders[project_name]
        if loaders_by_identifier_c.is_valid:
            return product_loaders_c.get_data(), repre_loaders_c.get_data()

        # Get all representation->loader combinations available for the
        # index under the cursor, so we can list the user the options.
        available_loaders = self._filter_loaders_by_tool_name(
            project_name, discover_loader_plugins(project_name)
        )
        repre_loaders = []
        product_loaders = []
        loaders_by_identifier = {}
        for loader_cls in available_loaders:
            if not loader_cls.enabled:
                continue

            identifier = get_loader_identifier(loader_cls)
            loaders_by_identifier[identifier] = loader_cls
            if issubclass(loader_cls, ProductLoaderPlugin):
                product_loaders.append(loader_cls)
            else:
                repre_loaders.append(loader_cls)

        loaders_by_identifier_c.update_data(loaders_by_identifier)
        product_loaders_c.update_data(product_loaders)
        repre_loaders_c.update_data(repre_loaders)

        return product_loaders, repre_loaders

    def _get_loader_by_identifier(self, project_name, identifier):
        if not self._loaders_by_identifier[project_name].is_valid:
            self._get_loaders(project_name)
        loaders_by_identifier_c = self._loaders_by_identifier[project_name]
        loaders_by_identifier = loaders_by_identifier_c.get_data()
        return loaders_by_identifier.get(identifier)

    def _actions_sorter(self, action_item):
        """Sort the Loaders by their order and then their name.

        Returns:
            tuple[int, str]: Sort keys.
        """

        return action_item.order, action_item.label

    def _contexts_for_versions(self, project_name, version_ids):
        """Get contexts for given version ids.

        Prepare version contexts for 'ProductLoaderPlugin' and representation
        contexts for 'LoaderPlugin' for all children representations of
        given versions.

        This method is very similar to '_contexts_for_representations' but the
        queries of entities are called in a different order.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            tuple[list[dict[str, Any]], list[dict[str, Any]]]: Version and
                representation contexts.
        """

        # TODO fix hero version
        version_context_by_id = {}
        repre_context_by_id = {}
        vids = set(version_ids)
        if not project_name or not vids:
            return version_context_by_id, repre_context_by_id

        version_entities = self._get_versions(project_name, vids)
        version_entities_by_id = {}
        version_entities_by_product_id = collections.defaultdict(list)
        for version_entity in version_entities:
            version_id = version_entity["id"]
            product_id = version_entity["productId"]
            version_entities_by_id[version_id] = version_entity
            version_entities_by_product_id[product_id].append(version_entity)

        _product_ids = set(version_entities_by_product_id.keys())
        _product_entities = self._get_products(project_name, _product_ids)
        product_entities_by_id = {p["id"]: p for p in _product_entities}

        _folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        _folder_entities = self._get_folders(project_name, _folder_ids)
        folder_entities_by_id = {f["id"]: f for f in _folder_entities}

        project_entity = self._get_project(project_name)

        for version_id, version_entity in version_entities_by_id.items():
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            version_context_by_id[version_id] = {
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
            }

        repre_ids_by_vid = self._get_repre_ids_by_version_ids(
            project_name, vids
        )
        all_repre_ids: set[str] = set()
        for ids in repre_ids_by_vid.values():
            all_repre_ids |= set(ids)
        repre_entities = self._get_representations(project_name, all_repre_ids)
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = version_entities_by_id.get(version_id)
            if not version_entity:
                continue
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]

            repre_context_by_id[repre_entity["id"]] = {
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
                "representation": repre_entity,
            }

        return version_context_by_id, repre_context_by_id

    def _contexts_for_representations(self, project_name, repre_ids):
        """Get contexts for given representation ids.

        Prepare version contexts for 'ProductLoaderPlugin' and representation
        contexts for 'LoaderPlugin' for all children representations of
        given versions.

        This method is very similar to '_contexts_for_versions' but the
        queries of entities are called in a different order.

        Args:
            project_name (str): Project name.
            repre_ids (Iterable[str]): Representation ids.

        Returns:
            tuple[list[dict[str, Any]], list[dict[str, Any]]]: Version and
                representation contexts.
        """

        version_context_by_id = {}
        repre_context_by_id = {}
        if not project_name and not repre_ids:
            return version_context_by_id, repre_context_by_id

        repre_entities = list(
            ayon_api.get_representations(
                project_name, representation_ids=repre_ids
            )
        )
        version_ids = {r["versionId"] for r in repre_entities}
        version_entities = ayon_api.get_versions(
            project_name, version_ids=version_ids
        )
        version_entities_by_id = {v["id"]: v for v in version_entities}

        product_ids = {v["productId"] for v in version_entities_by_id.values()}
        product_entities = ayon_api.get_products(
            project_name, product_ids=product_ids
        )
        product_entities_by_id = {p["id"]: p for p in product_entities}

        folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        folder_entities = ayon_api.get_folders(
            project_name, folder_ids=folder_ids
        )
        folder_entities_by_id = {f["id"]: f for f in folder_entities}

        project_entity = ayon_api.get_project(project_name)

        for version_id, version_entity in version_entities_by_id.items():
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            version_context_by_id[version_id] = {
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
            }

        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = version_entities_by_id[version_id]
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]

            repre_context_by_id[repre_entity["id"]] = {
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
                "representation": repre_entity,
            }
        return version_context_by_id, repre_context_by_id

    def _get_project(self, project_name: str) -> dict[str, Any]:
        cache = self._projects_cache[project_name]
        if not cache.is_valid:
            cache.update_data(ayon_api.get_project(project_name))
        return cache.get_data()

    def _get_folders(
        self, project_name: str, folder_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Get folders by ids."""
        return self._get_entities(
            project_name,
            folder_ids,
            self._folders_cache,
            ayon_api.get_folders,
            "folder_ids",
        )

    def _get_products(
        self, project_name: str, product_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Get products by ids."""
        return self._get_entities(
            project_name,
            product_ids,
            self._products_cache,
            ayon_api.get_products,
            "product_ids",
        )

    def _get_versions(
        self, project_name: str, version_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Get versions by ids."""
        return self._get_entities(
            project_name,
            version_ids,
            self._versions_cache,
            ayon_api.get_versions,
            "version_ids",
        )

    def _get_representations(
        self, project_name: str, representation_ids: set[str]
    ) -> list[dict[str, Any]]:
        """Get representations by ids."""
        return self._get_entities(
            project_name,
            representation_ids,
            self._representations_cache,
            ayon_api.get_representations,
            "representation_ids",
        )

    def _get_repre_ids_by_version_ids(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, set[str]]:
        output = {}
        if not version_ids:
            return output

        project_cache = self._repre_parents_cache[project_name]
        missing_ids = set()
        for version_id in version_ids:
            cache = project_cache[version_id]
            if cache.is_valid:
                output[version_id] = cache.get_data()
            else:
                missing_ids.add(version_id)

        if missing_ids:
            repre_cache = self._representations_cache[project_name]
            repres_by_parent_id = collections.defaultdict(list)
            for repre in ayon_api.get_representations(
                project_name, version_ids=missing_ids
            ):
                version_id = repre["versionId"]
                repre_cache[repre["id"]].update_data(repre)
                repres_by_parent_id[version_id].append(repre)

            for version_id, repres in repres_by_parent_id.items():
                repre_ids = {
                    repre["id"]
                    for repre in repres
                }
                output[version_id] = set(repre_ids)
                project_cache[version_id].update_data(repre_ids)

        return output

    def _get_entities(
        self,
        project_name: str,
        entity_ids: set[str],
        cache: NestedCacheItem,
        getter: Callable,
        filter_arg: str,
    ) -> list[dict[str, Any]]:
        entities = []
        if not entity_ids:
            return entities

        missing_ids = set()
        project_cache = cache[project_name]
        for entity_id in entity_ids:
            entity_cache = project_cache[entity_id]
            if entity_cache.is_valid:
                entities.append(entity_cache.get_data())
            else:
                missing_ids.add(entity_id)

        if missing_ids:
            for entity in getter(project_name, **{filter_arg: missing_ids}):
                entities.append(entity)
                entity_id = entity["id"]
                project_cache[entity_id].update_data(entity)
        return entities

    def get_representation_file_paths(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
        anatomy: Any,
    ) -> list[str]:
        """Resolve local file paths for the given version or representation ids."""
        if not anatomy or not entity_ids:
            return []
        if entity_type == "representation":
            repre_ids = entity_ids
        else:
            version_to_repres = self._get_repre_ids_by_version_ids(
                project_name, entity_ids
            )
            repre_ids = set()
            for ids in version_to_repres.values():
                repre_ids |= ids
        repres = self._get_representations(project_name, repre_ids)
        paths = []
        for repre in repres:
            try:
                path_result = get_representation_path_with_anatomy(repre, anatomy)
                path = os.path.normpath(str(path_result))
                if path:
                    paths.append(path)
            except Exception:
                pass
        return paths

    def _get_drag_drop_profiles(self, project_name: str) -> list[dict[str, Any]]:
        settings = get_project_settings(project_name)
        return (
            settings.get("core", {})
            .get("tools", {})
            .get("loader", {})
            .get("drag_drop_default_repre_profiles")
            or []
        )

    @staticmethod
    def _repre_extension_lower(repre_entity: dict[str, Any]) -> Optional[str]:
        ctx = repre_entity.get("context") or {}
        ext = ctx.get("ext")
        if ext:
            return str(ext).lower().lstrip(".")
        path = (repre_entity.get("attrib") or {}).get("path")
        if path:
            return os.path.splitext(path)[1].lower().lstrip(".")
        return None

    def _profile_matches_drag_drop(
        self,
        profile: dict[str, Any],
        host_name: Optional[str],
        task_type: Optional[str],
        product_type: Optional[str],
        product_base_type: Optional[str],
        non_thumb_repres: dict[str, dict[str, Any]],
    ) -> bool:
        hosts = profile.get("host_names") or []
        if hosts and (not host_name or host_name not in hosts):
            return False
        tasks = profile.get("task_types") or []
        if tasks and (not task_type or task_type not in tasks):
            return False
        pts = profile.get("product_types") or []
        if pts and (not product_type or product_type not in pts):
            return False
        pbts = profile.get("product_base_types") or []
        if pbts:
            ok = False
            if product_base_type and product_base_type in pbts:
                ok = True
            elif product_type and product_type in pbts:
                ok = True
            if not ok:
                return False
        exts = profile.get("extensions") or []
        if exts:
            want = {str(e).lower().lstrip(".") for e in exts}
            found = False
            for repre in non_thumb_repres.values():
                rxt = self._repre_extension_lower(repre)
                if rxt and rxt in want:
                    found = True
                    break
            if not found:
                return False
        return True

    def resolve_drag_drop_representation_selection(
        self,
        project_name: str,
        version_ids: set[str],
    ) -> tuple[dict[str, str], dict[str, list[str]]]:
        """Pick primary representation id per version for Loader drag-and-drop."""
        primary_by_vid: dict[str, str] = {}
        candidates_by_vid: dict[str, list[str]] = {}

        if not project_name or not version_ids:
            return primary_by_vid, candidates_by_vid

        host_name = get_current_host_name()

        (
            version_context_by_id,
            repre_context_by_id,
        ) = self._contexts_for_versions(project_name, version_ids)

        profiles = self._get_drag_drop_profiles(project_name)

        task_ids: set[str] = set()
        for vc in version_context_by_id.values():
            tid = (vc.get("version") or {}).get("taskId")
            if tid:
                task_ids.add(str(tid))
        task_type_by_tid: dict[str, Optional[str]] = {}
        if task_ids:
            for t in ayon_api.get_tasks(project_name, task_ids=task_ids):
                task_type_by_tid[str(t["id"])] = t.get("taskType")

        for vid in version_ids:
            vc = version_context_by_id.get(vid)
            if not vc:
                continue
            product = vc["product"]
            version_ent = vc["version"]
            pt = product.get("productType")
            pbt = product.get("productBaseType")
            tid = version_ent.get("taskId")
            task_type = (
                task_type_by_tid.get(str(tid)) if tid else None
            )

            repre_ids_for_version = [
                rid
                for rid, ctx in repre_context_by_id.items()
                if ctx["version"]["id"] == vid
            ]
            repre_by_id = {
                rid: repre_context_by_id[rid]["representation"]
                for rid in repre_ids_for_version
            }

            def is_thumb(repre: dict[str, Any]) -> bool:
                return (repre.get("name") or "").lower() == "thumbnail"

            non_thumb = {
                rid: r for rid, r in repre_by_id.items() if not is_thumb(r)
            }
            if not non_thumb:
                non_thumb = dict(repre_by_id)

            chosen_rid: Optional[str] = None
            ordered: list[str] = []

            for profile in profiles:
                if not self._profile_matches_drag_drop(
                    profile,
                    host_name,
                    task_type,
                    pt,
                    pbt,
                    non_thumb,
                ):
                    continue
                priority_names = profile.get("default_repre_names") or []
                if not priority_names:
                    continue
                for rep_name in priority_names:
                    for rid, r in non_thumb.items():
                        if r.get("name") == rep_name:
                            chosen_rid = rid
                            ordered = [rid]
                            break
                    if chosen_rid:
                        break
                if chosen_rid:
                    break

            if not chosen_rid:
                if len(non_thumb) == 1:
                    rid = next(iter(non_thumb.keys()))
                    chosen_rid = rid
                    ordered = [rid]
                elif len(non_thumb) > 1:
                    sorted_ids = sorted(
                        non_thumb.keys(),
                        key=lambda x: (non_thumb[x].get("name") or ""),
                    )
                    ordered = sorted_ids
                    chosen_rid = sorted_ids[0]
                elif repre_by_id:
                    fallback_ids = sorted(
                        repre_by_id.keys(),
                        key=lambda x: (repre_by_id[x].get("name") or ""),
                    )
                    ordered = fallback_ids
                    chosen_rid = fallback_ids[0]

            if chosen_rid:
                primary_by_vid[vid] = chosen_rid
            if not ordered:
                ordered = sorted(
                    non_thumb.keys(),
                    key=lambda x: (non_thumb[x].get("name") or ""),
                )
                if not ordered and repre_by_id:
                    ordered = sorted(
                        repre_by_id.keys(),
                        key=lambda x: (repre_by_id[x].get("name") or ""),
                    )
            candidates_by_vid[vid] = ordered

        return primary_by_vid, candidates_by_vid

    def _get_action_items_for_contexts(
        self,
        project_name,
        version_context_by_id,
        repre_context_by_id,
        selected_entity_type,
    ):
        """Prepare action items based on contexts.

        Actions are prepared based on discovered loader plugins and contexts.
        The context must be valid for the loader plugin.

        Args:
            project_name (str): Project name.
            version_context_by_id (dict[str, dict[str, Any]]): Version
                contexts by version id.
            repre_context_by_id (dict[str, dict[str, Any]]): Representation
        """

        action_items = []
        if not version_context_by_id and not repre_context_by_id:
            return action_items

        product_loaders, repre_loaders = self._get_loaders(project_name)

        repre_contexts_by_name = collections.defaultdict(list)
        for repre_context in repre_context_by_id.values():
            repre_name = repre_context["representation"]["name"]
            repre_contexts_by_name[repre_name].append(repre_context)

        for loader in repre_loaders:
            # Allow representation loaders to hide only from the products /
            # versions menu. The representation panel should still expose
            # representation-specific actions.
            if (
                selected_entity_type == "version"
                and not getattr(loader, "show_in_versions_menu", True)
            ):
                continue
            for repre_name, repre_contexts in repre_contexts_by_name.items():
                ext_ok = [
                    ctx
                    for ctx in repre_contexts
                    if loader.has_valid_extension(ctx["representation"])
                ]
                if not ext_ok:
                    continue
                filtered_repre_contexts = filter_repre_contexts_by_loader(
                    ext_ok, loader
                )
                if not filtered_repre_contexts:
                    continue

                repre_ids = set()
                for repre_context in filtered_repre_contexts:
                    repre_ids.add(repre_context["representation"]["id"])

                item = self._create_loader_action_item(
                    loader,
                    filtered_repre_contexts,
                    repre_ids,
                    "representation",
                    repre_name=repre_name,
                )
                action_items.append(item)

        # Product Loaders.
        version_ids = set(version_context_by_id.keys())
        version_contexts = list(version_context_by_id.values())
        for loader in product_loaders:
            item = self._create_loader_action_item(
                loader,
                version_contexts,
                version_ids,
                "version",
            )
            action_items.append(item)

        action_items.sort(key=self._actions_sorter)
        return action_items

    def _get_loader_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
        version_context_by_id: dict[str, dict[str, Any]],
        repre_context_by_id: dict[str, dict[str, Any]],
    ) -> list[ActionItem]:
        entities_cache = self._prepare_entities_cache(
            project_name,
            entity_type,
            version_context_by_id,
            repre_context_by_id,
            folder_ids=entity_ids if entity_type == "folder" else None,
        )
        selection = LoaderActionSelection(
            project_name,
            entity_ids,
            LoaderSelectedType(entity_type),
            entities_cache=entities_cache,
        )

        items = []
        for action in self._loader_actions.get_action_items(selection):
            if (
                entity_type not in ("representation", "folder")
                and self._is_representation_panel_only_action(action)
            ):
                continue

            items.append(ActionItem(
                action.identifier,
                label=action.label,
                group_label=action.group_label,
                icon=action.icon,
                tooltip=action.tooltip,
                order=action.order,
                data=action.data,
                options=None,
                representation_ids=getattr(action, "representation_ids", None),
                show_in_context_menu=getattr(action, "show_in_context_menu", True),
                drag_drop_enabled=getattr(action, "drag_drop_enabled", True),
                default_for_drag_drop=getattr(action, "default_for_drag_drop", False),
                drag_drop_contexts=getattr(action, "drag_drop_contexts", None),
            ))
        return items

    def _is_representation_panel_only_action(self, action) -> bool:
        if action.identifier in REPRESENTATION_PANEL_ONLY_ACTION_IDENTIFIERS:
            return True

        group_label = action.group_label
        if group_label and group_label.lower() in (
            REPRESENTATION_PANEL_ONLY_GROUP_LABELS
        ):
            return True

        label = action.label
        if label and label.lower() in REPRESENTATION_PANEL_ONLY_GROUP_LABELS:
            return True

        return False

    def _prepare_entities_cache(
        self,
        project_name: str,
        entity_type: str,
        version_context_by_id: dict[str, dict[str, Any]],
        repre_context_by_id: dict[str, dict[str, Any]],
        folder_ids: Optional[set[str]] = None,
    ):
        if entity_type == "folder" and folder_ids:
            folder_entities = list(
                ayon_api.get_folders(project_name, folder_ids=folder_ids)
            )
            folders_by_id = {fe["id"]: fe for fe in folder_entities}
            project_entity = ayon_api.get_project(project_name)
            return SelectionEntitiesCache(
                project_name,
                project_entity=project_entity,
                folders_by_id=folders_by_id,
            )

        project_entity = None
        folders_by_id = {}
        products_by_id = {}
        versions_by_id = {}
        representations_by_id = {}
        for context in version_context_by_id.values():
            if project_entity is None:
                project_entity = context["project"]
            folder_entity = context["folder"]
            product_entity = context["product"]
            version_entity = context["version"]
            folders_by_id[folder_entity["id"]] = folder_entity
            products_by_id[product_entity["id"]] = product_entity
            versions_by_id[version_entity["id"]] = version_entity

        for context in repre_context_by_id.values():
            repre_entity = context["representation"]
            representations_by_id[repre_entity["id"]] = repre_entity

        representation_ids_by_version_id = {}
        if entity_type == "version":
            representation_ids_by_version_id = {
                version_id: set()
                for version_id in versions_by_id
            }
            for context in repre_context_by_id.values():
                repre_entity = context["representation"]
                version_id = repre_entity["versionId"]
                representation_ids_by_version_id[version_id].add(
                    repre_entity["id"]
                )

        return SelectionEntitiesCache(
            project_name,
            project_entity=project_entity,
            folders_by_id=folders_by_id,
            products_by_id=products_by_id,
            versions_by_id=versions_by_id,
            representations_by_id=representations_by_id,
            representation_ids_by_version_id=(
                representation_ids_by_version_id
            ),
        )

    def _trigger_version_loader(
        self,
        loader,
        options,
        project_name,
        version_ids,
        event_id,
    ):
        """Trigger version loader.

        This triggers 'load' method of 'ProductLoaderPlugin' for given version
        ids.

        Note:
            Even when the plugin is 'ProductLoaderPlugin' it actually expects
                versions and should be named 'VersionLoaderPlugin'. Because it
                is planned to refactor load system and introduce
                'LoaderAction' plugins it is not relevant to change it
                anymore.

        Args:
            loader (ProductLoaderPlugin): Loader plugin to use.
            options (dict): Option values for loader.
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            event_id (str): Event ID for progress tracking.
        """

        project_entity = ayon_api.get_project(project_name)

        version_entities = list(
            ayon_api.get_versions(project_name, version_ids=version_ids)
        )
        product_ids = {v["productId"] for v in version_entities}
        product_entities = ayon_api.get_products(
            project_name, product_ids=product_ids
        )
        product_entities_by_id = {p["id"]: p for p in product_entities}
        folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        folder_entities = ayon_api.get_folders(
            project_name, folder_ids=folder_ids
        )
        folder_entities_by_id = {f["id"]: f for f in folder_entities}
        product_contexts = []
        for version_entity in version_entities:
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            product_contexts.append(
                {
                    "project": project_entity,
                    "folder": folder_entity,
                    "product": product_entity,
                    "version": version_entity,
                }
            )

        return self._load_products_by_loader(
            loader, product_contexts, options, event_id
        )

    def _trigger_representation_loader(
        self,
        loader,
        options,
        project_name,
        representation_ids,
        event_id,
    ):
        """Trigger representation loader.

        This triggers 'load' method of 'LoaderPlugin' for given representation
            ids. For that are prepared contexts for each representation, with
            all parent entities.

        Args:
            loader (LoaderPlugin): Loader plugin to use.
            options (dict): Option values for loader.
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.
            event_id (str): Event ID for progress tracking.
        """

        project_entity = ayon_api.get_project(project_name)
        repre_entities = list(
            ayon_api.get_representations(
                project_name, representation_ids=representation_ids
            )
        )
        version_ids = {r["versionId"] for r in repre_entities}
        version_entities = ayon_api.get_versions(
            project_name, version_ids=version_ids
        )
        version_entities_by_id = {v["id"]: v for v in version_entities}
        product_ids = {v["productId"] for v in version_entities_by_id.values()}
        product_entities = ayon_api.get_products(
            project_name, product_ids=product_ids
        )
        product_entities_by_id = {p["id"]: p for p in product_entities}
        folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        folder_entities = ayon_api.get_folders(
            project_name, folder_ids=folder_ids
        )
        folder_entities_by_id = {f["id"]: f for f in folder_entities}
        repre_contexts = []
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = version_entities_by_id[version_id]
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            repre_contexts.append(
                {
                    "project": project_entity,
                    "folder": folder_entity,
                    "product": product_entity,
                    "version": version_entity,
                    "representation": repre_entity,
                }
            )

        return self._load_representations_by_loader(
            loader, repre_contexts, options, event_id
        )

    def _load_representations_by_loader(
        self,
        loader,
        repre_contexts,
        options,
        event_id,
    ):
        """Loops through list of repre_contexts and loads them with one loader

        Args:
            loader (LoaderPlugin): Loader plugin to use.
            repre_contexts (list[dict]): Full info about selected
                representations, containing repre, version, product, folder
                and project entities.
            options (dict): Data from options.
            event_id (str): Event ID for progress tracking.
        """

        error_info = []
        total_count = len(repre_contexts)
        for idx, repre_context in enumerate(repre_contexts):
            # Emit progress event
            if event_id and total_count > 0:
                progress = int(((idx + 1) / total_count) * 100)
                self._controller.emit_event(
                    "load.progress",
                    {
                        "id": event_id,
                        "progress": progress,
                        "current": idx + 1,
                        "total": total_count,
                    },
                    ACTIONS_MODEL_SENDER,
                )
            version_entity = repre_context["version"]
            version = version_entity["version"]
            if version < 0:
                version = "Hero"
            try:
                # Pass event_id in options so loaders can emit progress events
                loader_options = dict(options) if options else {}
                loader_options["event_id"] = event_id
                load_with_repre_context(
                    loader, repre_context, options=loader_options
                )

            except IncompatibleLoaderError as exc:
                print(exc)
                error_info.append(
                    (
                        "Incompatible Loader",
                        None,
                        repre_context["representation"]["name"],
                        repre_context["product"]["name"],
                        version,
                    )
                )

            except Exception as exc:
                formatted_traceback = None
                if not isinstance(exc, LoadError):
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    formatted_traceback = "".join(
                        traceback.format_exception(
                            exc_type, exc_value, exc_traceback
                        )
                    )

                error_info.append(
                    (
                        str(exc),
                        formatted_traceback,
                        repre_context["representation"]["name"],
                        repre_context["product"]["name"],
                        version,
                    )
                )
        return error_info

    def _load_products_by_loader(
        self,
        loader,
        version_contexts,
        options,
        event_id,
    ):
        """Triggers load with ProductLoader type of loaders.

        Warning:
            Plugin is named 'ProductLoader' but version is passed to context
                too.

        Args:
            loader (ProductLoader): Loader used to load.
            version_contexts (list[dict[str, Any]]): For context for each
                version.
            options (dict[str, Any]): Options for loader that user could fill.
            event_id (str): Event ID for progress tracking.
        """
        from qtpy import QtWidgets

        error_info = []
        total_count = len(version_contexts)

        if loader.is_multiple_contexts_compatible:
            product_names = []
            for context in version_contexts:
                product_name = context.get("product", {}).get("name") or "N/A"
                product_names.append(product_name)

            # Emit progress for batch load
            if event_id and total_count > 0:
                self._controller.emit_event(
                    "load.progress",
                    {
                        "id": event_id,
                        "progress": 50,
                        "current": 0,
                        "total": total_count,
                    },
                    ACTIONS_MODEL_SENDER,
                )

            try:
                # Pass event_id in options so loaders can emit progress events
                loader_options = dict(options) if options else {}
                loader_options["event_id"] = event_id
                load_with_product_contexts(
                    loader, version_contexts, options=loader_options
                )

                # Emit completion progress
                if event_id and total_count > 0:
                    self._controller.emit_event(
                        "load.progress",
                        {
                            "id": event_id,
                            "progress": 100,
                            "current": total_count,
                            "total": total_count,
                        },
                        ACTIONS_MODEL_SENDER,
                    )
                    # Process Qt events to update UI for final progress
                    app = QtWidgets.QApplication.instance()
                    if app:
                        app.processEvents()
            except Exception as exc:
                formatted_traceback = None
                if not isinstance(exc, LoadError):
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    formatted_traceback = "".join(
                        traceback.format_exception(
                            exc_type, exc_value, exc_traceback
                        )
                    )
                error_info.append(
                    (
                        str(exc),
                        formatted_traceback,
                        None,
                        ", ".join(product_names),
                        None,
                    )
                )
        else:
            for idx, version_context in enumerate(version_contexts):
                # Emit progress event
                if event_id and total_count > 0:
                    progress = int(((idx + 1) / total_count) * 100)
                    self._controller.emit_event(
                        "load.progress",
                        {
                            "id": event_id,
                            "progress": progress,
                            "current": idx + 1,
                            "total": total_count,
                        },
                        ACTIONS_MODEL_SENDER,
                    )

                product_name = (
                    version_context.get("product", {}).get("name") or "N/A"
                )
                try:
                    # Pass event_id so loaders can emit progress events
                    loader_options = dict(options) if options else {}
                    loader_options["event_id"] = event_id
                    load_with_product_context(
                        loader, version_context, options=loader_options
                    )

                except Exception as exc:
                    formatted_traceback = None
                    if not isinstance(exc, LoadError):
                        exc_type, exc_value, exc_traceback = sys.exc_info()
                        formatted_traceback = "".join(
                            traceback.format_exception(
                                exc_type, exc_value, exc_traceback
                            )
                        )

                    error_info.append(
                        (
                            str(exc),
                            formatted_traceback,
                            None,
                            product_name,
                            None,
                        )
                    )

        return error_info
