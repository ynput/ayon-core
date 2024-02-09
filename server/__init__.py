from ayon_server.addons import BaseServerAddon

from .settings import CoreSettings, DEFAULT_VALUES


class CoreAddon(BaseServerAddon):
    settings_model = CoreSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)
