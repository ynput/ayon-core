"""Tools for working with python modules and classes."""
import os
import sys
import types
from typing import Optional
import importlib
import inspect
import logging

log = logging.getLogger(__name__)


def import_filepath(
        filepath: str,
        module_name: Optional[str]=None,
        sys_module_name: Optional[str]=None) -> types.ModuleType:
    """Import python file as python module.

    Args:
        filepath (str): Path to python file.
        module_name (str): Name of loaded module. Only for Python 3. By default
            is filled with filename of filepath.
        sys_module_name (str): Name of module in `sys.modules` where to store
            loaded module. By default is None so module is not added to
            `sys.modules`.

    Todo (antirotor): We should add the module to the sys.modules always but
        we need to be careful about it and test it properly.

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


def modules_from_path(folder_path):
    """Get python scripts as modules from a path.

    Arguments:
        path (str): Path to folder containing python scripts.

    Returns:
        tuple<list, list>: First list contains successfully imported modules
            and second list contains tuples of path and exception.
    """
    crashed = []
    modules = []
    output = (modules, crashed)
    # Just skip and return empty list if path is not set
    if not folder_path:
        return output

    # Do not allow relative imports
    if folder_path.startswith("."):
        log.warning((
            "BUG: Relative paths are not allowed for security reasons. {}"
        ).format(folder_path))
        return output

    folder_path = os.path.normpath(folder_path)

    if not os.path.isdir(folder_path):
        log.warning("Not a directory path: {}".format(folder_path))
        return output

    for filename in os.listdir(folder_path):
        # Ignore files which start with underscore
        if filename.startswith("_"):
            continue

        mod_name, mod_ext = os.path.splitext(filename)
        if not mod_ext == ".py":
            continue

        full_path = os.path.join(folder_path, filename)
        if not os.path.isfile(full_path):
            continue

        try:
            module = import_filepath(full_path, mod_name)
            modules.append((full_path, module))

        except Exception:
            crashed.append((full_path, sys.exc_info()))
            log.warning(
                "Failed to load path: \"{0}\"".format(full_path),
                exc_info=True
            )
            continue

    return output


def recursive_bases_from_class(klass):
    """Extract all bases from entered class."""
    result = []
    bases = klass.__bases__
    result.extend(bases)
    for base in bases:
        result.extend(recursive_bases_from_class(base))
    return result


def classes_from_module(superclass, module):
    """Return plug-ins from module

    Arguments:
        superclass (superclass): Superclass of subclasses to look for
        module (types.ModuleType): Imported module where to look for
            'superclass' subclasses.

    Returns:
        List of plug-ins, or empty list if none is found.

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
        dirpath, folder_name, dst_module_name=None):
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
        full_module_name = "{}.{}".format(dst_module_name, folder_name)
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
