# Deprecated file
# - the file container 'WeakMethod' implementation for Python 2 which is not
#   needed anymore.
import warnings
import weakref


WeakMethod = weakref.WeakMethod

warnings.warn(
    (
        "'ayon_core.lib.python_2_comp' is deprecated."
        "Please use 'weakref.WeakMethod'."
    ),
    DeprecationWarning,
    stacklevel=2
)
