"""Setup environment for UI preview scripts.

Makes sure that 'ayon_core' and 'qtmaterialsymbols' are in sys path.

Also makes sure module 'ui_preview' is available. That is done by using
a dummy module class if the module is not found. Python will auto-populate
rest of the submodules if 'ui_preview' is available.

It might be possible that it does not work in all cases and we might need to
import each file in 'ui_preview' package manually. But for now this should
be enough.

"""
import sys
from pathlib import Path

# Import QtWidgets to make sure Qt binding is available
from qtpy import QtWidgets

CURRENT_DIR = Path(__file__).parent


try:
    import ayon_core
except ImportError:
    sys.path.append(str(CURRENT_DIR.parent / "client"))

try:
    import qtmaterialsymbols
except ImportError:
    sys.path.append(
        str(CURRENT_DIR.parent / "client" / "ayon_core" / "vendor" / "python")
    )


class _ModuleClass:
    def __init__(self, name: str) -> None:
        # Call setattr on super class
        super().__setattr__("name", name)
        super().__setattr__("__name__", name)

        # Where modules and interfaces are stored
        super().__setattr__("__attributes__", {})

    def __getattr__(self, attr_name: str):
        if attr_name not in self.__attributes__:
            if attr_name in ("__path__", "__file__"):
                return None
            raise AttributeError(
                f"'{self.name}' has not attribute '{attr_name}'"
            )
        return self.__attributes__[attr_name]

    def __iter__(self):
        for module in self.values():
            yield module

    def __setattr__(self, attr_name, value):
        self.__attributes__[attr_name] = value

    def __setitem__(self, key, value):
        self.__setattr__(key, value)

    def __getitem__(self, key):
        return getattr(self, key)

    def get(self, key, default=None):
        return self.__attributes__.get(key, default)

    def keys(self):
        return self.__attributes__.keys()

    def values(self):
        return self.__attributes__.values()

    def items(self):
        return self.__attributes__.items()

try:
    import ui_preview
except ImportError:
    module = _ModuleClass("ui_preview")
    sys.modules[module.name] = module
