"""Metadata traits."""
from typing import ClassVar

from ayon_core.pipeline.traits import TraitBase


class NewTestTrait(TraitBase):
    """New Test trait model.

    This model represents a tagged trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "New Test Trait"
    description: ClassVar[str] = (
        "This test trait is used for testing updating."
    )
    id: ClassVar[str] = "ayon.test.NewTestTrait.v999"


__all__ = ["NewTestTrait"]
