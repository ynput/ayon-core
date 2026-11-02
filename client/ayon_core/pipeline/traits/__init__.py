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
from .lifecycle import Persistent, StagingDirectory, Transient
from .meta import (
    PROCESSING_TAGS,
    CustomTags,
    IntendedUse,
    KeepOriginalLocation,
    ReviewOutput,
    SourceApplication,
    Tagged,
    TemplatePath,
    Variant,
)
from .representation import Representation
from .temporal import (
    FrameRangeData,
    FrameRanged,
    GapPolicy,
    Handles,
    Sequence,
    Slate,
    SMPTETimecode,
    Static,
    get_frame_range_data,
    parse_frame_rate,
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

from .publishing import (
    TransferItem,
    apply_transfers,
    get_representation_context,
    prepare_for_json,
    update_sequence_traits,
    get_first_file_location,
    get_transfers_from_representations,
    get_template_data_from_representation,
    get_legacy_files_for_representation,
    replace_paths_in_representation,
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
    "StagingDirectory",
    "Transient",

    # meta
    "CustomTags",
    "IntendedUse",
    "KeepOriginalLocation",
    "SourceApplication",
    "Tagged",
    "PROCESSING_TAGS",
    "TemplatePath",
    "Variant",
    "ReviewOutput",

    # temporal
    "FrameRanged",
    "GapPolicy",
    "Handles",
    "Sequence",
    "SMPTETimecode",
    "Static",
    "FrameRangeData",
    "get_frame_range_data",
    "parse_frame_rate",
    "Slate",

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

    # publishing
    "TransferItem",
    "apply_transfers",
    "get_representation_context",
    "prepare_for_json",
    "update_sequence_traits",
    "get_first_file_location",
    "get_transfers_from_representations",
    "get_template_data_from_representation",
    "get_legacy_files_for_representation",
    "replace_paths_in_representation",
]
