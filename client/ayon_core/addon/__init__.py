# -*- coding: utf-8 -*-
from .interfaces import (
    IPluginPaths,
    ITrayAddon,
    ITrayAction,
    ITrayService,
    IHostAddon,
)

from .base import (
    AYONAddon,
    AddonsManager,
    TrayAddonsManager,
    load_addons,
)


__all__ = (
    "IPluginPaths",
    "ITrayAddon",
    "ITrayAction",
    "ITrayService",
    "IHostAddon",

    "AYONAddon",
    "AddonsManager",
    "TrayAddonsManager",
    "load_addons",
)
