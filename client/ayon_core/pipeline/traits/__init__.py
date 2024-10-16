"""Trait classes for the pipeline."""
from .content import (
    Bundle,
    Compressed,
    FileLocation,
    MimeType,
    RootlessLocation,
)
from .lifecycle import Persistent, Transient
from .meta import Tagged, TemplatePath
from .three_dimensional import Spatial
from .time import Clip, GapPolicy, Sequence, SMPTETimecode
from .trait import Representation, TraitBase
from .two_dimensional import (
    UDIM,
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

    # life cycle
    "Persistent",
    "Transient",

    # meta
    "Tagged",
    "TemplatePath",

    # two-dimensional
    "Compressed",
    "Deep",
    "Image",
    "Overscan",
    "PixelBased",
    "Planar",
    "UDIM",

    # three-dimensional
    "Spatial",

    # time
    "Clip",
    "GapPolicy",
    "Sequence",
    "SMPTETimecode",
]
