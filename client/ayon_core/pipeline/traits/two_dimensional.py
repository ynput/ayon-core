"""Two-dimensional image traits."""
from pydantic import Field

from .trait import TraitBase


class Image(TraitBase):
    """Image trait model.

    This model represents an image trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version

    """

    name: str = "Image"
    description = "Image Trait"
    id: str = "ayon.content.Image.v1"


class PixelBased(TraitBase):
    """PixelBased trait model.

    This model represents a pixel based trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        display_window_width (int): Width of the image display window.
        display_window_height (int): Height of the image display window.
        pixel_aspect_ratio (float): Pixel aspect ratio.

    """

    name: str = "PixelBased"
    description = "PixelBased Trait Model"
    id: str = "ayon.content.PixelBased.v1"
    display_window_width: int = Field(..., title="Display Window Width")
    display_window_height: int = Field(..., title="Display Window Height")
    pixel_aspect_ratio: float = Field(..., title="Pixel Aspect Ratio")


class Planar(TraitBase):
    """Planar trait model.

    This model represents an Image with planar configuration.

    Todo (antirotor): Is this really a planar configuration? As with
        bitplanes and everything? If it serves as differentiator for
        Deep images, should it be named differently? Like Raster?

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        planar_configuration (str): Planar configuration.

    """

    name: str = "Planar"
    description = "Planar Trait Model"
    id: str = "ayon.content.Planar.v1"
    planar_configuration: str = Field(..., title="Planar-based Image")


class Deep(TraitBase):
    """Deep trait model.

    This model represents a deep image trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        deep_data_type (str): Deep data type.

    """

    name: str = "Deep"
    description = "Deep Trait Model"
    id: str = "ayon.content.Deep.v1"
    deep_data_type: str = Field(..., title="Deep Data Type")


class Compressed(TraitBase):
    """Compressed trait model.

    This model represents a compressed image trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        compression_type (str): Compression type.

    """

    name: str = "Compressed"
    description = "Compressed Trait"
    id: str = "ayon.content.Compressed.v1"
    compression_type: str = Field(..., title="Compression Type")


class Overscan(TraitBase):
    """Overscan trait model.

    This model represents an overscan (or underscan) trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        left (int): Left overscan/underscan.
        right (int): Right overscan/underscan.
        top (int): Top overscan/underscan.
        bottom (int): Bottom overscan/underscan.

    """

    name: str = "Overscan"
    description = "Overscan Trait"
    id: str = "ayon.content.Overscan.v1"
    left: int = Field(..., title="Left Overscan")
    right: int = Field(..., title="Right Overscan")
    top: int = Field(..., title="Top Overscan")
    bottom: int = Field(..., title="Bottom Overscan")
