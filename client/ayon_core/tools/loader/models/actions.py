import sys
import traceback
import inspect
import collections
import uuid

import ayon_api

from ayon_core.lib import NestedCacheItem
from ayon_core.pipeline.load import (
    discover_loader_plugins,
    ProductLoaderPlugin,
    filter_repre_contexts_by_loader,
    get_loader_identifier,
    load_with_repre_context,
    load_with_product_context,
    load_with_product_contexts,
    LoadError,
    IncompatibleLoaderError,
)
from ayon_core.tools.loader.abstract import ActionItem

ACTIONS_MODEL_SENDER = "actions.model"
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
        self._controller = controller
        self._current_context_project = NOT_SET
        self._loaders_by_identifier = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime)
        self._product_loaders = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime)
        self._repre_loaders = NestedCacheItem(
            levels=1, lifetime=self.loaders_cache_lifetime)

    def reset(self):
        """Reset the model with all cached items."""

        self._current_context_project = NOT_SET
        self._loaders_by_identifier.reset()
        self._product_loaders.reset()
        self._repre_loaders.reset()

    def get_versions_action_items(self, project_name, version_ids):
        """Get action items for given version ids.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.

        Returns:
            list[ActionItem]: List of action items.
        """

        (
            version_context_by_id,
            repre_context_by_id
        ) = self._contexts_for_versions(
            project_name,
            version_ids
        )
        return self._get_action_items_for_contexts(
            project_name,
            version_context_by_id,
            repre_context_by_id
        )

    def get_representations_action_items(
        self, project_name, representation_ids
    ):
        """Get action items for given representation ids.

        Args:
            project_name (str): Project name.
            representation_ids (Iterable[str]): Representation ids.

        Returns:
            list[ActionItem]: List of action items.
        """

        (
            product_context_by_id,
            repre_context_by_id
        ) = self._contexts_for_representations(
            project_name,
            representation_ids
        )
        return self._get_action_items_for_contexts(
            project_name,
            product_context_by_id,
            repre_context_by_id
        )

    def trigger_action_item(
        self,
        identifier,
        options,
        project_name,
        version_ids,
        representation_ids
    ):
        """Trigger action by identifier.

        Triggers the action by identifier for given contexts.

        Triggers events "load.started" and "load.finished". Finished event
            also contains "error_info" key with error information if any
            happened.

        Args:
            identifier (str): Loader identifier.
            options (dict[str, Any]): Loader option values.
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            representation_ids (Iterable[str]): Representation ids.
        """

        event_data = {
            "identifier": identifier,
            "id": uuid.uuid4().hex,
        }
        self._controller.emit_event(
            "load.started",
            event_data,
            ACTIONS_MODEL_SENDER,
        )
        loader = self._get_loader_by_identifier(project_name, identifier)
        if representation_ids is not None:
            error_info = self._trigger_representation_loader(
                loader,
                options,
                project_name,
                representation_ids,
            )
        elif version_ids is not None:
            error_info = self._trigger_version_loader(
                loader,
                options,
                project_name,
                version_ids,
            )
        else:
            raise NotImplementedError(
                "Invalid arguments to trigger action item")

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
                "color": getattr(loader, "color", None) or "white"
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
        project_name,
        folder_ids=None,
        product_ids=None,
        version_ids=None,
        representation_ids=None,
        repre_name=None,
    ):
        label = self._get_action_label(loader)
        if repre_name:
            label = "{} ({})".format(label, repre_name)
        return ActionItem(
            get_loader_identifier(loader),
            label=label,
            icon=self._get_action_icon(loader),
            tooltip=self._get_action_tooltip(loader),
            options=loader.get_options(contexts),
            order=loader.order,
            project_name=project_name,
            folder_ids=folder_ids,
            product_ids=product_ids,
            version_ids=version_ids,
            representation_ids=representation_ids,
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
        if not project_name and not version_ids:
            return version_context_by_id, repre_context_by_id

        version_entities = ayon_api.get_versions(
            project_name, version_ids=version_ids
        )
        version_entities_by_id = {}
        version_entities_by_product_id = collections.defaultdict(list)
        for version_entity in version_entities:
            version_id = version_entity["id"]
            product_id = version_entity["productId"]
            version_entities_by_id[version_id] = version_entity
            version_entities_by_product_id[product_id].append(version_entity)

        _product_ids = set(version_entities_by_product_id.keys())
        _product_entities = ayon_api.get_products(
            project_name, product_ids=_product_ids
        )
        product_entities_by_id = {p["id"]: p for p in _product_entities}

        _folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        _folder_entities = ayon_api.get_folders(
            project_name, folder_ids=_folder_ids
        )
        folder_entities_by_id = {f["id"]: f for f in _folder_entities}

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

        repre_entities = ayon_api.get_representations(
            project_name, version_ids=version_ids)
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

        product_context_by_id = {}
        repre_context_by_id = {}
        if not project_name and not repre_ids:
            return product_context_by_id, repre_context_by_id

        repre_entities = list(ayon_api.get_representations(
            project_name, representation_ids=repre_ids
        ))
        version_ids = {r["versionId"] for r in repre_entities}
        version_entities = ayon_api.get_versions(
            project_name, version_ids=version_ids
        )
        version_entities_by_id = {
            v["id"]: v for v in version_entities
        }

        product_ids = {v["productId"] for v in version_entities_by_id.values()}
        product_entities = ayon_api.get_products(
            project_name, product_ids=product_ids
        )
        product_entities_by_id = {
            p["id"]: p for p in product_entities
        }

        folder_ids = {p["folderId"] for p in product_entities_by_id.values()}
        folder_entities = ayon_api.get_folders(
            project_name, folder_ids=folder_ids
        )
        folder_entities_by_id = {
            f["id"]: f for f in folder_entities
        }

        project_entity = ayon_api.get_project(project_name)

        for product_id, product_entity in product_entities_by_id.items():
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            product_context_by_id[product_id] = {
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
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
        return product_context_by_id, repre_context_by_id

    def _get_action_items_for_contexts(
        self,
        project_name,
        version_context_by_id,
        repre_context_by_id
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
            for repre_name, repre_contexts in repre_contexts_by_name.items():
                filtered_repre_contexts = filter_repre_contexts_by_loader(
                    repre_contexts, loader)
                if not filtered_repre_contexts:
                    continue

                repre_ids = set()
                repre_version_ids = set()
                repre_product_ids = set()
                repre_folder_ids = set()
                for repre_context in filtered_repre_contexts:
                    repre_ids.add(repre_context["representation"]["id"])
                    repre_product_ids.add(repre_context["product"]["id"])
                    repre_version_ids.add(repre_context["version"]["id"])
                    repre_folder_ids.add(repre_context["folder"]["id"])

                item = self._create_loader_action_item(
                    loader,
                    repre_contexts,
                    project_name=project_name,
                    folder_ids=repre_folder_ids,
                    product_ids=repre_product_ids,
                    version_ids=repre_version_ids,
                    representation_ids=repre_ids,
                    repre_name=repre_name,
                )
                action_items.append(item)

        # Product Loaders.
        version_ids = set(version_context_by_id.keys())
        product_folder_ids = set()
        product_ids = set()
        for product_context in version_context_by_id.values():
            product_ids.add(product_context["product"]["id"])
            product_folder_ids.add(product_context["folder"]["id"])

        version_contexts = list(version_context_by_id.values())
        for loader in product_loaders:
            item = self._create_loader_action_item(
                loader,
                version_contexts,
                project_name=project_name,
                folder_ids=product_folder_ids,
                product_ids=product_ids,
                version_ids=version_ids,
            )
            action_items.append(item)

        action_items.sort(key=self._actions_sorter)
        return action_items

    def _trigger_version_loader(
        self,
        loader,
        options,
        project_name,
        version_ids,
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
        """

        project_entity = ayon_api.get_project(project_name)

        version_entities = list(ayon_api.get_versions(
            project_name, version_ids=version_ids
        ))
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
            product_contexts.append({
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
            })

        return self._load_products_by_loader(
            loader, product_contexts, options
        )

    def _trigger_representation_loader(
        self,
        loader,
        options,
        project_name,
        representation_ids,
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
        """

        project_entity = ayon_api.get_project(project_name)
        repre_entities = list(ayon_api.get_representations(
            project_name, representation_ids=representation_ids
        ))
        version_ids = {r["versionId"] for r in repre_entities}
        version_entities = ayon_api.get_versions(
            project_name, version_ids=version_ids
        )
        version_entities_by_id = {v["id"]: v for v in version_entities}
        product_ids = {
            v["productId"] for v in version_entities_by_id.values()
        }
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
            repre_contexts.append({
                "project": project_entity,
                "folder": folder_entity,
                "product": product_entity,
                "version": version_entity,
                "representation": repre_entity,
            })

        return self._load_representations_by_loader(
            loader, repre_contexts, options
        )

    def _load_representations_by_loader(self, loader, repre_contexts, options):
        """Loops through list of repre_contexts and loads them with one loader

        Args:
            loader (LoaderPlugin): Loader plugin to use.
            repre_contexts (list[dict]): Full info about selected
                representations, containing repre, version, product, folder
                and project entities.
            options (dict): Data from options.
        """

        error_info = []
        for repre_context in repre_contexts:
            version_entity = repre_context["version"]
            version = version_entity["version"]
            if version < 0:
                version = "Hero"
            try:
                load_with_repre_context(
                    loader,
                    repre_context,
                    options=options
                )

            except IncompatibleLoaderError as exc:
                print(exc)
                error_info.append((
                    "Incompatible Loader",
                    None,
                    repre_context["representation"]["name"],
                    repre_context["product"]["name"],
                    version
                ))

            except Exception as exc:
                formatted_traceback = None
                if not isinstance(exc, LoadError):
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    formatted_traceback = "".join(traceback.format_exception(
                        exc_type, exc_value, exc_traceback
                    ))

                error_info.append((
                    str(exc),
                    formatted_traceback,
                    repre_context["representation"]["name"],
                    repre_context["product"]["name"],
                    version
                ))
        return error_info

    def _load_products_by_loader(self, loader, version_contexts, options):
        """Triggers load with ProductLoader type of loaders.

        Warning:
            Plugin is named 'ProductLoader' but version is passed to context
                too.

        Args:
            loader (ProductLoader): Loader used to load.
            version_contexts (list[dict[str, Any]]): For context for each
                version.
            options (dict[str, Any]): Options for loader that user could fill.
        """

        error_info = []
        if loader.is_multiple_contexts_compatible:
            product_names = []
            for context in version_contexts:
                product_name = context.get("product", {}).get("name") or "N/A"
                product_names.append(product_name)
            try:
                load_with_product_contexts(
                    loader,
                    version_contexts,
                    options=options
                )

            except Exception as exc:
                formatted_traceback = None
                if not isinstance(exc, LoadError):
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    formatted_traceback = "".join(traceback.format_exception(
                        exc_type, exc_value, exc_traceback
                    ))
                error_info.append((
                    str(exc),
                    formatted_traceback,
                    None,
                    ", ".join(product_names),
                    None
                ))
        else:
            for version_context in version_contexts:
                product_name = (
                    version_context.get("product", {}).get("name") or "N/A"
                )
                try:
                    load_with_product_context(
                        loader,
                        version_context,
                        options=options
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

                    error_info.append((
                        str(exc),
                        formatted_traceback,
                        None,
                        product_name,
                        None
                    ))

        return error_info
