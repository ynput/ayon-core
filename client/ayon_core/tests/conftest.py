import sys
from pathlib import Path

import pytest

# Test with the vendorized qtmaterialsymbols
VENDOR_ROOT = Path(__file__).parent.parent / "vendor" / "python"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

collect_ignore = ["vendor", "resources"]

RESOURCES_PATH = 'resources'


@pytest.fixture
def resources_path_factory():
    def factory(*args):
        dirpath = Path(__file__).parent / RESOURCES_PATH
        for arg in args:
            dirpath = dirpath / arg
        return dirpath
    return factory
