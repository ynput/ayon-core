# Backwards compatibility support
# - TODO should be removed before release 1.0.0
from ayon_core.addon import (
    AYONAddon,
    AddonsManager,
    TrayAddonsManager,
    load_addons,
)
from ayon_core.addon.base import (
    OpenPypeModule,
    OpenPypeAddOn,
)

ModulesManager = AddonsManager
TrayModulesManager = TrayAddonsManager
load_modules = load_addons


__all__ = (
    "AYONAddon",
    "AddonsManager",
    "TrayAddonsManager",
    "load_addons",
    "OpenPypeModule",
    "OpenPypeAddOn",
    "ModulesManager",
    "TrayModulesManager",
    "load_modules",
)
