"""Trait classes for the pipeline."""
from .content import Compressed, FileLocation, RootlessLocation
from .three_dimensional import Spatial
from .trait import TraitBase, TraitsData
from .two_dimensional import (
    Deep,
    Image,
    Overscan,
    PixelBased,
    Planar,
)

__all__ = [
    # base
    "TraitBase",
    "TraitsData",
    # content
    "FileLocation",
    "RootlessLocation",
    # two-dimensional
    "Image",
    "PixelBased",
    "Planar",
    "Deep",
    "Compressed",
    "Overscan",
    # three-dimensional
    "Spatial",
]
