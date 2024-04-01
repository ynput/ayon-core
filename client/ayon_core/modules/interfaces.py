from ayon_core.addon.interfaces import (
    IPluginPaths,
    ITrayAddon,
    ITrayAction,
    ITrayService,
    IHostAddon,
)

ITrayModule = ITrayAddon
ILaunchHookPaths = object


__all__ = (
    "IPluginPaths",
    "ITrayAddon",
    "ITrayAction",
    "ITrayService",
    "IHostAddon",
    "ITrayModule",
    "ILaunchHookPaths",
)
