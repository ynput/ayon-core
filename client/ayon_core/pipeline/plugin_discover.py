from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import os
from pathlib import Path
import platform
import traceback
import typing

from ayon_core.lib import Logger
from ayon_core.lib.python_module_tools import (
    modules_from_path,
    classes_from_module,
)

if typing.TYPE_CHECKING:
    from types import ModuleType
    from ayon_core.lib.python_module_tools import ModulesResult

log = Logger.get_logger(__name__)

IS_WINDOWS = platform.system().lower() == "windows"


@dataclass
class SuperClassDef:
    superclass: type
    paths: list[str] = field(default_factory=list)
    classes: list[type] = field(default_factory=list)


class DiscoverResult:
    """Result of Plug-ins discovery of a single superclass type.

    Stores discovered, duplicated, ignored and abstract plugins and file paths
    which crashed on execution of file.
    """

    def __init__(self, superclass):
        self.superclass = superclass
        self.plugins = []
        self.crashed_file_paths = {}
        self.duplicated_plugins = []
        self.abstract_plugins = []
        self.ignored_plugins = set()
        # Store loaded modules to keep them in memory
        self._modules = set()

    def __iter__(self):
        for plugin in self.plugins:
            yield plugin

    def __getitem__(self, item):
        return self.plugins[item]

    def __setitem__(self, item, value):
        self.plugins[item] = value

    def add_module(self, module: ModuleType) -> None:
        """Add dynamically loaded python module to keep it in memory."""
        self._modules.add(module)

    def ignore_plugins(self, plugins: list[type]) -> None:
        """Add plugins to be ignored from the result."""
        for plugin in plugins:
            if plugin in self.ignored_plugins:
                continue
            if plugin in self.plugins:
                self.plugins.remove(plugin)
            self.ignored_plugins.add(plugin)

    def remove_duplicates(self) -> None:
        """Remove duplicated plugins from the result."""
        plugin_names: set[str] = set()
        for plugin in tuple(self.plugins):
            class_name = plugin.__name__
            if class_name in plugin_names:
                self.plugins.remove(plugin)
                self.duplicated_plugins.append(plugin)
                continue
            plugin_names.add(class_name)

    def get_report(
        self,
        only_errors: bool = True,
        exc_info: bool = True,
        full_report: bool = False,
    ) -> str:
        lines = []
        if not only_errors:
            # Successfully discovered plugins
            if self.plugins or full_report:
                lines.append(f"*** Discovered {len(self.plugins)} plugins")
                for cls in self.plugins:
                    lines.append(f"- {cls.__name__}")

            # Plugin that were defined to be ignored
            if self.ignored_plugins or full_report:
                lines.append(
                    f"*** Ignored plugins {len(self.ignored_plugins)}"
                )
                for cls in self.ignored_plugins:
                    lines.append(f"- {cls.__name__}")

        # Abstract classes
        if self.abstract_plugins or full_report:
            lines.append(
                f"*** Discovered {len(self.abstract_plugins)}"
                " abstract plugins"
            )
            for cls in self.abstract_plugins:
                lines.append(f"- {cls.__name__}")

        # Abstract classes
        if self.duplicated_plugins or full_report:
            lines.append(
                f"*** There were {len(self.duplicated_plugins)}"
                " duplicated plugins"
            )
            for cls in self.duplicated_plugins:
                lines.append(f"- {cls.__name__}")

        if self.crashed_file_paths or full_report:
            lines.append(
                f"*** Failed to load {len(self.crashed_file_paths)} files"
            )
            for path, exc_info_args in self.crashed_file_paths.items():
                lines.append(f"- {path}")
                if exc_info:
                    lines.append(10 * "*")
                    lines.extend(traceback.format_exception(*exc_info_args))
                    lines.append(10 * "*")

        return "\n".join(lines)

    def log_report(
        self, only_errors: bool=True, exc_info: bool=True
    ) -> None:
        report = self.get_report(only_errors, exc_info)
        if report:
            log.info(report)


