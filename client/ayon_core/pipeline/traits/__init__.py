"""Trait classes for the pipeline."""
from .color import ColorManaged
from .content import (
    Bundle,
    Compressed,
    FileLocation,
    Fragment,
    LocatableContent,
    MimeType,
    RootlessLocation,
)
from .cryptography import DigitallySigned, GPGSigned
from .lifecycle import Persistent, Transient
from .meta import Tagged, TemplatePath
from .three_dimensional import Geometry, IESProfile, Lighting, Shader, Spatial
from .time import (
    FrameRanged,
    GapPolicy,
    Handles,
    Sequence,
    SMPTETimecode,
    Static,
)
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
    "Fragment",
    "LocatableContent",

    # color
    "ColorManaged",

    # cryptography
    "DigitallySigned",
    "GPGSigned",

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
    "Geometry",
    "IESProfile",
    "Lighting",
    "Shader",
    "Spatial",

    # time
    "FrameRanged",
    "Static",
    "Handles",
    "GapPolicy",
    "Sequence",
    "SMPTETimecode",
]
