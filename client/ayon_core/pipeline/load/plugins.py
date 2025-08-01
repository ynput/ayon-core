"""Plugins for loading representations and products into host applications."""
from __future__ import annotations

from abc import abstractmethod
import logging
import os
from typing import Any, Optional, Type

from ayon_core.pipeline.plugin_discover import (
    deregister_plugin,
    deregister_plugin_path,
    discover,
    register_plugin,
    register_plugin_path,
)
from ayon_core.settings import get_project_settings

from .utils import get_representation_path_from_context


class LoaderPlugin(list):
    """Load representation into host application"""

    product_types: set[str] = set()
    product_base_types: Optional[set[str]] = None
    representations = set()
    extensions = {"*"}
    order = 0
    is_multiple_contexts_compatible = False
    enabled = True

    options = []

    log = logging.getLogger("ProductLoader")
    log.propagate = True

    @classmethod
    def apply_settings(cls, project_settings):
        host_name = os.environ.get("AYON_HOST_NAME")
        plugin_type = "load"
        plugin_type_settings = (
            project_settings
            .get(host_name, {})
            .get(plugin_type, {})
        )
        global_type_settings = (
            project_settings
            .get("core", {})
            .get(plugin_type, {})
        )
        if not global_type_settings and not plugin_type_settings:
            return

        plugin_name = cls.__name__

        plugin_settings = None
        # Look for plugin settings in host specific settings
        if plugin_name in plugin_type_settings:
            plugin_settings = plugin_type_settings[plugin_name]

        # Look for plugin settings in global settings
        elif plugin_name in global_type_settings:
            plugin_settings = global_type_settings[plugin_name]

        if not plugin_settings:
            return

        print(f">>> We have preset for {plugin_name}")
        for option, value in plugin_settings.items():
            if option == "enabled" and value is False:
                print("  - is disabled by preset")
            else:
                print(f"  - setting `{option}`: `{value}`")
            setattr(cls, option, value)

    @classmethod
    def has_valid_extension(cls, repre_entity):
        """Has representation document valid extension for loader.

        Args:
            repre_entity (dict[str, Any]): Representation entity.

        Returns:
             bool: Representation has valid extension
        """
        if "*" in cls.extensions:
            return True

        # Get representation main file extension from 'context'
        repre_context = repre_entity.get("context") or {}
        ext = repre_context.get("ext")
        if not ext:
            # Legacy way how to get extensions
            path = repre_entity.get("attrib", {}).get("path")
            if not path:
                cls.log.info(
                    "Representation doesn't have known source of extension"
                    " information."
                )
                return False

            cls.log.debug("Using legacy source of extension from path.")
            ext = os.path.splitext(path)[-1].lstrip(".")

        # If representation does not have extension then can't be valid
        if not ext:
            return False

        valid_extensions_low = {ext.lower() for ext in cls.extensions}
        return ext.lower() in valid_extensions_low

    @classmethod
    def is_compatible_loader(cls, context):
        """Return whether a loader is compatible with a context.

        On override make sure it is overridden as class or static method.

        This checks the product type and the representation for the given
        loader plugin.

        Args:
            context (dict[str, Any]): Documents of context for which should
                be loader used.

        Returns:
            bool: Is loader compatible for context.
        """

        plugin_repre_names = cls.get_representations()

        # If the product base type isn't defined on the loader plugin,
        # then we will use the product types.
        plugin_product_filter = cls.product_base_types
        if plugin_product_filter is None:
            plugin_product_filter = cls.product_types

        if plugin_product_filter:
            plugin_product_filter = set(plugin_product_filter)

        repre_entity = context.get("representation")
        product_entity = context["product"]

        # If no representation names, product types or extensions are defined
        # then loader is not compatible with any context.
        if (
            not plugin_repre_names
            or not plugin_product_filter
            or not cls.extensions
        ):
            return False

        # If no representation entity is provided then loader is not
        # compatible with context.
        if not repre_entity:
            return False

        # Check the compatibility with the representation names.
        plugin_repre_names = set(plugin_repre_names)
        if (
            "*" not in plugin_repre_names
            and repre_entity["name"] not in plugin_repre_names
        ):
            return False

        # Check the compatibility with the extension of the representation.
        if not cls.has_valid_extension(repre_entity):
            return False

        product_type = product_entity.get("productType")
        product_base_type = product_entity.get("productBaseType")

        # Use product base type if defined, otherwise use product type.
        product_filter = product_base_type
        # If there is no product base type defined in the product entity,
        # then we will use the product type.
        if product_filter is None:
            product_filter = product_type

        # If wildcard is used in product types or base types,
        # then we will consider the loader compatible with any product type.
        if "*" in plugin_product_filter:
            return True

        # compatibility with legacy loader
        if cls.product_base_types is None and product_base_type:
            cls.log.error(
                f"Loader {cls.__name__} is doesn't specify "
                "`product_base_types` but product entity has "
                f"`productBaseType` defined as `{product_base_type}`. "
            )

        return product_filter in plugin_product_filter

    @classmethod
    def get_representations(cls):
        """Representation names with which is plugin compatible.

        Empty set makes the plugin incompatible with any representation. To
            allow compatibility with all representations use '{"*"}'.

        Returns:
            set[str]: Names with which is plugin compatible.

        """
        return cls.representations

    @classmethod
    def filepath_from_context(cls, context):
        return get_representation_path_from_context(context)

    def load(self, context, name=None, namespace=None, options=None):
        """Load asset via database

        Arguments:
            context (dict): Full parenthood of representation to load
            name (str, optional): Use pre-defined name
            namespace (str, optional): Use pre-defined namespace
            options (dict, optional): Additional settings dictionary

        """
        raise NotImplementedError("Loader.load() must be "
                                  "implemented by subclass")

    def update(self, container, context):
        """Update `container` to `representation`

        Args:
            container (avalon-core:container-1.0): Container to update,
                from `host.ls()`.
            context (dict): Update the container to this representation.

        """
        raise NotImplementedError("Loader.update() must be "
                                  "implemented by subclass")

    def remove(self, container):
        """Remove a container

        Arguments:
            container (avalon-core:container-1.0): Container to remove,
                from `host.ls()`.

        Returns:
            bool: Whether the container was deleted

        """
        raise NotImplementedError("Loader.remove() must be "
                                  "implemented by subclass")

    @classmethod
    def get_options(cls, contexts):
        """Returns static (cls) options or could collect from 'contexts'.

        Args:
            contexts (list): of repre or product contexts
        Returns:
            (list)
        """
        return cls.options or []

    @classmethod
    def get_representation_name_aliases(cls, representation_name: str):
        """Return representation names to which switching is allowed from
        the input representation name, like an alias replacement of the input
        `representation_name`.

        For example, to allow an automated switch on update from representation
        `ma` to `mb` or `abc`, then when `representation_name` is `ma` return:
            ["mb", "abc"]

        The order of the names in the returned representation names is
        important, because the first one existing under the new version will
        be chosen.

        Returns:
            List[str]: Representation names switching to is allowed on update
              if the input representation name is not found on the new version.
        """
        return []


