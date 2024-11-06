"""Lifecycle traits."""
from typing import ClassVar

from .trait import TraitBase


class Transient(TraitBase):
    """Transient trait model.

    Transient trait marks representation as transient. Such representations
    are not persisted in the system.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "Transient"
    description: ClassVar[str] = "Transient Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Transient.v1"

    def validate(self, representation) -> bool:  # noqa: ANN001
        """Validate representation is not Persistent.

        Args:
            representation (Representation): Representation model.

        Returns:
            bool: True if representation is valid, False otherwise.
        """
        return not representation.contains_trait(Persistent)


class Persistent(TraitBase):
    """Persistent trait model.

    Persistent trait is opposite to transient trait. It marks representation
    as persistent. Such representations are persisted in the system (e.g. in
    the database).

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be namespaced trait name with version
    """

    name: ClassVar[str] = "Persistent"
    description: ClassVar[str] = "Persistent Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Persistent.v1"

    def validate(self, representation) -> bool:  # noqa: ANN001
        """Validate representation is not Transient.

        Args:
            representation (Representation): Representation model.

        Returns:
            bool: True if representation is valid, False otherwise.
        """
        return not representation.contains_trait(Transient)
