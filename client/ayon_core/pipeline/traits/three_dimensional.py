"""Two-dimensional image traits."""
from typing import ClassVar

from pydantic import Field

from .trait import TraitBase


class Spatial(TraitBase):
    """Spatial trait model.

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
