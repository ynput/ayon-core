"""Two-dimensional image traits."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import Field, field_validator

from .trait import TraitBase

if TYPE_CHECKING:
    from .content import FileLocation, FileLocations


class Image(TraitBase):
    """Image trait model.

    Type trait model for image.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "Image"
    description: ClassVar[str] = "Image Trait"
    id: ClassVar[str] = "ayon.2d.Image.v1"


class PixelBased(TraitBase):
    """PixelBased trait model.

    Pixel related trait for image data.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        display_window_width (int): Width of the image display window.
        display_window_height (int): Height of the image display window.
        pixel_aspect_ratio (float): Pixel aspect ratio.
    """

    name: ClassVar[str] = "PixelBased"
    description: ClassVar[str] = "PixelBased Trait Model"
    id: ClassVar[str] = "ayon.2d.PixelBased.v1"
    display_window_width: int = Field(..., title="Display Window Width")
    display_window_height: int = Field(..., title="Display Window Height")
    pixel_aspect_ratio: float = Field(..., title="Pixel Aspect Ratio")


class Planar(TraitBase):
    """Planar trait model.

    This model represents an Image with planar configuration.

    Todo:
        * (antirotor): Is this really a planar configuration? As with
            bitplanes and everything? If it serves as differentiator for
            Deep images, should it be named differently? Like Raster?

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        planar_configuration (str): Planar configuration.
    """

    name: ClassVar[str] = "Planar"
    description: ClassVar[str] = "Planar Trait Model"
    id: ClassVar[str] = "ayon.2d.Planar.v1"
    planar_configuration: str = Field(..., title="Planar-based Image")


class Deep(TraitBase):
    """Deep trait model.

    Type trait model for deep EXR images.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "Deep"
    description: ClassVar[str] = "Deep Trait Model"
    id: ClassVar[str] = "ayon.2d.Deep.v1"


class Overscan(TraitBase):
    """Overscan trait model.

    This model represents an overscan (or underscan) trait. Defines the
    extra pixels around the image.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        left (int): Left overscan/underscan.
        right (int): Right overscan/underscan.
        top (int): Top overscan/underscan.
        bottom (int): Bottom overscan/underscan.
    """

    name: ClassVar[str] = "Overscan"
    description: ClassVar[str] = "Overscan Trait"
    id: ClassVar[str] = "ayon.2d.Overscan.v1"
    left: int = Field(..., title="Left Overscan")
    right: int = Field(..., title="Right Overscan")
    top: int = Field(..., title="Top Overscan")
    bottom: int = Field(..., title="Bottom Overscan")


class UDIM(TraitBase):
    """UDIM trait model.

    This model represents a UDIM trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        udim (int): UDIM value.
    """

    name: ClassVar[str] = "UDIM"
    description: ClassVar[str] = "UDIM Trait"
    id: ClassVar[str] = "ayon.2d.UDIM.v1"
    udim: list[int] = Field(..., title="UDIM")
    udim_regex: Optional[str] = Field(
        default=r"(?:\.|_)(?P<udim>\d+)\.\D+\d?$", title="UDIM Regex")

    @field_validator("udim_regex")
    @classmethod
    def validate_frame_regex(cls, v: Optional[str]) -> Optional[str]:
        """Validate udim regex.

        Returns:
            Optional[str]: UDIM regex.

        Raises:
            ValueError: UDIM regex must include 'udim' named group.

        """
        if v is not None and "?P<udim>" not in v:
            msg = "UDIM regex must include 'udim' named group"
            raise ValueError(msg)
        return v

    def get_file_location_for_udim(
            self,
            file_locations: FileLocations,
            udim: int,
        ) -> Optional[FileLocation]:
        """Get file location for UDIM.

        Args:
            file_locations (FileLocations): File locations.
            udim (int): UDIM value.

        Returns:
            Optional[FileLocation]: File location.

        """
        pattern = re.compile(self.udim_regex)
        for location in file_locations.file_paths:
            result = re.search(pattern, location.file_path.name)
            if result:
                udim_index = int(result.group("udim"))
                if udim_index == udim:
                    return location
        return None

    def get_udim_from_file_location(
            self, file_location: FileLocation) -> Optional[int]:
        """Get UDIM from file location.

        Args:
            file_location (FileLocation): File location.

        Returns:
            Optional[int]: UDIM value.

        """
        pattern = re.compile(self.udim_regex)
        result = re.search(pattern, file_location.file_path.name)
        if result:
            return int(result.group("udim"))
        return None
