from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import SubstancePainterSettings, DEFAULT_SPAINTER_SETTINGS


class SubstancePainterAddon(BaseServerAddon):
    settings_model: Type[SubstancePainterSettings] = SubstancePainterSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_SPAINTER_SETTINGS)
