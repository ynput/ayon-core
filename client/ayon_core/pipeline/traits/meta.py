"""Metadata traits."""
from typing import ClassVar, List

from pydantic import Field

from .trait import TraitBase


class Tagged(TraitBase):
    """Tagged trait model.

    This trait can hold list of tags.

    Example::

        Tagged(tags=["tag1", "tag2"])

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
    Template path can be Anatomy template and data is used to format it.

    Example::

        TemplatePath(template="path/{key}/file", data={"key": "to"})

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        template (str): Template path.
        data (dict[str]): Formatting data.
    """

    name: ClassVar[str] = "TemplatePath"
    description: ClassVar[str] = "Template Path Trait Model"
    id: ClassVar[str] = "ayon.meta.TemplatePath.v1"
    template: str = Field(..., title="Template Path")
    data: dict = Field(..., title="Formatting Data")
