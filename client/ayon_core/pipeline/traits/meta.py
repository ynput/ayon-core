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


class Variant(TraitBase):
    """Variant trait model.

    This model represents a variant of the representation.

    Example::

        Variant(variant="high")
        Variant(variant="prores444)

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        variant (str): Variant name.
    """

    name: ClassVar[str] = "Variant"
    description: ClassVar[str] = "Variant Trait Model"
    id: ClassVar[str] = "ayon.meta.Variant.v1"
    variant: str = Field(..., title="Variant")


class KeepOriginalLocation(TraitBase):
    """Keep files in its original location.

    Note:
        This is not a persistent trait.

    """
    name: ClassVar[str] = "KeepOriginalLocation"
    description: ClassVar[str] = "Keep Original Location Trait Model"
    id: ClassVar[str] = "ayon.meta.KeepOriginalLocation.v1"
    persistent: bool = Field(default=False, title="Persistent")

class KeepOriginalName(TraitBase):
    """Keep files in its original name.

    Note:
        This is not a persistent trait.

    """
    name: ClassVar[str] = "KeepOriginalName"
    description: ClassVar[str] = "Keep Original Name Trait Model"
    id: ClassVar[str] = "ayon.meta.KeepOriginalName.v1"
    persistent: bool = Field(default=False, title="Persistent")


class SourceApplication(TraitBase):
    """Metadata about the source (producing) application."""

    name: ClassVar[str] = "SourceApplication"
    description: ClassVar[str] = "Source Application Trait Model"
    id: ClassVar[str] = "ayon.meta.SourceApplication.v1"
    application: str = Field(..., title="Application Name")
    variant: str = Field(..., title="Application Variant (e.g. Pro)")
    version: str = Field(..., title="Application Version")
    platform: str = Field(..., title="Platform Name")
