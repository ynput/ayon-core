"""Defines the base trait model."""
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



class TraitsData:
    """Traits data container.

    This model represents the data of a trait.

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


    def add(self, trait: TraitBase, *, exists_ok: bool=False) -> None:
        """Add a trait to the data.

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

    def remove(self,
               trait_id: Optional[str],
               trait: Optional[Type[TraitBase]]) -> None:
        """Remove a trait from the data.

        Args:
            trait_id (str, optional): Trait ID.
            trait (TraitBase, optional): Trait class.

        """
        if trait_id:
            self._data.pop(trait_id)
        elif trait:
            self._data.pop(trait.id)

    def has_trait(self,
                  trait_id: Optional[str]=None,
                  trait: Optional[Type[TraitBase]]=None) -> bool:
        """Check if the trait exists.

        Args:
            trait_id (str, optional): Trait ID.
            trait (TraitBase, optional): Trait class.

        Returns:
            bool: True if the trait exists, False otherwise.

        """
        if not trait_id:
            trait_id = trait.id
        return hasattr(self, trait_id)

    def get(self,
            trait_id: Optional[str]=None,
            trait: Optional[Type[TraitBase]]=None) -> Union[TraitBase, None]:
        """Get a trait from the data.

        Args:
            trait_id (str, optional): Trait ID.
            trait (TraitBase, optional): Trait class.

        Returns:
            TraitBase: Trait instance.

        """
        trait_class = None
        if trait_id:
            trait_class = self._get_trait_class(trait_id)
            if not trait_class:
                error_msg = f"Trait model with ID {trait_id} not found."
                raise ValueError(error_msg)

        if trait:
            trait_class = trait
            trait_id = trait.id

        if not trait_class and not trait_id:
            error_msg = "Trait ID or Trait class is required"
            raise ValueError(error_msg)

        return self._data[trait_id] if self._data.get(trait_id) else None

    def as_dict(self) -> dict:
        """Return the data as a dictionary.

        Returns:
            dict: Data dictionary.

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

    def __init__(self, traits: Optional[list[TraitBase]]):
        """Initialize the data."""
        self._data = {}
        if traits:
            for trait in traits:
                self.add(trait)
