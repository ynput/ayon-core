"""Utility functions for traits."""
from __future__ import annotations

from typing import TYPE_CHECKING

from clique import assemble

from ayon_core.pipeline.traits import Sequence

if TYPE_CHECKING:
    from pathlib import Path


def get_sequence_from_files(paths: list[Path]) -> Sequence:
    """Get original frame range from files.

    Note that this cannot guess frame rate, so it's set to 25.

    Args:
        paths (list[Path]): List of file paths.

    Returns:
        Sequence: Sequence trait.

    """
    col = assemble([path.as_posix() for path in paths])[0][0]
    sorted_frames = sorted(col.indexes)
    # First frame used for end value
    first_frame = sorted_frames[0]
    # Get last frame for padding
    last_frame = sorted_frames[-1]
    # Use padding from collection of length of last frame as string
    padding = max(col.padding, len(str(last_frame)))

    return Sequence(
        frame_start=first_frame, frame_end=last_frame, frame_padding=padding,
        frames_per_second=25
    )
