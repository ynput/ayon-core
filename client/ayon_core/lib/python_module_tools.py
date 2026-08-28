"""Tools for working with python modules and classes."""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import inspect
import os
import sys
import types

from .log import Logger

log = Logger.get_logger(__name__)


def import_filepath(
    filepath: str,
    module_name: str | None = None,
    sys_module_name: str | None = None,
) -> types.ModuleType:
    """Import python file as python module.

    Args:
        filepath (str): Path to python file.
        module_name (str): Name of loaded module. Only for Python 3. By default
            is filled with filename of filepath.
        sys_module_name (str): Name of module in `sys.modules` where to store
            loaded module. By default is None so module is not added to
            `sys.modules`.

    """
    if module_name is None:
        module_name = os.path.splitext(os.path.basename(filepath))[0]

    # Prepare module object where content of file will be parsed
    module = types.ModuleType(module_name)
    module.__file__ = filepath

    # Use loader so module has full specs
    module_loader = importlib.machinery.SourceFileLoader(
        module_name, filepath
    )
    # only add to sys.modules if requested
    if sys_module_name:
        sys.modules[sys_module_name] = module
    module_loader.exec_module(module)
    return module


@dataclass
class ModuleInfo:
    filepath: str
    module: types.ModuleType

    # Backwards compatibility - added 27/08/2026
    def __iter__(self):
        # Yield data as tuple for unpacking
        yield self.filepath
        yield self.module

    def __getitem__(self, index: int) -> str | types.ModuleType:
        # Allow index access
        return [self.filepath, self.module][index]


@dataclass
class CrashedModuleInfo:
    filepath: str
    exc_info: tuple

    # Backwards compatibility - added 27/08/2026
    def __iter__(self):
        # Yield data as tuple for unpacking
        yield self.filepath
        yield self.exc_info

    def __getitem__(self, index: int) -> str | tuple:
        # Allow index access
        return [self.filepath, self.exc_info][index]


@dataclass
class ModulesResult:
    modules: list[ModuleInfo] = field(default_factory=list)
    crashed: list[CrashedModuleInfo] = field(default_factory=list)

    def add_module(self, path: str, module: types.ModuleType) -> None:
        self.modules.append(ModuleInfo(path, module))

    def add_crashed_module(self, path: str, exc_info: tuple) -> None:
        self.crashed.append(CrashedModuleInfo(path, exc_info))

    # Backwards compatibility - added 27/08/2026
    def __iter__(self):
        # Yield data as tuple for unpacking
        yield self.modules
        yield self.crashed

    def __getitem__(
        self, index: int
    ) -> list[ModuleInfo] | list[CrashedModuleInfo]:
        # Allow index access
        return [self.modules, self.crashed][index]


def modules_from_path(dir_path: str) -> ModulesResult:
    """Get python scripts as modules from a path.

    Arguments:
        dir_path (str): Path to folder containing python scripts.

    Returns:
        ModulesResult: Contains successfully imported modules and
            information about paths that failed to import.

    """
    result = ModulesResult()
    # Just skip and return empty list if path is not set
    if not dir_path:
        return result

    # Do not allow relative imports
    if dir_path.startswith("."):
        log.warning(
            "BUG: Relative paths are not allowed for security reasons."
            f" {dir_path}"
        )
        return result

    dir_path = os.path.normpath(dir_path)

    if not os.path.isdir(dir_path):
        log.warning(f"Not a directory path: {dir_path}")
        return result

    for filename in os.listdir(dir_path):
        # Ignore files which start with underscore
        if filename.startswith("_"):
            continue

        mod_name, mod_ext = os.path.splitext(filename)
        if not mod_ext == ".py":
            continue

        full_path = os.path.join(dir_path, filename)
        if not os.path.isfile(full_path):
            continue

        try:
            module = import_filepath(full_path, mod_name)
            result.add_module(full_path, module)

        except Exception:
            result.add_crashed_module(full_path, sys.exc_info())
            log.warning(
                f"Failed to load path: \"{full_path}\"",
                exc_info=True
            )
            continue

    return result


