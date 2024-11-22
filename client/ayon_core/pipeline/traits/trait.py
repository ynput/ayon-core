"""Defines the base trait model and representation."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

import pydantic.alias_generators
from pydantic import (
    AliasGenerator,
    BaseModel,
    ConfigDict,
)

if TYPE_CHECKING:
    from .representation import Representation


class TraitBase(ABC, BaseModel):
    """Base trait model.

    This model must be used as a base for all trait models.
    It is using Pydantic BaseModel for serialization and validation.
    ``id``, ``name``, and ``description`` are abstract attributes that must be
    implemented in the derived classes.

    """

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=pydantic.alias_generators.to_camel,
        )
    )

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

    def validate(self, representation: Representation) -> None:
        """Validate the trait.

        This method should be implemented in the derived classes to validate
        the trait data. It can be used by traits to validate against other
        traits in the representation.

        Args:
            representation (Representation): Representation instance.

        Raises:
            TraitValidationError: If the trait is invalid
                within representation.

        """
        return

    @classmethod
    def get_version(cls) -> Optional[int]:
        # sourcery skip: use-named-expression
        """Get trait version from ID.

        This assumes Trait ID ends with `.v{version}`. If not, it will
        return None.

        """
        version_regex = r"v(\d+)$"
        match = re.search(version_regex, str(cls.id))
        return int(match[1]) if match else None

    @classmethod
    def get_versionless_id(cls) -> str:
        """Get trait ID without version.

        Returns:
            str: Trait ID without version.

        """
        return re.sub(r"\.v\d+$", "", str(cls.id))






class IncompatibleTraitVersionError(Exception):
    """Incompatible trait version exception.

    This exception is raised when the trait version is incompatible with the
    current version of the trait.
    """


class UpgradableTraitError(Exception):
    """Upgradable trait version exception.

    This exception is raised when the trait can upgrade existing data
    meant for older versions of the trait. It must implement `upgrade`
    method that will take old trait data as argument to handle the upgrade.
    """

    trait: TraitBase
    old_data: dict

class LooseMatchingTraitError(Exception):
    """Loose matching trait exception.

    This exception is raised when the trait is found with a loose matching
    criteria.
    """

    found_trait: TraitBase
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
