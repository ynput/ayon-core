"""Trait classes for the pipeline."""
from .color import ColorManaged
from .content import (
    Bundle,
    Compressed,
    FileLocation,
    FileLocations,
    Fragment,
    LocatableContent,
    MimeType,
    RootlessLocation,
)
from .cryptography import DigitallySigned, GPGSigned
from .lifecycle import Persistent, Transient
from .meta import Tagged, TemplatePath
from .representation import Representation
from .three_dimensional import Geometry, IESProfile, Lighting, Shader, Spatial
from .time import (
    FrameRanged,
    GapPolicy,
    Handles,
    Sequence,
    SMPTETimecode,
    Static,
)
from .trait import MissingTraitError, TraitBase
from .two_dimensional import (
    UDIM,
    Deep,
    Image,
    Overscan,
    PixelBased,
    Planar,
)
from .utils import (
    get_sequence_from_files,
)

__all__ = [
    # base
    "Representation",
    "TraitBase",
    "MissingTraitError",

    # content
    "Bundle",
    "Compressed",
    "FileLocation",
    "FileLocations",
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

    # utils
    "get_sequence_from_files",
]
