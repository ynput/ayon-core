from typing import Type

from ayon_server.addons import BaseServerAddon

from .version import __version__
from .settings import ZbrushSettings, DEFAULT_VALUES


class ZbrushAddon(BaseServerAddon):
    name = "zbrush"
    title = "Zbrush"
    version = __version__
    settings_model: Type[ZbrushSettings] = ZbrushSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
