"""Defines the base trait model and representation."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Generic, Optional, TypeVar

if TYPE_CHECKING:
    from .representation import Representation


T = TypeVar("T", bound="TraitBase")


@dataclass
class TraitBase(ABC):
    """Base trait model.

    This model must be used as a base for all trait models.
    ``id``, ``name``, and ``description`` are abstract attributes that must be
    implemented in the derived classes.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Abstract attribute for ID."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Abstract attribute for name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Abstract attribute for description."""
        ...

    def validate_trait(self, representation: Representation) -> None:  # noqa: PLR6301
        """Validate the trait.

        This method should be implemented in the derived classes to validate
        the trait data. It can be used by traits to validate against other
        traits in the representation.

        Args:
            representation (Representation): Representation instance.

        """
        return

    @classmethod
    def get_version(cls) -> Optional[int]:
        # sourcery skip: use-named-expression
        """Get a trait version from ID.

        This assumes Trait ID ends with `.v{version}`. If not, it will
        return None.

        Returns:
            Optional[int]: Trait version

        """
        version_regex = r"v(\d+)$"
        match = re.search(version_regex, str(cls.id))
        return int(match[1]) if match else None

    @classmethod
    def get_versionless_id(cls) -> str:
        """Get a trait ID without a version.

        Returns:
            str: Trait ID without a version.

        """
        return re.sub(r"\.v\d+$", "", str(cls.id))

    def as_dict(self) -> dict:
        """Return a trait as a dictionary.

        Returns:
            dict: Trait as dictionary.

        """
        return asdict(self)


class IncompatibleTraitVersionError(Exception):
    """Incompatible trait version exception.

    This exception is raised when the trait version is incompatible with the
    current version of the trait.
    """


class UpgradableTraitError(Exception, Generic[T]):
    """Upgradable trait version exception.

    This exception is raised when the trait can upgrade existing data
    meant for older versions of the trait. It must implement an `upgrade`
    method that will take old trait data as an argument to handle the upgrade.
    """

    trait: T
    old_data: dict


class LooseMatchingTraitError(Exception, Generic[T]):
    """Loose matching trait exception.

    This exception is raised when the trait is found with a loose matching
    criteria.
    """

    found_trait: T
    expected_id: str


class TraitValidationError(Exception):
    """Trait validation error exception.

    This exception is raised when the trait validation fails.
    """

    def __init__(self, scope: str, message: str):
        """Initialize the exception.

        We could determine the scope from the stack in the future,
        provided the scope is always Trait name.

        Args:
            scope (str): Scope of the error.
            message (str): Error message.

        """
        super().__init__(f"{scope}: {message}")


class MissingTraitError(TypeError):
    """Missing trait error exception.

    This exception is raised when the trait is missing.
    """
