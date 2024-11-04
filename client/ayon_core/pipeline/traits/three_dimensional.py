"""3D traits."""
from typing import ClassVar

from pydantic import Field

from .trait import TraitBase


class Spatial(TraitBase):
    """Spatial trait model.

    Trait describing spatial information. Up axis valid strings are
    "Y", "Z", "X". Handedness valid strings are "left", "right". Meters per
    unit is a float value.

    Example::

            Spatial(up_axis="Y", handedness="right", meters_per_unit=1.0)

    Todo:
        * Add value validation for up_axis and handedness.

    Attributes:
        up_axis (str): Up axis.
        handedness (str): Handedness.
        meters_per_unit (float): Meters per unit.

    """
    id: ClassVar[str] = "ayon.3d.Spatial.v1"
    name: ClassVar[str] = "Spatial"
    description: ClassVar[str] = "Spatial trait model."
    up_axis: str = Field(..., title="Up axis")
    handedness: str = Field(..., title="Handedness")
    meters_per_unit: float = Field(..., title="Meters per unit")


class Geometry(TraitBase):
    """Geometry type trait model.

    Type trait for geometry data.

    Sync with OpenAssetIO MediaCreation Traits.
    """

    id: ClassVar[str] = "ayon.3d.Geometry.v1"
    name: ClassVar[str] = "Geometry"
    description: ClassVar[str] = "Geometry trait model."

class Shader(TraitBase):
    """Shader trait model.

    Type trait for shader data.

    Sync with OpenAssetIO MediaCreation Traits.
    """

    id: ClassVar[str] = "ayon.3d.Shader.v1"
    name: ClassVar[str] = "Shader"
    description: ClassVar[str] = "Shader trait model."

class Lighting(TraitBase):
    """Lighting trait model.

    Type trait for lighting data.

    Sync with OpenAssetIO MediaCreation Traits.
    """

    id: ClassVar[str] = "ayon.3d.Lighting.v1"
    name: ClassVar[str] = "Lighting"
    description: ClassVar[str] = "Lighting trait model."

class IESProfile(TraitBase):
    """IES profile (IES-LM-64) type trait model.

    Sync with OpenAssetIO MediaCreation Traits.
    """

    id: ClassVar[str] = "ayon.3d.IESProfile.v1"
    name: ClassVar[str] = "IESProfile"
    description: ClassVar[str] = "IES profile trait model."
