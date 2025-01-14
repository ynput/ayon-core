import os
from .version import __version__


AYON_CORE_ROOT = os.path.dirname(os.path.abspath(__file__))

# -------------------------
# DEPRECATED - Remove before '1.x.x' release
# -------------------------
PACKAGE_DIR = AYON_CORE_ROOT
PLUGINS_DIR = os.path.join(AYON_CORE_ROOT, "plugins")
# -------------------------


__all__ = (
    "__version__",

    # Deprecated
    "AYON_CORE_ROOT",
    "PACKAGE_DIR",
    "PLUGINS_DIR",
)
