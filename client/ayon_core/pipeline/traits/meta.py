"""Metadata traits."""
from typing import ClassVar, List

from pydantic import Field

from .trait import TraitBase


class Tagged(TraitBase):
    """Tagged trait model.

    This model represents a tagged trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        tags (List[str]): Tags.
    """

    name: ClassVar[str] = "Tagged"
    description: ClassVar[str] = "Tagged Trait Model"
    id: ClassVar[str] = "ayon.meta.Tagged.v1"
    tags: List[str] = Field(..., title="Tags")
