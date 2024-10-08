"""Trait classes for the pipeline."""
from .trait import TraitBase
from .two_dimensional import (
    Compressed,
    Deep,
    Image,
    Overscan,
    PixelBased,
    Planar,
)

__all__ = [
    # base
    "TraitBase",
    # two-dimensional
    "Image",
    "PixelBased",
    "Planar",
    "Deep",
    "Compressed",
    "Overscan",
]
