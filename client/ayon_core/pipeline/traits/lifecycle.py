"""Lifecycle traits."""
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from .trait import TraitBase, TraitValidationError


@dataclass
class Transient(TraitBase):
    """Transient trait model.

    Transient trait marks representation as transient. Such representations
    are not persisted in the system.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with the version
    """

    name: ClassVar[str] = "Transient"
    description: ClassVar[str] = "Transient Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Transient.v1"
    persistent: ClassVar[bool] = True  # see note in Persistent

    def validate_trait(self, representation) -> None:  # noqa: ANN001
        """Validate representation is not Persistent.

        Args:
            representation (Representation): Representation model.

        Raises:
            TraitValidationError: If representation is marked as both
                Persistent and Transient.

        """
        if representation.contains_trait(Persistent):
            msg = "Representation is marked as both Persistent and Transient."
            raise TraitValidationError(self.name, msg)


@dataclass
class Persistent(TraitBase):
    """Persistent trait model.

    Persistent trait is opposite to transient trait. It marks representation
    as persistent. Such representations are persisted in the system (e.g. in
    the database).

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with the version
    """

    name: ClassVar[str] = "Persistent"
    description: ClassVar[str] = "Persistent Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.Persistent.v1"
    # Note that this affects the persistence of the trait itself, not
    # the representation. This is a class variable, so it is shared
    # among all instances of the class.
    persistent: bool = True

    def validate_trait(self, representation) -> None:  # noqa: ANN001
        """Validate representation is not Transient.

        Args:
            representation (Representation): Representation model.

        Raises:
            TraitValidationError: If representation is marked
                as both Persistent and Transient.

        """
        if representation.contains_trait(Transient):
            msg = "Representation is marked as both Persistent and Transient."
            raise TraitValidationError(self.name, msg)


@dataclass
class StagingDirectory(TraitBase):
    """Staging directory of representation files during publishing.

    Directory where the files were created before they are integrated
    (legacy representation "stagingDir"). Files of persistent staging
    directory are not removed by publish cleanup (legacy representation
    "stagingDir_persistent").

    Representation without this trait has its files staged in their parent
    directory and persistence is given by its instance.

    Note:
        This is not a persistent trait - the staging directory is not
        stored with the representation.

    Attributes:
        name (str): Trait name.
        description (str): Trait description.
        id (str): id should be a namespaced trait name with the version
        path (Path): Staging directory.
        is_persistent (bool): Files in the staging directory must be kept
            after publishing.

    """

    name: ClassVar[str] = "StagingDirectory"
    description: ClassVar[str] = "Staging Directory Trait Model"
    id: ClassVar[str] = "ayon.lifecycle.StagingDirectory.v1"
    persistent: ClassVar[bool] = False
    path: Path
    is_persistent: bool = False