class ProductLoaderPlugin(LoaderPlugin):
    """Load product into host application
    Arguments:
        context (dict): avalon-core:context-1.0
        name (str, optional): Use pre-defined name
        namespace (str, optional): Use pre-defined namespace
    """


class LoaderHookPlugin:
    """Plugin that runs before and post specific Loader in 'loaders'

    Should be used as non-invasive method to enrich core loading process.
    Any studio might want to modify loaded data before or after
    they are loaded without need to override existing core plugins.

    The post methods are called after the loader's methods and receive the
    return value of the loader's method as `result` argument.
    """
    order = 0

    @classmethod
    @abstractmethod
    def is_compatible(cls, Loader: Type[LoaderPlugin]) -> bool:
        pass

    @abstractmethod
    def pre_load(
        self,
        plugin: LoaderPlugin,
        context: dict,
        name: Optional[str],
        namespace: Optional[str],
        options: Optional[dict],
    ):
        pass

    @abstractmethod
    def post_load(
        self,
        plugin: LoaderPlugin,
        result: Any,
        context: dict,
        name: Optional[str],
        namespace: Optional[str],
        options: Optional[dict],
    ):
        pass

    @abstractmethod
    def pre_update(
        self,
        plugin: LoaderPlugin,
        container: dict,  # (ayon:container-3.0)
        context: dict,
    ):
        pass

    @abstractmethod
    def post_update(
        self,
        plugin: LoaderPlugin,
        result: Any,
        container: dict,  # (ayon:container-3.0)
        context: dict,
    ):
        pass

    @abstractmethod
    def pre_remove(
        self,
        plugin: LoaderPlugin,
        container: dict,  # (ayon:container-3.0)
    ):
        pass

    @abstractmethod
    def post_remove(
        self,
        plugin: LoaderPlugin,
        result: Any,
        container: dict,  # (ayon:container-3.0)
    ):
        pass


