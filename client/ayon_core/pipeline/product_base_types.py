"""Product base types definition.

Type definitions for product base types and mapping to existing product types.

There is an abstract base class `ProductBaseType` that defines the interface
for product base types. All product base types should inherit from this class
and implement the required methods.

Maybe we should also consider deriving UI-related class so we can
have icon etc.

"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ProductBaseType(ABC):
    """Base class for all product base types.

    This class is used to define the interface for product base types.
    All product base types should inherit from this class and implement
    the required methods.

    It should handle the `data` field to store additional information about
    the product base type.

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


class Workfile(ProductBaseType):
    """Workfile product base type.

    This class represents the workfile product base type.
    It is used to define the interface for workfile product base types.
    """
    name = "workfile"
    label = "Workfile"
    description = "Workfile product base type."


class Pointcache(ProductBaseType):
    """Pointcache product base type.

    This class represents the pointcache product base type.
    It is used to define the interface for pointcache product base types.
    """
    name = "pointcache"
    label = "Pointcache"
    description = "Pointcache product base type."


class Camera(ProductBaseType):
    """Camera product base type.

    This class represents the camera product base type.
    It is used to define the interface for camera product base types.
    """
    name = "camera"
    label = "Camera"
    description = "Camera product base type."


class Layout(ProductBaseType):
    """Layout product base type.

    This class represents the layout product base type.
    It is used to define the interface for layout product base types.
    """
    name = "layout"
    label = "Layout"
    description = "Layout product base type."


class Look(ProductBaseType):
    """Look product base type.

    This class represents the look product base type.
    It is used to define the interface for look product base types.
    """
    name = "look"
    label = "Look"
    description = "Look product base type."


class Matchmove(ProductBaseType):
    """Matchmove product base type.

    This class represents the matchmove product base type.
    It is used to define the interface for matchmove product base types.
    """
    name = "matchmove"
    label = "Matchmove"
    description = "Matchmove Script product base type."


class USD(ProductBaseType):
    """USD product base type.

    This class represents the USD product base type.
    It is used to define the interface for USD product base types.
    """
    name = "usd"
    label = "USD"
    description = "USD product base type."


class Model(ProductBaseType):
    """Model product base type.

    This class represents the model product base type.
    It is used to define the interface for model product base types.
    """
    name = "model"
    label = "Model"
    description = "Model product base type."


class Image(ProductBaseType):
    """Image product base type.

    This class represents the image product base type.
    It is used to define the interface for image product base types.
    """
    name = "image"
    label = "Image"
    description = "Image product base type."


class Shot(ProductBaseType):
    """Shot product base type.

    This class represents the shot product base type.
    It is used to define the interface for shot product base types.
    """
    name = "shot"
    label = "Shot"
    description = "Shot product base type."


class Animation(ProductBaseType):
    """Animation product base type.

    This class represents the animation product base type.
    It is used to define the interface for animation product base types.
    """
    name = "animation"
    label = "Animation"
    description = "Animation product base type."


class Rig(ProductBaseType):
    """Rig product base type.

    This class represents the rig product base type.
    It is used to define the interface for rig product base types.
    """
    name = "rig"
    label = "Rig"
    description = "Rig product base type."
