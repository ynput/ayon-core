from typing import Type

from ayon_server.addons import BaseServerAddon

from .version import __version__
from .settings import DeadlineSettings, DEFAULT_VALUES, DeadlineSiteSettings


class Deadline(BaseServerAddon):
    name = "deadline"
    title = "Deadline"
    version = __version__
    settings_model: Type[DeadlineSettings] = DeadlineSettings
    site_settings_model: Type[DeadlineSiteSettings] = DeadlineSiteSettings


    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
