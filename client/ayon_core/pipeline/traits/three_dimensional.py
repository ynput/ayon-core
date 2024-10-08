"""Two-dimensional image traits."""
from pydantic import Field

from .trait import TraitBase


class Spatial(TraitBase):
    """Spatial trait model.

    Attributes:
        up_axis (str): Up axis.
        handedness (str): Handedness.
        meters_per_unit (float): Meters per unit.

    """
    id: str = "ayon.content.Spatial.v1"
    name: str = "Spatial"
    description = "Spatial trait model."
    up_axis: str = Field(..., title="Up axis")
    handedness: str = Field(..., title="Handedness")
    meters_per_unit: float = Field(..., title="Meters per unit")
