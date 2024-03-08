"""OpenAssetIO host interface implementation.

This module provides the implementation of the OpenAssetIO host interface
that is used to communicate with the OpenAssetIO manager. Manager
is used for loading and publishing data.

At this moment, the implementation is minimal and only provides the
host interface and manager initialization.

"""
from openassetio.errors import ConfigurationException
from openassetio.hostApi import HostInterface, Manager, ManagerFactory
from openassetio.log import ConsoleLogger, SeverityFilter
from openassetio.pluginSystem import (
    PythonPluginSystemManagerImplementationFactory,
)


class AyonHostInterface(HostInterface):
    """A minimal host interface implementation."""

    def identifier(self):
        return "io.ayon.host.resolver"

    def displayName(self):
        return "AYON OpenAssetIO Resolver"


def initialize_openassetio_host_interface() -> HostInterface:
    """Initialize the host interface.

    Returns:
        HostInterface: The host interface instance.

    """
    return AyonHostInterface()


def get_openassetio_manager() -> Manager:
    """Initialize the host interface.

    Returns:
        Manager: The manager instance.

    """
    logger = SeverityFilter(ConsoleLogger())
    impl_factory = PythonPluginSystemManagerImplementationFactory(logger)
    host_interface = initialize_openassetio_host_interface()
    manager = ManagerFactory.defaultManagerForInterface(host_interface, impl_factory, logger)

    if not manager:
        raise ConfigurationException(
            "No default manager configured, "
            f"check ${ManagerFactory.kDefaultManagerConfigEnvVarName}"
        )

    return manager
