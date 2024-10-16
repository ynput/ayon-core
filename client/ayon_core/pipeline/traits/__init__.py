"""Trait classes for the pipeline."""
from .content import (
    Bundle,
    Compressed,
    FileLocation,
    MimeType,
    RootlessLocation,
)
from .meta import Tagged
from .three_dimensional import Spatial
from .time import Clip, GapPolicy, Sequence, SMPTETimecode
from .trait import Representation, TraitBase
from .two_dimensional import (
    Deep,
    Image,
    Overscan,
    PixelBased,
    Planar,
)

__all__ = [
    # base
    "Representation",
    "TraitBase",

    # content
    "Bundle",
    "Compressed",
    "FileLocation",
    "MimeType",
    "RootlessLocation",

    # meta
    "Tagged",

    # two-dimensional
    "Compressed",
    "Deep",
    "Image",
    "Overscan",
    "PixelBased",
    "Planar",

    # three-dimensional
    "Spatial",

    # time
    "Clip",
    "GapPolicy",
    "Sequence",
    "SMPTETimecode",
]
