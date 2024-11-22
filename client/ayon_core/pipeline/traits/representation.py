"""Defines the base trait model and representation."""
from __future__ import annotations

import inspect
import re
import sys
import uuid
from functools import lru_cache
from typing import ClassVar, Optional, Type, TypeVar, Union

from .trait import (
    IncompatibleTraitVersionError,
    LooseMatchingTraitError,
    MissingTraitError,
    TraitBase,
    UpgradableTraitError,
)

T = TypeVar("T", bound=TraitBase)


def _get_version_from_id(_id: str) -> int:
    """Get version from ID.

    Args:
        _id (str): ID.

    Returns:
        int: Version.

    """
    match = re.search(r"v(\d+)$", _id)
    return int(match[1]) if match else None


class Representation:
    """Representation of products.

    Representation defines collection of individual properties that describe
    the specific "form" of the product. Each property is represented by a
    trait therefore the Representation is a collection of traits.

    It holds methods to add, remove, get, and check for the existence of a
    trait in the representation. It also provides a method to get all the

    Arguments:
        name (str): Representation name. Must be unique within instance.
        representation_id (str): Representation ID.

    """
    _data: dict
    _module_blacklist: ClassVar[list[str]] = [
        "_", "builtins", "pydantic"]
    name: str
    representation_id: str

    def __hash__(self):
        """Return hash of the representation ID."""
        return hash(self.representation_id)

    def add_trait(self, trait: TraitBase, *, exists_ok: bool=False) -> None:
        """Add a trait to the Representation.

        Args:
            trait (TraitBase): Trait to add.
            exists_ok (bool, optional): If True, do not raise an error if the
                trait already exists. Defaults to False.

        Raises:
            ValueError: If the trait ID is not provided or the trait already
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
            self, traits: list[TraitBase], *, exists_ok: bool=False) -> None:
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
            self._data.pop(trait.id)
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

    def remove_traits(self, traits: list[Type[TraitBase]]) -> None:
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

    def contains_trait(self, trait: Type[TraitBase]) -> bool:
        """Check if the trait exists in the Representation.

        Args:
            trait (TraitBase): Trait class.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        return bool(self._data.get(trait.id))

    def contains_trait_by_id(self, trait_id: str) -> bool:
        """Check if the trait exists using trait id.

        Args:
            trait_id (str): Trait ID.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        return  bool(self._data.get(trait_id))

    def contains_traits(self, traits: list[Type[TraitBase]]) -> bool:
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

    def get_trait(self, trait: Type[T]) -> Union[T]:
        """Get a trait from the representation.

        Args:
            trait (TraitBase, optional): Trait class.

        Returns:
            TraitBase: Trait instance.

        Raises:
            MissingTraitError: If the trait is not found.

        """
        try:
            return self._data[trait.id]
        except KeyError as e:
            msg = f"Trait with ID {trait.id} not found."
            raise MissingTraitError(msg) from e

    def get_trait_by_id(self, trait_id: str) -> Union[T]:
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
        if not result:
            msg = f"Trait with ID {trait_id} not found."
            raise MissingTraitError(msg)
        return result

    def get_traits(self,
                     traits: Optional[list[Type[TraitBase]]]=None
                   ) -> dict[str, T]:
        """Get a list of traits from the representation.

        If no trait IDs or traits are provided, all traits will be returned.

        Args:
            traits (list[TraitBase], optional): List of trait classes.

        Returns:
            dict: Dictionary of traits.

        """
        result = {}
        if not traits:
            for trait_id in self._data:
                result[trait_id] = self.get_trait_by_id(trait_id=trait_id)
            return result

        for trait in traits:
             result[trait.id] = self.get_trait(trait=trait)
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
            trait_id: trait.model_dump()
            for trait_id, trait in self._data.items()
            if trait and trait_id
        }

    def __len__(self):
        """Return the length of the data."""
        return len(self._data)

    def __init__(
            self,
            name: str,
            representation_id: Optional[str]=None,
            traits: Optional[list[TraitBase]]=None):
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
        """Check if the trait has version specified.

        Args:
            trait_id (str): Trait ID.

        Returns:
            int: Trait version.
            None: If the trait id does not have a version.

        """
        version_regex = r"v(\d+)$"
        match = re.search(version_regex, trait_id)
        return int(match[1]) if match else None

    def __eq__(self, other: Representation) -> bool:  # noqa: PLR0911
        """Check if the representation is equal to another.

        Args:
            other (Representation): Representation to compare.

        Returns:
            bool: True if the representations are equal, False otherwise.

        """
        if self.representation_id != other.representation_id:
            return False

        if not isinstance(other, Representation):
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
            for key, value in trait.model_dump().items():
                if value != other._data[trait_id].model_dump().get(key):
                    return False

        return True

    @classmethod
    @lru_cache(maxsize=64)
    def _get_possible_trait_classes_from_modules(
            cls,
            trait_id: str) -> set[type[TraitBase]]:
        """Get possible trait classes from modules.

        Args:
            trait_id (str): Trait ID.

        Returns:
            set[type[TraitBase]]: Set of trait classes.

        """
        modules = sys.modules.copy()
        filtered_modules = modules.copy()
        for module_name in modules:
            for bl_module in cls._module_blacklist:
                if module_name.startswith(bl_module):
                    filtered_modules.pop(module_name)

        trait_candidates = set()
        for module in filtered_modules.values():
            if not module:
                continue
            for _, klass in inspect.getmembers(module, inspect.isclass):
                if inspect.isclass(klass) \
                        and issubclass(klass, TraitBase) \
                        and str(klass.id).startswith(trait_id):
                    trait_candidates.add(klass)
        return trait_candidates

    @classmethod
    @lru_cache(maxsize=64)
    def _get_trait_class(
            cls, trait_id: str) -> Union[Type[TraitBase], None]:
        """Get the trait class with corresponding to given ID.

        This method will search for the trait class in all the modules except
        the blacklisted modules. There is some issue in Pydantic where
        ``issubclass`` is not working properly so we are excluding explicitly
        modules with offending classes. This list can be updated as needed to
        speed up the search.

        Args:
            trait_id (str): Trait ID.

        Returns:
            Type[TraitBase]: Trait class.

        Raises:
            LooseMatchingTraitError: If the trait is found with a loose
                matching criteria. This exception will include the trait
                class that was found and the expected trait ID. Additional
                downstream logic must decide how to handle this error.

        """
        version = cls._get_version_from_id(trait_id)

        trait_candidates = cls._get_possible_trait_classes_from_modules(
            trait_id
        )

        for trait_class in trait_candidates:
            if trait_class.id == trait_id:
                # we found direct match
                return trait_class

        # if we didn't find direct match, we will search for the highest
        # version of the trait.
        if not version:
            # sourcery skip: use-named-expression
            trait_versions = [
                trait_class for trait_class in trait_candidates
                if re.match(
                    rf"{trait_id}.v(\d+)$", str(trait_class.id))
            ]
            if trait_versions:
                def _get_version_by_id(trait_klass: Type[TraitBase]) -> int:
                    match = re.search(r"v(\d+)$", str(trait_klass.id))
                    return int(match[1]) if match else 0

                error = LooseMatchingTraitError(
                    "Found trait that might match.")
                error.found_trait = max(
                    trait_versions, key=_get_version_by_id)
                error.expected_id = trait_id
                raise error

        return None

    @classmethod
    def get_trait_class_by_trait_id(cls, trait_id: str) -> type[TraitBase]:
        """Get the trait class for the given trait ID.

        Args:
            trait_id (str): Trait ID.

        Returns:
            type[TraitBase]: Trait class.

        Raises:
            IncompatibleTraitVersionError: If the trait version is incompatible
                with the current version of the trait.
            UpgradableTraitError: If the trait can upgrade existing data
                meant for older versions of the trait.
            ValueError: If the trait model with the given ID is not found.

        """
        trait_class = None
        try:
            trait_class = cls._get_trait_class(trait_id=trait_id)
        except LooseMatchingTraitError as e:
            requested_version = _get_version_from_id(trait_id)
            found_version = _get_version_from_id(e.found_trait.id)

            if not requested_version:
                trait_class = e.found_trait

            else:
                if requested_version > found_version:
                    error_msg = (
                        f"Requested trait version {requested_version} is "
                        f"higher than the found trait version {found_version}."
                    )
                    raise IncompatibleTraitVersionError(error_msg) from e

                if requested_version < found_version and hasattr(
                        e.found_trait, "upgrade"):
                    error_msg = (
                        "Requested trait version "
                        f"{requested_version} is lower "
                        f"than the found trait version {found_version}."
                    )
                    error = UpgradableTraitError(error_msg)
                    error.trait = e.found_trait
                    raise error from e
        return trait_class

    @classmethod
    def from_dict(
            cls,
            name: str,
            representation_id: Optional[str]=None,
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

        """
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
                # we found newer version of trait, we will upgrade the data
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


    def validate(self) -> bool:
        """Validate the representation.

        This method will validate all the traits in the representation.

        Returns:
            bool: True if the representation is valid, False otherwise.

        """
        return all(trait.validate(self) for trait in self._data.values())
