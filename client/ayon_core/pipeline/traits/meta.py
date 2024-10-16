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


class TemplatePath(TraitBase):
    """TemplatePath trait model.

    This model represents a template path with formatting data.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        template_path (str): Template path.
        data (dict[str]): Formatting data.
    """

    name: ClassVar[str] = "TemplatePath"
    description: ClassVar[str] = "Template Path Trait Model"
    id: ClassVar[str] = "ayon.meta.TemplatePath.v1"
    template: str = Field(..., title="Template Path")
    data: dict = Field(..., title="Formatting Data")