def discover_loader_plugins(project_name=None):
    from ayon_core.lib import Logger
    from ayon_core.pipeline import get_current_project_name

    log = Logger.get_logger("LoaderDiscover")
    if not project_name:
        project_name = get_current_project_name()
    project_settings = get_project_settings(project_name)
    plugins = discover(LoaderPlugin)
    hooks = discover(LoaderHookPlugin)
    sorted_hooks = sorted(hooks, key=lambda hook: hook.order)
    for plugin in plugins:
        try:
            plugin.apply_settings(project_settings)
        except Exception:
            log.warning(
                f"Failed to apply settings to loader {plugin.__name__}",
                exc_info=True
            )
        compatible_hooks = []
        for hook_cls in sorted_hooks:
            if hook_cls.is_compatible(plugin):
                compatible_hooks.append(hook_cls)
        add_hooks_to_loader(plugin, compatible_hooks)
    return plugins


def add_hooks_to_loader(
    loader_class: LoaderPlugin, compatible_hooks: list[Type[LoaderHookPlugin]]
) -> None:
    """Monkey patch method replacing Loader.load|update|remove methods

    It wraps applicable loaders with pre/post hooks. Discovery is called only
    once per loaders discovery.
    """
    loader_class._load_hooks = compatible_hooks

    def wrap_method(method_name: str):
        original_method = getattr(loader_class, method_name)

        def wrapped_method(self, *args, **kwargs):
            # Call pre_<method_name> on all hooks
            pre_hook_name = f"pre_{method_name}"

            hooks: list[LoaderHookPlugin] = []
            for cls in loader_class._load_hooks:
                hook = cls()  # Instantiate the hook
                hooks.append(hook)
                pre_hook = getattr(hook, pre_hook_name, None)
                if callable(pre_hook):
                    pre_hook(self, *args, **kwargs)
            # Call original method
            result = original_method(self, *args, **kwargs)
            # Call post_<method_name> on all hooks
            post_hook_name = f"post_{method_name}"
            for hook in hooks:
                post_hook = getattr(hook, post_hook_name, None)
                if callable(post_hook):
                    post_hook(self, result, *args, **kwargs)

            return result

        setattr(loader_class, method_name, wrapped_method)

    for method in ("load", "update", "remove"):
        if hasattr(loader_class, method):
            wrap_method(method)


def register_loader_plugin(plugin):
    return register_plugin(LoaderPlugin, plugin)


def deregister_loader_plugin(plugin):
    deregister_plugin(LoaderPlugin, plugin)


def deregister_loader_plugin_path(path):
    deregister_plugin_path(LoaderPlugin, path)


def register_loader_plugin_path(path):
    return register_plugin_path(LoaderPlugin, path)


def register_loader_hook_plugin(plugin):
    return register_plugin(LoaderHookPlugin, plugin)


def deregister_loader_hook_plugin(plugin):
    deregister_plugin(LoaderHookPlugin, plugin)


def register_loader_hook_plugin_path(path):
    return register_plugin_path(LoaderHookPlugin, path)


def deregister_loader_hook_plugin_path(path):
    deregister_plugin_path(LoaderHookPlugin, path)
