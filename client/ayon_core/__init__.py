import os


AYON_CORE_ROOT = os.path.dirname(os.path.abspath(__file__))

# TODO remove after '1.x.x'
PACKAGE_DIR = AYON_CORE_ROOT
PLUGINS_DIR = os.path.join(AYON_CORE_ROOT, "plugins")
AYON_SERVER_ENABLED = True

# Indicate if AYON entities should be used instead of OpenPype entities
USE_AYON_ENTITIES = False
