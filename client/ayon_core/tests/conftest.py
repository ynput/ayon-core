import pytest
from pathlib import Path

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
