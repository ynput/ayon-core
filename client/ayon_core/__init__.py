import os
from .version import __version__


AYON_CORE_ROOT = os.path.dirname(os.path.abspath(__file__))

# -------------------------
# DEPRECATED - Remove before '1.x.x' release
# -------------------------
PACKAGE_DIR = AYON_CORE_ROOT
PLUGINS_DIR = os.path.join(AYON_CORE_ROOT, "plugins")
AYON_SERVER_ENABLED = True

# Indicate if AYON entities should be used instead of OpenPype entities
USE_AYON_ENTITIES = True
# -------------------------


__all__ = (
    "__version__",

    # Deprecated
    "AYON_CORE_ROOT",
    "PACKAGE_DIR",
    "PLUGINS_DIR",
    "AYON_SERVER_ENABLED",
    "USE_AYON_ENTITIES",
)
