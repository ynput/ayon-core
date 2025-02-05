"""Metadata traits."""
from __future__ import annotations

from typing import ClassVar, List, Optional

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
    """Metadata about the source (producing) application.

    This can be useful in cases, where this information is
    needed but it cannot be determined from other means - like
    .txt files used for various motion tracking applications that
    must be interpreted by the loader.

    Note that this is not really connected to any logic in
    ayon-applications addon.

    """

    name: ClassVar[str] = "SourceApplication"
    description: ClassVar[str] = "Source Application Trait Model"
    id: ClassVar[str] = "ayon.meta.SourceApplication.v1"
    application: str = Field(..., title="Application Name")
    variant: Optional[str] = Field(
        None, title="Application Variant (e.g. Pro)")
    version: Optional[str] = Field(
        None, title="Application Version")
    platform: Optional[str] = Field(
        None, title="Platform Name (e.g. Windows)")
    host_name: Optional[str] = Field(
        None, title="AYON host Name if applicable")


class IntendedUse(TraitBase):
    """Intended use of the representation.

    This trait describes the intended use of the representation. It
    can be used in cases, where the other traits are not enough to
    describe the intended use. For example txt file with tracking
    points can be used as corner pin in After Effect but not in Nuke.
    """

    name: ClassVar[str] = "IntendedUse"
    description: ClassVar[str] = "Intended Use Trait Model"
    id: ClassVar[str] = "ayon.meta.IntendedUse.v1"
    use: str = Field(..., title="Intended Use")
