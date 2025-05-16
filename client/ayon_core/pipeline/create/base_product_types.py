"""Base product types for the pipeline creation process."""
from dataclasses import dataclass


@dataclass
class BaseProductType:
    """Base class for product types."""
    name: str
    description: str
    icon: str = "cube"
    color: str = "#FFFFFF"


@dataclass
class Image(BaseProductType):
    """Image product type."""
    name: str = "Image"
    description: str = "An image product."
    icon: str = "image"
    color: str = "#FF0000"


@dataclass
class Video(BaseProductType):
    """Video product type."""
    name: str = "Video"
    description: str = "A video product."
    icon: str = "video"
    color: str = "#00FF00"


@dataclass
class Audio(BaseProductType):
    """Audio product type."""
    name: str = "Audio"
    description: str = "An audio product."
    icon: str = "audio"
    color: str = "#0000FF"


@dataclass
class Model(BaseProductType):
    """Document product type."""
    name: str = "Model"
    description: str = "A model product."
    icon: str = "model"
    color: str = "#FFFF00"
