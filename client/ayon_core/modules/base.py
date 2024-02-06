from ayon_core.addon import (
    AYONAddon,
    AddonsManager,
    TrayAddonsManager,
    load_addons,
)

ModulesManager = AddonsManager
TrayModulesManager = TrayAddonsManager
load_modules = load_addons


class OpenPypeModule(AYONAddon):
    """Base class of OpenPype module.

    Instead of 'AYONAddon' are passed in module settings.

    Args:
        manager (AddonsManager): Manager object who discovered addon.
        settings (dict[str, Any]): Settings.
    """

    # Disable by default
    enabled = False


class OpenPypeAddOn(OpenPypeModule):
    # Enable Addon by default
    enabled = True
