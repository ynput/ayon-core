"""Defines the base trait model and representation."""
from __future__ import annotations

import inspect
import re
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, fields
from enum import Enum
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Optional,
    TypeVar,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

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

    @classmethod
    def from_dict(cls: type[T], data: dict) -> T:
        """Create a trait from a dictionary.

        This is the reverse of `as_dict()` and also accepts its JSON
        serialized form. Values are converted based on field type hints,
        so nested traits (e.g. `FileLocation` items of `FileLocations`),
        paths, regex patterns and enums are restored to their types.

        Args:
            data (dict): Trait data.

        Returns:
            TraitBase: Trait instance.

        """
        type_hints = _get_field_type_hints(cls)
        init_fields = {field.name for field in fields(cls) if field.init}
        kwargs = {}
        for key, value in data.items():
            if key in init_fields and key in type_hints:
                value = _convert_value(value, type_hints[key])
            kwargs[key] = value
        return cls(**kwargs)


def _get_field_type_hints(trait_class: type) -> dict[str, Any]:
    """Resolve field type hints of a trait class.

    Annotations are strings because of `from __future__ import annotations`
    and they are resolved in the module namespace of the class. If it is
    not possible (e.g. type imported only for type checking), values
    are not converted.
    """
    try:
        return get_type_hints(trait_class)
    except (NameError, TypeError):
        return {}


def _convert_value(value: Any, type_hint: Any) -> Any:  # noqa: PLR0911
    """Convert value to the type defined by type hint, if possible."""
    if value is None:
        return value

    origin = get_origin(type_hint)
    if origin is Union:
        args = [arg for arg in get_args(type_hint) if arg is not type(None)]
        if len(args) == 1:
            return _convert_value(value, args[0])
        return value

    if origin in (list, tuple, set):
        args = get_args(type_hint)
        if not args or not isinstance(value, (list, tuple)):
            return value
        return origin(_convert_value(item, args[0]) for item in value)

    if not isinstance(type_hint, type) or isinstance(value, type_hint):
        return value

    if issubclass(type_hint, Path) and isinstance(value, str):
        return Path(value)
    if type_hint is re.Pattern and isinstance(value, str):
        return re.compile(value)
    if issubclass(type_hint, Enum):
        if isinstance(value, str) and value in type_hint.__members__:
            return type_hint[value]
        return type_hint(value)
    if (
        issubclass(type_hint, TraitBase)
        and not inspect.isabstract(type_hint)
        and isinstance(value, dict)
    ):
        return type_hint.from_dict(value)
    return value


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
