"""Utility functions for traits."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from clique import assemble

from ayon_core.addon import AddonsManager, ITraits
from ayon_core.pipeline.traits.temporal import FrameRanged

if TYPE_CHECKING:
    from pathlib import Path
    from ayon_core.pipeline.traits.trait import TraitBase


def get_sequence_from_files(paths: list[Path]) -> FrameRanged:
    """Get the original frame range from files.

    Note that this cannot guess frame rate, so it's set to 25.
    This will also fail on paths that cannot be assembled into
    one collection without any reminders.

    Args:
        paths (list[Path]): List of file paths.

    Returns:
        FrameRanged: FrameRanged trait.

    Raises:
        ValueError: If paths cannot be assembled into one collection

    """
    cols, rems = assemble([path.as_posix() for path in paths])
    if rems:
        msg = "Cannot assemble paths into one collection"
        raise ValueError(msg)
    if len(cols) != 1:
        msg = "More than one collection found"
        raise ValueError(msg)
    col = cols[0]

    sorted_frames = sorted(col.indexes)
    # First frame used for end value
    first_frame = sorted_frames[0]
    # Get last frame for padding
    last_frame = sorted_frames[-1]
    # Use padding from a collection of the last frame lengths as string
    # padding = max(col.padding, len(str(last_frame)))

    return FrameRanged(
        frame_start=first_frame, frame_end=last_frame,
        frames_per_second="25.0"
    )


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
