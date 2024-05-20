import pyblish.api

from ayon_core.lib import filter_profiles
from ayon_core.host import ILoadHost
from ayon_core.pipeline.load import any_outdated_containers
from ayon_core.pipeline import (
    get_current_host_name,
    registered_host,
    PublishXmlValidationError,
    OptionalPyblishPluginMixin
)


class ShowInventory(pyblish.api.Action):

    label = "Show Inventory"
    icon = "briefcase"
    on = "failed"

    def process(self, context, plugin):
        from ayon_core.tools.utils import host_tools

        host_tools.show_scene_inventory()


class ValidateOutdatedContainers(
    OptionalPyblishPluginMixin,
    pyblish.api.ContextPlugin
):
    """Containers are must be updated to latest version on publish."""

    label = "Validate Outdated Containers"
    order = pyblish.api.ValidatorOrder

    optional = True
    actions = [ShowInventory]

    @classmethod
    def apply_settings(cls, settings):
        # Disable plugin if host does not inherit from 'ILoadHost'
        # - not a host that can load containers
        host = registered_host()
        if not isinstance(host, ILoadHost):
            cls.enabled = False
            return

        # Disable if no profile is found for the current host
        profiles = (
            settings
            ["core"]
            ["publish"]
            ["ValidateOutdatedContainers"]
            ["plugin_state_profiles"]
        )
        profile = filter_profiles(
            profiles, {"host_names": get_current_host_name()}
        )
        if not profile:
            cls.enabled = False
            return

        # Apply settings from profile
        for attr_name in {
            "enabled",
            "optional",
            "active",
        }:
            setattr(cls, attr_name, profile[attr_name])

    def process(self, context):
        if not self.is_active(context.data):
            return

        if any_outdated_containers():
            msg = "There are outdated containers in the scene."
            raise PublishXmlValidationError(self, msg)
