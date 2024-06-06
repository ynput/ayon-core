# -*- coding: utf-8 -*-
"""Module providing support for Royal Render."""
import os

from ayon_core.addon import AYONAddon, IPluginPaths

from .version import __version__


class RoyalRenderAddon(AYONAddon, IPluginPaths):
    """Class providing basic Royal Render implementation logic."""
    name = "royalrender"
    version = __version__

    # _rr_api = None
    # @property
    # def rr_api(self):
    #     if not self._rr_api:
    #         # import royal render modules
    #         from .api import Api
    #         self._rr_api = Api(self.settings)
    #     return self._rr_api

    def initialize(self, studio_settings):
        # type: (dict) -> None
        self.enabled = self.name in studio_settings

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
