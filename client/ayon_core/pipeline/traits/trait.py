"""Defines the base trait model and representation."""
from __future__ import annotations

import inspect
import sys
from abc import ABC, abstractmethod
from collections import OrderedDict
from functools import lru_cache
from typing import ClassVar, Optional, Type, Union

import pydantic.alias_generators
from pydantic import AliasGenerator, BaseModel, ConfigDict


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



class Representation:
    """Representation of products.

    Representation defines collection of individual properties that describe
    the specific "form" of the product. Each property is represented by a
    trait therefore the Representation is a collection of traits.

    It holds methods to add, remove, get, and check for the existence of a
    trait in the representation. It also provides a method to get all the

    """
    _data: dict
    _module_blacklist: ClassVar[list[str]] = [
        "_", "builtins", "pydantic"]

    @lru_cache(maxsize=64)  # noqa: B019
    def _get_trait_class(self, trait_id: str) -> Union[Type[TraitBase], None]:
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

        """
        modules = sys.modules.copy()
        filtered_modules = modules.copy()
        for module_name in modules:
            for bl_module in self._module_blacklist:
                if module_name.startswith(bl_module):
                    filtered_modules.pop(module_name)

        for module in filtered_modules.values():
            if not module:
                continue
            for _, klass in inspect.getmembers(module, inspect.isclass):
                if inspect.isclass(klass) and \
                        issubclass(klass, TraitBase) and \
                        klass.id == trait_id:
                    return klass
        return None


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
        if not trait.id:
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

    def get_trait(self, trait: Type[TraitBase]) -> Union[TraitBase, None]:
        """Get a trait from the representation.

        Args:
            trait (TraitBase, optional): Trait class.

        Returns:
            TraitBase: Trait instance.

        """
        return self._data[trait.id] if self._data.get(trait.id) else None

    def get_trait_by_id(self, trait_id: str) -> Union[TraitBase, None]:
        """Get a trait from the representation by id.

        Args:
            trait_id (str): Trait ID.

        Returns:
            TraitBase: Trait instance.

        """
        trait_class = self._get_trait_class(trait_id)
        if not trait_class:
            error_msg = f"Trait model with ID {trait_id} not found."
            raise ValueError(error_msg)

        return self._data[trait_id] if self._data.get(trait_id) else None

    def get_traits(self,
                     traits: Optional[list[Type[TraitBase]]]=None) -> dict:
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

    def get_traits_by_ids(self, trait_ids: list[str]) -> dict:
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
        result = OrderedDict()
        for trait_id, trait in self._data.items():
            if not trait or not trait_id:
                continue
            result[trait_id] = OrderedDict(trait.dict())

        return result

    def __len__(self):
        """Return the length of the data."""
        return len(self._data)

    def __init__(self, traits: Optional[list[TraitBase]]=None):
        """Initialize the data."""
        self._data = {}
        if traits:
            for trait in traits:
                self.add_trait(trait)
