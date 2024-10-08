"""Defines the base trait model."""
from pydantic import BaseModel, Field


def camelize(src: str) -> str:
    """Convert snake_case to camelCase."""
    components = src.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


class TraitBase(BaseModel):
    """Base trait model.

    This model must be used as a base for all trait models.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
            as ``ayon.content.LocatableBundle.v1``

    """

    class Config:
        """API model config."""

        orm_mode = True
        allow_population_by_field_name = True
        alias_generator = camelize

    name: str = Field(..., title="Trait name")
    description: str = Field(..., title="Trait description")
    # id should be: ayon.content.LocatableBundle.v1
    id: str = Field(..., title="Trait ID",
                    description="Unique identifier for the trait.")
