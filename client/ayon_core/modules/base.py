# Backwards compatibility support
# - TODO should be removed before release 1.0.0
from ayon_core.addon import (
    AYONAddon,
    AddonsManager,
    load_addons,
)
from ayon_core.addon.base import (
    OpenPypeModule,
    OpenPypeAddOn,
)

ModulesManager = AddonsManager
load_modules = load_addons


__all__ = (
    "AYONAddon",
    "AddonsManager",
    "load_addons",
    "OpenPypeModule",
    "OpenPypeAddOn",
    "ModulesManager",
    "load_modules",
)
