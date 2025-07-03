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
from .cryptography import DigitallySigned, PGPSigned
from .lifecycle import Persistent, Transient
from .meta import (
    IntendedUse,
    KeepOriginalLocation,
    SourceApplication,
    Tagged,
    TemplatePath,
    Variant,
)
from .representation import Representation
from .temporal import (
    FrameRanged,
    GapPolicy,
    Handles,
    Sequence,
    SMPTETimecode,
    Static,
)
from .three_dimensional import Geometry, IESProfile, Lighting, Shader, Spatial
from .trait import (
    MissingTraitError,
    TraitBase,
    TraitValidationError,
)
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

__all__ = [  # noqa: RUF022
    # base
    "Representation",
    "TraitBase",
    "MissingTraitError",
    "TraitValidationError",

    # color
    "ColorManaged",

    # content
    "Bundle",
    "Compressed",
    "FileLocation",
    "FileLocations",
    "Fragment",
    "LocatableContent",
    "MimeType",
    "RootlessLocation",

    # cryptography
    "DigitallySigned",
    "PGPSigned",

    # life cycle
    "Persistent",
    "Transient",

    # meta
    "IntendedUse",
    "KeepOriginalLocation",
    "SourceApplication",
    "Tagged",
    "TemplatePath",
    "Variant",

    # temporal
    "FrameRanged",
    "GapPolicy",
    "Handles",
    "Sequence",
    "SMPTETimecode",
    "Static",

    # three-dimensional
    "Geometry",
    "IESProfile",
    "Lighting",
    "Shader",
    "Spatial",

    # two-dimensional
    "Compressed",
    "Deep",
    "Image",
    "Overscan",
    "PixelBased",
    "Planar",
    "UDIM",

    # utils
    "get_sequence_from_files",
]