def discover_plugins_with_defs(
    superclass_defs: list[SuperClassDef],
) -> dict[type, DiscoverResult]:
    """Find and return subclasses.

    Args:
        superclass_defs (list[SuperClassDef]): List of superclasses with
            their paths and classes to discover.

    Returns:
        dict[type, DiscoverResult]: Discover result by superclass.

    """
    normalized_paths: dict[Path, str] = {}
    paths_by_superclass: dict[type, set[str]] = {}
    results: dict[type, DiscoverResult] = {}
    for superclass_def in superclass_defs:
        superclass_paths = set()
        for path in superclass_def.paths:
            path = Path(path)
            if not path.is_absolute():
                log.warning(
                    "Relative paths are not allowed for"
                    f" security reasons '{path}'."
                )
                continue

            if not path.exists():
                continue

            unique_path = path.as_posix()
            if IS_WINDOWS:
                unique_path = unique_path.lower()
            normalized_paths[path] = unique_path
            superclass_paths.add(unique_path)

        result = DiscoverResult(superclass_def.superclass)
        result.plugins.extend(superclass_def.classes)

        paths_by_superclass[superclass_def.superclass] = superclass_paths
        results[superclass_def.superclass] = result

    for path, unique_path in normalized_paths.items():
        import_result: ModulesResult = modules_from_path(path)
        for item in import_result.crashed:
            for superclass, superclass_paths in paths_by_superclass.items():
                if unique_path in superclass_paths:
                    results[superclass].crashed_file_paths[item.filepath] = (
                        item.exc_info
                    )

        for item in import_result.modules:
            for superclass, superclass_paths in paths_by_superclass.items():
                if unique_path not in superclass_paths:
                    continue

                sc_result = results[superclass]
                sc_result.add_module(item.module)
                for cls in classes_from_module(superclass, item.module):
                    if cls is superclass:
                        continue
                    # Class has defined 'skip_discovery = True'
                    skip_discovery = cls.__dict__.get("skip_discovery")
                    if skip_discovery is True:
                        continue
                    if inspect.isabstract(cls):
                        sc_result.abstract_plugins.append(cls)
                        continue
                    sc_result.plugins.append(cls)
    return results


def discover_plugins(
    base_class: type,
    paths: list[str] | None = None,
    classes: list[type] | None = None,
    ignored_classes: list[type] | None = None,
    allow_duplicates: bool = True,
) -> DiscoverResult:
    """Find and return subclasses of `superclass`

    Args:
        base_class (type): Class which determines discovered subclasses.
        paths (list[str] | None): List of paths to look for plug-ins.
        classes (list[str] | None): List of classes to filter.
        ignored_classes (list[type]): List of classes that won't be added to
            the output plugins.
        allow_duplicates (bool): Validate class name duplications.

    Returns:
        DiscoverResult: Object holding successfully
            discovered plugins, ignored plugins, plugins with missing
            abstract implementation and duplicated plugin.

    """
    result = discover_plugins_with_defs([
        SuperClassDef(
            base_class,
            paths=paths or [],
            classes=classes or [],
        ),
    ])[base_class]
    result.ignore_plugins(ignored_classes or [])
    if not allow_duplicates:
        result.remove_duplicates()
    return result


