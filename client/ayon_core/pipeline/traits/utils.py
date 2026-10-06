"""Utility functions for traits."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ayon_core.addon import AddonsManager, ITraits

if TYPE_CHECKING:

    from ayon_core.pipeline.traits.trait import TraitBase


def get_available_traits(
        addons_manager: Optional[AddonsManager] = None
) -> Optional[list[TraitBase]]:
    """Get available traits from active addons.

    Args:
        addons_manager (Optional[AddonsManager]): Addons manager instance.
            If not provided, a new one will be created. Within pyblish
            plugins, you can use an already collected instance of
            AddonsManager from context `context.data["ayonAddonsManager"]`.

    Returns:
        list[TraitBase]: List of available traits.

    """
    if addons_manager is None:
        # Create a new instance of AddonsManager
        addons_manager = AddonsManager()

    # Get active addons
    enabled_addons = addons_manager.get_enabled_addons()
    traits = []
    for addon in enabled_addons:
        if not issubclass(type(addon), ITraits):
            # Skip addons not providing traits
            continue
        # Get traits from addon
        addon_traits = addon.get_addon_traits()
        if addon_traits:
            # Add traits to a list
            for trait in addon_traits:
                if trait not in traits:
                    traits.append(trait)

    return traits
