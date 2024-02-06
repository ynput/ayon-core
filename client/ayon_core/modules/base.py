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