def recursive_bases_from_class(klass: type) -> list[type]:
    """Extract all bases from entered class."""
    result = []
    bases = klass.__bases__
    result.extend(bases)
    for base in bases:
        result.extend(recursive_bases_from_class(base))
    return result


def classes_from_module(
    superclass: type, module: types.ModuleType
) -> list[type]:
    """Return plug-ins from module

    Arguments:
        superclass (type): Superclass of subclasses to look for
        module (types.ModuleType): Imported module where to look for
            'superclass' subclasses.

    Returns:
        list[type]: List of plug-ins, or empty list if none is found.

    """
    classes = list()
    for name in dir(module):
        # It could be anything at this point
        obj = getattr(module, name)
        if not inspect.isclass(obj) or obj is superclass:
            continue

        if issubclass(obj, superclass):
            classes.append(obj)

    return classes


def import_module_from_dirpath(
    dirpath: str,
    folder_name: str,
    dst_module_name: str | None = None,
) -> types.ModuleType:
    """Import passed directory as a python module.

    Imported module can be assigned as a child attribute of already loaded
    module from `sys.modules` if has support of `setattr`. That is not default
    behavior of python modules so parent module must be a custom module with
    that ability.

    It is not possible to reimport already cached module. If you need to
    reimport module you have to remove it from caches manually.

    Args:
        dirpath (str): Parent directory path of loaded folder.
        folder_name (str): Folder name which should be imported inside passed
            directory.
        dst_module_name (str): Parent module name under which can be loaded
            module added.

    """
    # Import passed dirpath as python module
    if dst_module_name:
        full_module_name = f"{dst_module_name}.{folder_name}"
        dst_module = sys.modules[dst_module_name]
    else:
        full_module_name = folder_name
        dst_module = None

    # Skip import if is already imported
    if full_module_name in sys.modules:
        return sys.modules[full_module_name]

    import importlib.util
    from importlib._bootstrap_external import PathFinder

    # Find loader for passed path and name
    loader = PathFinder.find_module(full_module_name, [dirpath])

    # Load specs of module
    spec = importlib.util.spec_from_loader(
        full_module_name, loader, origin=dirpath
    )

    # Create module based on specs
    module = importlib.util.module_from_spec(spec)

    # Store module to destination module and `sys.modules`
    # WARNING this mus be done before module execution
    if dst_module is not None:
        setattr(dst_module, folder_name, module)

    sys.modules[full_module_name] = module

    # Execute module import
    loader.exec_module(module)

    return module


def is_func_signature_supported(func, *args, **kwargs):
    """Check if a function signature supports passed args and kwargs.

    This check does not actually call the function, just look if function can
    be called with the arguments.

    Notes:
        This does NOT check if the function would work with passed arguments
            only if they can be passed in. If function have *args, **kwargs
            in parameters, this will always return 'True'.

    Example:
        >>> def my_function(my_number):
        ...     return my_number + 1
        ...
        >>> is_func_signature_supported(my_function, 1)
        True
        >>> is_func_signature_supported(my_function, 1, 2)
        False
        >>> is_func_signature_supported(my_function, my_number=1)
        True
        >>> is_func_signature_supported(my_function, number=1)
        False
        >>> is_func_signature_supported(my_function, "string")
        True
        >>> def my_other_function(*args, **kwargs):
        ...     my_function(*args, **kwargs)
        ...
        >>> is_func_signature_supported(
        ...     my_other_function,
        ...     "string",
        ...     1,
        ...     other=None
        ... )
        True

    Args:
        func (Callable): A function where the signature should be tested.
        *args (Any): Positional arguments for function signature.
        **kwargs (Any): Keyword arguments for function signature.

    Returns:
        bool: Function can pass in arguments.

    """
    sig = inspect.signature(func)
    try:
        sig.bind(*args, **kwargs)
        return True
    except TypeError:
        pass
    return False
