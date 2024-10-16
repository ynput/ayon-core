"""Lifecycle traits."""
from typing import ClassVar

from .trait import TraitBase


class Transient(TraitBase):
    """Transient trait model.

    This model represents a transient trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
        tags (List[str]): Tags.
    """

    name: ClassVar[str] = "Transient"
    description: ClassVar[str] = "Transient Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Transient.v1"


class Persistent(TraitBase):
    """Persistent trait model.

    This model represents a persistent trait.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "Persistent"
    description: ClassVar[str] = "Persistent Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Persistent.v1"
