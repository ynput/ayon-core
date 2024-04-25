from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import TimersManagerSettings


class TimersManagerAddon(BaseServerAddon):
    settings_model: Type[TimersManagerSettings] = TimersManagerSettings
