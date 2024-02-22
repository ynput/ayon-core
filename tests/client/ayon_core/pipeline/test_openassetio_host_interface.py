import ayon_core
from ayon_core.pipeline.openassetio_host_interface import (
    initialize_openassetio_host_interface,
    get_openassetio_manager
)

from openassetio.errors import ConfigurationException
import pytest
import os
import ayon_openassetio_manager
from pathlib import Path


@pytest.fixture
def plugin_path_env():
    conf_path = Path(os.path.dirname(ayon_core.__file__)) / "host.toml"
    os.environ["OPENASSETIO_DEFAULT_CONFIG"] = conf_path.as_posix()
    os.environ["OPENASSETIO_PLUGIN_PATH"] = ayon_openassetio_manager.AYON_OPENASSETIO_ROOT
    return os.environ["OPENASSETIO_PLUGIN_PATH"], os.environ["OPENASSETIO_DEFAULT_CONFIG"]


@pytest.fixture
def ayon_connection_env():
    os.environ["AYON_SERVER_URL"] = os.getenv("AYON_SERVER_URL", "http://localhost:5000")
    os.environ["AYON_API_KEY"] = os.getenv("AYON_API_KEY")


def test_initialize_openassetio_host_interface():
    host_interface = initialize_openassetio_host_interface()
    assert host_interface is not None


def test_get_openassetio_manager_without_configured_manager():

    with pytest.raises(ConfigurationException):
        get_openassetio_manager()


def test_get_openassetio_manager(plugin_path_env):
    manager = get_openassetio_manager()
    assert manager is not None
    assert manager.identifier() == "io.ynput.ayon.openassetio.manager.interface"
