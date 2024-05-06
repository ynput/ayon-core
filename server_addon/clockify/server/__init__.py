from typing import Type

from ayon_server.addons import BaseServerAddon

from .settings import ClockifySettings


class ClockifyAddon(BaseServerAddon):
    settings_model: Type[ClockifySettings] = ClockifySettings
