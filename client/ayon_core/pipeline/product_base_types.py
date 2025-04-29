"""Product base types definition.

Type definitions for product base types and mapping to existing product types.

There is an abstract base class `ProductBaseType` that defines the interface
for product base types. All product base types should inherit from this class
and implement the required methods.

Maybe we should also consider deriver UI related class so we can
have icon etc.

"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar


class ProductBaseType(ABC):
    """Base class for all product base types.

    This class is used to define the interface for product base types.
    All product base types should inherit from this class and implement
    the required methods.

    It should handle `data` field to store additional information about the
    product base type.

    Attributes:
        name (str): The name of the product base type.
        label (str): A description of the product base type.
        description (str): A detailed description of the product base type.

    """
    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the product base type."""

    @name.setter
    @abstractmethod
    def name(self, value: str) -> None:
        """Set the name of the product base type."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Label of the product base type."""

    @label.setter
    @abstractmethod
    def label(self, value: str) -> None:
        """Set the label of the product base type."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Description of the product base type."""

    @description.setter
    @abstractmethod
    def description(self, value: str) -> None:
        """Set the description of the product base type."""


class Image(ProductBaseType):
    """Image product base type.

    This class represents the image product base type.
    It is used to define the interface for image product base types.
    """
    name = "image"
    label = "Image"
    description = "Image product base type."


class Video(ProductBaseType):
    """Video product base type.

    This class represents the video product base type.
    It is used to define the interface for video product base types.
    """
    name = "video"
    label = "Video"
    description = "Video product base type."


class Audio(ProductBaseType):
    """Audio product base type.

    This class represents the audio product base type.
    It is used to define the interface for audio product base types.
    """
    name = "audio"
    label = "Audio"
    description = "Audio product base type."


class Document(ProductBaseType):
    """Document product base type.

    This class represents the document product base type.
    It is used to define the interface for document product base types.
    """
    name = "document"
    label = "Document"
    description = "Document product base type."


class Geometry(ProductBaseType):
    """Geometry product base type.

    This class represents the geometry product base type.
    It is used to define the interface for geometry product base types.
    """
    name = "geometry"
    label = "Geometry"
    description = "Geometry product base type."


class Animation(ProductBaseType):
    """Animation product base type.

    This class represents the animation product base type.
    It is used to define the interface for animation product base types.
    """
    name = "animation"
    label = "Animation"
    description = "Animation product base type."


class Workfile(ProductBaseType):
    """Workfile product base type.

    This class represents the workfile product base type.
    It is used to define the interface for workfile product base types.
    """
    name = "workfile"
    label = "Workfile"
    description = "Workfile product base type."


class ProductBaseTypeFactory:
    """Factory class for creating product base type instances.

    This class is used to create instances of product base types.
    It uses a mapping of product base type names to their corresponding
    classes to create instances of the desired product base type.
    """
    _product_base_type_map: ClassVar[dict[str, ProductBaseType]] = {
        "image": Image,
        "video": Video,
        "audio": Audio,
        "document": Document,
        "geometry": Geometry,
        "animation": Animation,
        "workfile": Workfile,
    }

    @classmethod
    def create_product_base_type(cls, name: str) -> ProductBaseType:
        """Create an instance of the specified product base type.

        Args:
            name (str): The name of the product base type.

        Returns:
            ProductBaseType: An instance of the specified product base type.

        Raises:
            ValueError: If the specified product base type does not exist.
        """
        if name not in cls._product_base_type_map:
            msg = f"Product base type '{name}' does not exist."
            raise ValueError(msg)

        return cls._product_base_type_map[name]()
