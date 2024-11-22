"""Color management related traits."""
from __future__ import annotations

from typing import ClassVar, Optional

from pydantic import Field

from .trait import TraitBase


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
    description: ClassVar[str] = "Color Managed trait."
    color_space: str = Field(
        ...,
        description="Color space."
    )
    config: Optional[str] = Field(None, description="Color config.")
