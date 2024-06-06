# -*- coding: utf-8 -*-
"""Module providing support for Royal Render."""
import os

from ayon_core.addon import AYONAddon, IPluginPaths

from .version import __version__


class RoyalRenderAddon(AYONAddon, IPluginPaths):
    """Class providing basic Royal Render implementation logic."""
    name = "royalrender"
    version = __version__

    def initialize(self, studio_settings):
        # type: (dict) -> None
        self.enabled = False
        addon_settings = studio_settings.get(self.name)
        if addon_settings:
            self.enabled = addon_settings["enabled"]

    @staticmethod
    def get_plugin_paths():
        # type: () -> dict
        """Royal Render plugin paths.

        Returns:
            dict: Dictionary of plugin paths for RR.
        """
        current_dir = os.path.dirname(os.path.abspath(__file__))
        return {
            "publish": [os.path.join(current_dir, "plugins", "publish")]
        }
