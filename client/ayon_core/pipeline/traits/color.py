"""Color-management-related traits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from .trait import TraitBase


@dataclass
class ColorManaged(TraitBase):
    """Color managed trait.

    Holds color management information. Can be used with Image-related
    traits to define color space and config.

    Sync with OpenAssetIO MediaCreation Traits.

    Attributes:
        color_space (str): An OCIO colorspace name available
            in the "current" OCIO context.
        config_path (Optional[str]): Absolute, resolved path to the
            OCIO config used to interpret `color_space`.
        config_template (Optional[str]): Anatomy template (with tokens)
            pointing at the same OCIO config, for contexts where the
            resolved absolute path isn't portable (e.g. remote publishing).
    """

    id: ClassVar[str] = "ayon.color.ColorManaged.v1"
    name: ClassVar[str] = "ColorManaged"
    color_space: str
    description: ClassVar[str] = "Color Managed trait."
    persistent: ClassVar[bool] = True
    config_path: Optional[str] = None
    config_template: Optional[str] = None
