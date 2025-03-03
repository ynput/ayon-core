"""Color management related traits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from .trait import TraitBase


@dataclass
class ColorManaged(TraitBase):
    """Color managed trait.

    Holds color management information. Can be used with Image related
    traits to define color space and config.

    Sync with OpenAssetIO MediaCreation Traits.

    Attributes:
        color_space (str): An OCIO colorspace name available
            in the "current" OCIO context.
        config (str): An OCIO config name defining color space.
    """

    id: ClassVar[str] = "ayon.color.ColorManaged.v1"
    name: ClassVar[str] = "ColorManaged"
    color_space: str
    description: ClassVar[str] = "Color Managed trait."
    persistent: ClassVar[bool] = True
    config: Optional[str] = None
