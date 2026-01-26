"""Defines the base trait model and representation."""
from __future__ import annotations

import contextlib
import re
import uuid
from typing import (
    Generic,
    ItemsView,
    Optional,
    Type,
    TypeVar,
    Union,
)

from .trait import (
    IncompatibleTraitVersionError,
    MissingTraitError,
    TraitBase,
    TraitValidationError,
    UpgradableTraitError,
)

T = TypeVar("T", bound="TraitBase")


def _get_version_from_id(_id: str) -> Optional[int]:
    """Get the version from ID.

    Args:
        _id (str): ID.

    Returns:
        int: Version.

    """
    match = re.search(r"v(\d+)$", _id)
    return int(match[1]) if match else None


class Representation(Generic[T]):  # noqa: PLR0904
    """Representation of products.

    Representation defines a collection of individual properties that describe
    the specific "form" of the product. A trait represents a set of
    properties therefore, the Representation is a collection of traits.

    It holds methods to add, remove, get, and check for the existence of a
    trait in the representation.

    Note:
        `PLR0904` is the rule for checking the number of public methods
        in a class.

    Arguments:
        name (str): Representation name. Must be unique within instance.
        representation_id (str): Representation ID.
    """

    _data: dict[str, T]
    name: str
    representation_id: str

    def __hash__(self):
        """Return hash of the representation ID."""
        return hash(self.representation_id)

    def __getitem__(self, key: str) -> T:
        """Get the trait by ID.

        Args:
            key (str): Trait ID.

        Returns:
            TraitBase: Trait instance.

        """
        return self.get_trait_by_id(key)

    def __setitem__(self, key: str, value: T) -> None:
        """Set the trait by ID.

        Args:
            key (str): Trait ID.
            value (TraitBase): Trait instance.

        """
        with contextlib.suppress(KeyError):
            self._data.pop(key)

        self.add_trait(value)

    def __delitem__(self, key: str) -> None:
        """Remove the trait by ID.

        Args:
            key (str): Trait ID.


        """
        self.remove_trait_by_id(key)

    def __contains__(self, key: str) -> bool:
        """Check if the trait exists by ID.

        Args:
            key (str): Trait ID.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        return self.contains_trait_by_id(key)

    def __iter__(self):
        """Return the trait ID iterator."""
        return iter(self._data)

    def __str__(self):
        """Return the representation name."""
        return self.name

    def items(self) -> ItemsView[str, T]:
        """Return the traits as items."""
        return ItemsView(self._data)

    def add_trait(self, trait: T, *, exists_ok: bool = False) -> None:
        """Add a trait to the Representation.

        Args:
            trait (TraitBase): Trait to add.
            exists_ok (bool, optional): If True, do not raise an error if the
                trait already exists. Defaults to False.

        Raises:
            ValueError: If the trait ID is not provided, or the trait already
                exists.

        """
        if not hasattr(trait, "id"):
            error_msg = f"Invalid trait {trait} - ID is required."
            raise ValueError(error_msg)
        if trait.id in self._data and not exists_ok:
            error_msg = f"Trait with ID {trait.id} already exists."
            raise ValueError(error_msg)
        self._data[trait.id] = trait

    def add_traits(
            self, traits: list[T], *, exists_ok: bool = False) -> None:
        """Add a list of traits to the Representation.

        Args:
            traits (list[TraitBase]): List of traits to add.
            exists_ok (bool, optional): If True, do not raise an error if the
                trait already exists. Defaults to False.

        """
        for trait in traits:
            self.add_trait(trait, exists_ok=exists_ok)

    def remove_trait(self, trait: Type[TraitBase]) -> None:
        """Remove a trait from the data.

        Args:
            trait (TraitBase, optional): Trait class.

        Raises:
            ValueError: If the trait is not found.

        """
        try:
            self._data.pop(str(trait.id))
        except KeyError as e:
            error_msg = f"Trait with ID {trait.id} not found."
            raise ValueError(error_msg) from e

    def remove_trait_by_id(self, trait_id: str) -> None:
        """Remove a trait from the data by its ID.

        Args:
            trait_id (str): Trait ID.

        Raises:
            ValueError: If the trait is not found.

        """
        try:
            self._data.pop(trait_id)
        except KeyError as e:
            error_msg = f"Trait with ID {trait_id} not found."
            raise ValueError(error_msg) from e

    def remove_traits(self, traits: list[Type[T]]) -> None:
        """Remove a list of traits from the Representation.

        If no trait IDs or traits are provided, all traits will be removed.

        Args:
            traits (list[TraitBase]): List of trait classes.

        """
        if not traits:
            self._data = {}
            return

        for trait in traits:
            self.remove_trait(trait)

    def remove_traits_by_id(self, trait_ids: list[str]) -> None:
        """Remove a list of traits from the Representation by their ID.

        If no trait IDs or traits are provided, all traits will be removed.

        Args:
            trait_ids (list[str], optional): List of trait IDs.

        """
        for trait_id in trait_ids:
            self.remove_trait_by_id(trait_id)

    def has_traits(self) -> bool:
        """Check if the Representation has any traits.

        Returns:
            bool: True if the Representation has any traits, False otherwise.

        """
        return bool(self._data)

    def contains_trait(self, trait: Type[T]) -> bool:
        """Check if the trait exists in the Representation.

        Args:
            trait (TraitBase): Trait class.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        return bool(self._data.get(str(trait.id)))

    def contains_trait_by_id(self, trait_id: str) -> bool:
        """Check if the trait exists using trait id.

        Args:
            trait_id (str): Trait ID.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        return bool(self._data.get(trait_id))

    def contains_traits(self, traits: list[Type[T]]) -> bool:
        """Check if the traits exist.

        Args:
            traits (list[TraitBase], optional): List of trait classes.

        Returns:
            bool: True if all traits exist, False otherwise.

        """
        return all(self.contains_trait(trait=trait) for trait in traits)

    def contains_traits_by_id(self, trait_ids: list[str]) -> bool:
        """Check if the traits exist by id.

        If no trait IDs or traits are provided, it will check if the
        representation has any traits.

        Args:
            trait_ids (list[str]): List of trait IDs.

        Returns:
            bool: True if all traits exist, False otherwise.

        """
        return all(
            self.contains_trait_by_id(trait_id) for trait_id in trait_ids
        )

    def get_trait(self, trait: Type[T]) -> T:
        """Get a trait from the representation.

        Args:
            trait (TraitBase, optional): Trait class.

        Returns:
            TraitBase: Trait instance.

        Raises:
            MissingTraitError: If the trait is not found.

        """
        try:
            return self._data[str(trait.id)]
        except KeyError as e:
            msg = f"Trait with ID {trait.id} not found."
            raise MissingTraitError(msg) from e

    def get_trait_by_id(self, trait_id: str) -> T:
        # sourcery skip: use-named-expression
        """Get a trait from the representation by id.

        Args:
            trait_id (str): Trait ID.

        Returns:
            TraitBase: Trait instance.

        Raises:
            MissingTraitError: If the trait is not found.

        """
        version = _get_version_from_id(trait_id)
        if version:
            try:
                return self._data[trait_id]
            except KeyError as e:
                msg = f"Trait with ID {trait_id} not found."
                raise MissingTraitError(msg) from e

        result = next(
            (
                self._data.get(trait_id)
                for trait_id in self._data
                if trait_id.startswith(trait_id)
            ),
            None,
        )
        if result is None:
            msg = f"Trait with ID {trait_id} not found."
            raise MissingTraitError(msg)
        return result

    def get_traits(self,
                     traits: Optional[list[Type[T]]] = None
     ) -> dict[str, T]:
        """Get a list of traits from the representation.

        If no trait IDs or traits are provided, all traits will be returned.

        Args:
            traits (list[TraitBase], optional): List of trait classes.

        Returns:
            dict: Dictionary of traits.

        """
        result: dict[str, T] = {}
        if not traits:
            for trait_id in self._data:
                result[trait_id] = self.get_trait_by_id(trait_id=trait_id)
            return result

        for trait in traits:
            result[str(trait.id)] = self.get_trait(trait=trait)
        return result

    def get_traits_by_ids(self, trait_ids: list[str]) -> dict[str, T]:
        """Get a list of traits from the representation by their id.

        If no trait IDs or traits are provided, all traits will be returned.

        Args:
            trait_ids (list[str]): List of trait IDs.

        Returns:
            dict: Dictionary of traits.

        """
        return {
            trait_id: self.get_trait_by_id(trait_id)
            for trait_id in trait_ids
        }

    def traits_as_dict(self) -> dict:
        """Return the traits from Representation data as a dictionary.

        Returns:
            dict: Traits data dictionary.

        """
        return {
            trait_id: trait.as_dict()
            for trait_id, trait in self._data.items()
            if trait and trait_id
        }

    def __len__(self):
        """Return the length of the data."""
        return len(self._data)

    def __init__(
            self,
            name: str,
            representation_id: Optional[str] = None,
            traits: Optional[list[T]] = None):
        """Initialize the data.

        Args:
            name (str): Representation name. Must be unique within instance.
            representation_id (str, optional): Representation ID.
            traits (list[TraitBase], optional): List of traits.

        """
        self.name = name
        self.representation_id = representation_id or uuid.uuid4().hex
        self._data = {}
        if traits:
            for trait in traits:
                self.add_trait(trait)

    @staticmethod
    def _get_version_from_id(trait_id: str) -> Union[int, None]:
        # sourcery skip: use-named-expression
        """Check if the trait has a version specified.

        Args:
            trait_id (str): Trait ID.

        Returns:
            int: Trait version.
            None: If the trait id does not have a version.

        """
        version_regex = r"v(\d+)$"
        match = re.search(version_regex, trait_id)
        return int(match[1]) if match else None

    def __eq__(self, other: object) -> bool:  # noqa: PLR0911
        """Check if the representation is equal to another.

        Args:
            other (Representation): Representation to compare.

        Returns:
            bool: True if the representations are equal, False otherwise.

        """
        if not isinstance(other, Representation):
            return False

        if self.representation_id != other.representation_id:
            return False

        if self.name != other.name:
            return False

        # number of traits
        if len(self) != len(other):
            return False

        for trait_id, trait in self._data.items():
            if trait_id not in other._data:
                return False
            if trait != other._data[trait_id]:
                return False

        return True

    @classmethod
    def get_trait_class_by_trait_id(cls, trait_id: str) -> Optional[Type[T]]:
        """Get the trait class for the given trait ID.

        Args:
            trait_id (str): Trait ID.

        Returns:
            type[TraitBase]: Trait class.
            None: If the trait class is not found.

        Raises:
            IncompatibleTraitVersionError: If the trait version is incompatible
                with the current version of the trait.
            UpgradableTraitError: If the trait version is upgradable to a newer
                version.

        Note:
            `ignore[return-value]` can be removed in future versions of Python
            where the Generics support is better.

        """
        # Iteratively collect all subclasses
        trait_classes = set()
        to_process = [TraitBase]

        while to_process:
            current = to_process.pop()
            subclasses = current.__subclasses__()
            trait_classes.update(subclasses)
            to_process.extend(subclasses)

        # 1. Search for the exact match
        for trait_class in trait_classes:
            if getattr(trait_class, "id", None) == trait_id:
                return trait_class  # type: ignore[return-value]

        # 2. Search for fuzzy matches (same base ID, different version)
        req_version = _get_version_from_id(trait_id)
        # Determine base ID (e.g., 'ayon.trait' from 'ayon.trait.v1')
        base_id = trait_id
        if req_version is not None:
            base_id = re.sub(r"\.v\d+$", "", trait_id)

        candidates = []
        for trait_class in trait_classes:
            t_id = getattr(trait_class, "id", "")
            if not t_id:
                continue

            t_ver = _get_version_from_id(t_id)
            t_base = (
                re.sub(r"\.v\d+$", "", t_id) if t_ver is not None else t_id
            )

            if t_base == base_id:
                candidates.append(
                    (trait_class, t_ver or 0)
                )

        if not candidates:
            return None  # type: ignore[return-value]

        # Find the highest version among candidates
        found_trait, found_version = max(candidates, key=lambda x: x[1])

        if req_version is None:
            return found_trait  # type: ignore[return-value]

        if found_version == 0:
            msg = (
                f"Trait {found_trait.id} found with no version, "
                "but requested version is specified."
            )
            raise IncompatibleTraitVersionError(msg)

        if req_version > found_version:
            error_msg = (
                f"Requested trait version {req_version} is "
                f"higher than the found trait version {found_version}."
            )
            raise IncompatibleTraitVersionError(error_msg)

        if req_version < found_version:
            if hasattr(found_trait, "upgrade"):
                error_msg = (
                    "Requested trait version "
                    f"{req_version} is lower "
                    f"than the found trait version {found_version}."
                )
                error: UpgradableTraitError = UpgradableTraitError(error_msg)
                error.trait = found_trait
                raise error
            # If the explicit version was requested, matches failed,
            # and no upgrade path exists, we return None (effectively
            # "Not Found" for thatversion)
            return None  # type: ignore[return-value]

        return found_trait  # type: ignore[return-value]

    @classmethod
    def from_dict(
            cls: Type[Representation],
            name: str,
            representation_id: Optional[str] = None,
            trait_data: Optional[dict] = None) -> Representation:
        """Create a representation from a dictionary.

        Args:
            name (str): Representation name.
            representation_id (str, optional): Representation ID.
            trait_data (dict): Representation data. Dictionary with keys
                as trait ids and values as trait data. Example::

                    {
                        "ayon.2d.PixelBased.v1": {
                            "display_window_width": 1920,
                            "display_window_height": 1080
                        },
                        "ayon.2d.Planar.v1": {
                            "channels": 3
                        }
                    }

        Returns:
            Representation: Representation instance.

        Raises:
            ValueError: If the trait model with ID is not found.
            TypeError: If the trait data is not a dictionary.
            IncompatibleTraitVersionError: If the trait version is incompatible

        """
        if not trait_data:
            trait_data = {}
        traits = []
        for trait_id, value in trait_data.items():
            if not isinstance(value, dict):
                msg = (
                    f"Invalid trait data for trait ID {trait_id}. "
                    "Trait data must be a dictionary."
                )
                raise TypeError(msg)

            try:
                trait_class = cls.get_trait_class_by_trait_id(trait_id)
            except UpgradableTraitError as e:
                # we found a newer version of trait, we will upgrade the data
                if hasattr(e.trait, "upgrade"):
                    traits.append(e.trait.upgrade(value))
                else:
                    msg = (
                        f"Newer version of trait {e.trait.id} found "
                        f"for requested {trait_id} but without "
                        "upgrade method."
                    )
                    raise IncompatibleTraitVersionError(msg) from e
            else:
                if not trait_class:
                    error_msg = f"Trait model with ID {trait_id} not found."
                    raise ValueError(error_msg)

                traits.append(trait_class(**value))

        return cls(
            name=name, representation_id=representation_id, traits=traits)

    def validate(self) -> None:
        """Validate the representation.

        This method will validate all the traits in the representation.

        Raises:
            TraitValidationError: If the trait is invalid within representation

        """
        errors = []
        for trait in self._data.values():
            # we do this in the loop to catch all the errors
            try:
                trait.validate_trait(self)
            except TraitValidationError as e:  # noqa: PERF203
                errors.append(str(e))
        if errors:
            msg = "\n".join(errors)
            scope = self.name
            raise TraitValidationError(scope, msg)