class PluginDiscoverContext:
    """Store and discover registered types nad registered paths to types.

    Keeps in memory all registered types and their paths. Paths are dynamically
    loaded on discover so different discover calls won't return the same
    class objects even if were loaded from same file.
    """

    def __init__(self):
        self._registered_plugins = {}
        self._registered_plugin_paths = {}
        self._last_discovered_plugins = {}
        # Store the last result to memory
        self._last_discovered_results = {}

    def get_last_discovered_plugins(self, superclass):
        """Access last discovered plugin by a subperclass.

        Returns:
            None: When superclass was not discovered yet.
            list: Lastly discovered plugins of the superclass.
        """

        return self._last_discovered_plugins.get(superclass)

    def discover(
        self,
        superclass,
        allow_duplicates=True,
        ignore_classes=None,
        return_report=False
    ):
        """Find and return subclasses of `superclass`

        Args:
            superclass (type): Class which determines discovered subclasses.
            allow_duplicates (bool): Validate class name duplications.
            ignore_classes (list): List of classes that will be ignored
                and not added to result.
            return_report (bool): Output will be full report if set to 'True'.

        Returns:
            Union[DiscoverResult, list[Any]]: Object holding successfully
                discovered plugins, ignored plugins, plugins with missing
                abstract implementation and duplicated plugin.

        """
        registered_classes = self._registered_plugins.get(superclass) or []
        registered_paths = self._registered_plugin_paths.get(superclass) or []
        result = discover_plugins(
            superclass,
            paths=registered_paths,
            classes=registered_classes,
            ignored_classes=ignore_classes,
            allow_duplicates=allow_duplicates,
        )

        # Store in memory last result to keep in memory loaded modules
        self._last_discovered_results[superclass] = result
        self._last_discovered_plugins[superclass] = list(
            result.plugins
        )
        result.log_report()
        if return_report:
            return result
        return result.plugins

    def discover_with_report(
        self,
        superclasses: tuple[type, ...] | list[type] | set[type],
    ) -> dict[type, DiscoverResult]:
        """Find and return subclasses of superclasses.

        Args:
            superclasses (tuple[type, ...] | list[type] | set[type]|): Classes
                which determines discovered subclasses.

        Returns:
            dict[type, DiscoverResult]: Object holding successfully
                discovered plugins, ignored plugins, plugins with missing
                abstract implementation and duplicated plugin.

        """
        defs = [
            SuperClassDef(
                superclass=superclass,
                paths=self._registered_plugin_paths.get(superclass) or [],
                classes=self._registered_plugins.get(superclass) or [],
            )
            for superclass in superclasses
        ]
        result = discover_plugins_with_defs(defs)

        # Store in memory last result to keep in memory loaded modules
        for superclass, sc_result in result.items():
            self._last_discovered_results[superclass] = sc_result
            self._last_discovered_plugins[superclass] = list(
                sc_result.plugins
            )
            sc_result.log_report()
        return result

    def register_plugin(self, superclass, cls):
        """Register a directory containing plug-ins of type `superclass`

        Arguments:
            superclass (type): Superclass of plug-in
            cls (object): Subclass of `superclass`

        """
        if superclass not in self._registered_plugins:
            self._registered_plugins[superclass] = list()

        if cls not in self._registered_plugins[superclass]:
            self._registered_plugins[superclass].append(cls)

    def register_plugin_path(self, superclass, path):
        """Register a directory of one or more plug-ins

        Arguments:
            superclass (type): Superclass of plug-ins to look for during
                discovery
            path (str): Absolute path to directory in which to discover
                plug-ins

        """
        if superclass not in self._registered_plugin_paths:
            self._registered_plugin_paths[superclass] = list()

        path = os.path.normpath(path)
        if path not in self._registered_plugin_paths[superclass]:
            self._registered_plugin_paths[superclass].append(path)

    def registered_plugin_paths(self):
        """Return all currently registered plug-in paths"""
        # Return shallow copy so we the original data can't be changed
        return {
            superclass: paths[:]
            for superclass, paths in self._registered_plugin_paths.items()
        }

    def deregister_plugin(self, superclass, plugin):
        """Opposite of `register_plugin()`"""
        if superclass in self._registered_plugins:
            self._registered_plugins[superclass].remove(plugin)

    def deregister_plugin_path(self, superclass, path):
        """Opposite of `register_plugin_path()`"""
        self._registered_plugin_paths[superclass].remove(path)


class _GlobalDiscover:
    """Access to global object of PluginDiscoverContext.

    Using singleton object to register/deregister plugins and plugin paths
    and then discover them by superclass.
    """

    _context = None

    @classmethod
    def get_context(cls):
        if cls._context is None:
            cls._context = PluginDiscoverContext()
        return cls._context


def discover(
    superclass,
    allow_duplicates=True,
    ignore_classes=None,
    return_report=False
):
    """Find and return subclasses of `superclass`

    Args:
        superclass (type): Class which determines discovered subclasses.
        allow_duplicates (bool): Validate class name duplications.
        ignore_classes (list): List of classes that will be ignored
            and not added to result.
        return_report (bool): Output will be full report if set to 'True'.

    Returns:
        Union[DiscoverResult, list[Any]]: Object holding successfully
            discovered plugins, ignored plugins, plugins with missing
            abstract implementation and duplicated plugin.
    """

    context = _GlobalDiscover.get_context()
    return context.discover(
        superclass,
        allow_duplicates,
        ignore_classes,
        return_report
    )


def discover_with_report(
    superclasses: tuple[type, ...] | list[type] | set[type]
) -> dict[type, DiscoverResult]:
    """Find and return subclasses of superclasses.

    Args:
        superclasses (tuple[type, ...] | list[type] | set[type]): Class which
            determines discovered subclasses.

    Returns:
        dict[type, DiscoverResult]: Report by super class.

    """
    context = _GlobalDiscover.get_context()
    return context.discover_with_report(superclasses)


def get_last_discovered_plugins(superclass):
    context = _GlobalDiscover.get_context()
    return context.get_last_discovered_plugins(superclass)


def register_plugin(superclass, cls):
    context = _GlobalDiscover.get_context()
    context.register_plugin(superclass, cls)


def register_plugin_path(superclass, path):
    context = _GlobalDiscover.get_context()
    context.register_plugin_path(superclass, path)


def deregister_plugin(superclass, cls):
    context = _GlobalDiscover.get_context()
    context.deregister_plugin(superclass, cls)


def deregister_plugin_path(superclass, path):
    context = _GlobalDiscover.get_context()
    context.deregister_plugin_path(superclass, path)
