"""Tools for working with python modules and classes."""
from __future__ import annotations

from dataclasses import dataclass, field
import importlib
import inspect
import hashlib
import os
from pathlib import Path
import platform
import sys
import types
import warnings

from .log import Logger

log = Logger.get_logger(__name__)

IS_WINDOWS = platform.platform().lower() == "windows"


def get_dynamic_import_module_name(
    dirpath: Path | str,
    filename: str | None = None,
) -> str:
    """Get hash of directory path.

    Args:
        dirpath (Path | str): Directory path to hash.

    Returns:
        str: Hash of directory path.

    """
    if isinstance(dirpath, str):
        dirpath = Path(dirpath)
    unified_path = dirpath.absolute().as_posix()
    if IS_WINDOWS:
        unified_path = unified_path.lower()
    dirhash = hashlib.md5(unified_path.encode("utf-8")).hexdigest()
    if not filename:
        return dirhash
    return f"{dirhash}.{os.path.splitext(filename)[0]}"


def import_filepath(
    filepath: str | Path,
    module_name: str | None = None,
    sys_module_name: str | None = None,
) -> types.ModuleType:
    """Import python file as python module.

    It is recommended to pass in only 'filepath' and let function generate
        module names automatically.

    Args:
        filepath (str | Path): Path to python file.
        module_name (str): Name of loaded module. Only for Python 3.
            By default is filled with filename of filepath.
        sys_module_name (str): Name of module in `sys.modules` where to store
            loaded module. By default is used directory hash and module name.

    """
    if isinstance(filepath, str):
        filepath = Path(filepath)

    if module_name is None:
        module_name = filepath.stem

    if not sys_module_name:
        dirpath_hash = get_dynamic_import_module_name(filepath.parent)
        sys_module_name = f"{dirpath_hash}.{module_name}"

    # Prepare module object where content of file will be parsed
    module = types.ModuleType(sys_module_name)
    module.__file__ = filepath.as_posix()

    sys.modules[sys_module_name] = module

    # Use loader so module has full specs
    module_loader = importlib.machinery.SourceFileLoader(
        sys_module_name, filepath.as_posix()
    )

    module_loader.exec_module(module)
    return module


@dataclass
class ModuleInfo:
    filepath: str
    module: types.ModuleType

    # Backwards compatibility - added 27/08/2026
    def __iter__(self):
        # Yield data as tuple for unpacking
        warnings.warn(
            (
                "Using ModuleInfo as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.filepath
        yield self.module

    def __getitem__(self, index: int) -> str | types.ModuleType:
        # Allow index access
        warnings.warn(
            (
                "Using ModuleInfo as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        return [self.filepath, self.module][index]


@dataclass
class CrashedModuleInfo:
    filepath: str
    exc_info: tuple

    # Backwards compatibility - added 27/08/2026
    def __iter__(self):
        # Yield data as tuple for unpacking
        warnings.warn(
            (
                "Using CrashedModuleInfo as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.filepath
        yield self.exc_info

    def __getitem__(self, index: int) -> str | tuple:
        # Allow index access
        warnings.warn(
            (
                "Using CrashedModuleInfo as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
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
        warnings.warn(
            (
                "Using ModulesResult as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        yield self.modules
        yield self.crashed

    def __getitem__(
        self, index: int
    ) -> list[ModuleInfo] | list[CrashedModuleInfo]:
        # Allow index access
        warnings.warn(
            (
                "Using ModulesResult as tuple is deprecated"
                " and will be removed in future versions. "
            ),
            DeprecationWarning,
            stacklevel=2,
        )
        return [self.modules, self.crashed][index]


def modules_from_path(path: str | Path) -> ModulesResult:
    """Get python scripts as modules from a path.

    Arguments:
        path (str | Path): Path to folder containing python scripts or path
            to a python script.

    Returns:
        ModulesResult: Contains successfully imported modules and
            information about paths that failed to import.

    """
    result = ModulesResult()

    if isinstance(path, str):
        # Just skip and return empty result if path is not set
        if not path:
            return result

        # Do not allow relative imports
        if path.startswith("."):
            log.warning(
                "BUG: Relative paths are not allowed for security reasons."
                f" {path}"
            )
            return result

        path = Path(path)

    filepaths = []
    if path.is_file():
        filepaths.append(path)

    elif path.is_dir():
        for file in path.iterdir():
            # Ignore files which start with underscore
            if file.name.startswith("_"):
                continue

            filepaths.append(file)
    else:
        return result

    for filepath in filepaths:
        if not filepath.is_file():
            continue

        _, mod_ext = os.path.splitext(filepath.name)
        if mod_ext.lower() != ".py":
            continue

        try:
            module = import_filepath(filepath)
            result.add_module(filepath.as_posix(), module)

        except Exception:
            result.add_crashed_module(filepath.as_posix(), sys.exc_info())
            log.warning(
                f"Failed to load path: \"{filepath}\"",
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
