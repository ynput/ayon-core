"""Conditions evaluated against values of attribute definitions.

Conditions are used e.g. to define when an attribute definition is
visible based on values of other attribute definitions.

Example:
    ```python
    from ayon_core.lib import (
        BoolDef,
        EnumDef,
        NumberDef,
        AndCondition,
        ValueCondition,
    )

    attr_defs = [
        BoolDef("use_custom_range", default=False),
        EnumDef("mode", items=["frames", "seconds"]),
        NumberDef(
            "frame_start",
            visibility_condition=AndCondition([
                ValueCondition("use_custom_range", True),
                ValueCondition("mode", "frames"),
            ]),
        ),
    ]
    ```

"""
from __future__ import annotations

import copy
import operator
import typing
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar

if typing.TYPE_CHECKING:
    from typing import Union

    AttrDefConditionInput = Union["AttrDefCondition", dict[str, Any]]


def _contains(container: Any, value: Any) -> bool:
    try:
        return value in container
    except TypeError:
        return False


def _compare(func: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    def _inner(value: Any, condition_value: Any) -> bool:
        try:
            return func(value, condition_value)
        except TypeError:
            return False
    return _inner


# Comparison operators by name. First argument is current value of the
#   attribute, second is value defined on condition.
_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "in": lambda value, cond: _contains(cond, value),
    "not_in": lambda value, cond: not _contains(cond, value),
    "contains": _contains,
    "not_contains": lambda value, cond: not _contains(value, cond),
    "gt": _compare(operator.gt),
    "gte": _compare(operator.ge),
    "lt": _compare(operator.lt),
    "lte": _compare(operator.le),
}

_condition_classes_by_type: dict[str, type[AttrDefCondition]] = {}


class AttrDefCondition(ABC):
    """Base of conditions evaluated against attribute values.

    Each condition type must define unique 'type' used for serialization.

    """
    type: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cond_type = getattr(cls, "type", None)
        if isinstance(cond_type, str):
            _condition_classes_by_type[cond_type] = cls

    @abstractmethod
    def evaluate(self, values: Mapping[str, Any]) -> bool:
        """Evaluate the condition.

        Args:
            values (Mapping[str, Any]): Attribute values by key. Missing
                key means the attribute is not available, e.g. is hidden.

        Returns:
            bool: Condition is met.

        """

    @abstractmethod
    def get_keys(self) -> set[str]:
        """Keys of attributes used by the condition.

        Returns:
            set[str]: Attribute keys.

        """

    @abstractmethod
    def to_data(self) -> dict[str, Any]:
        """Serialize the condition to json serializable data.

        Returns:
            dict[str, Any]: Serialized condition, can be passed to
                'condition_from_data'.

        """

    @classmethod
    @abstractmethod
    def from_data(cls, data: dict[str, Any]) -> AttrDefCondition:
        """Create the condition from serialized data.

        Args:
            data (dict[str, Any]): Data created with 'to_data'.

        Returns:
            AttrDefCondition: Condition object.

        """


@dataclass
class ValueCondition(AttrDefCondition):
    """Compare value of an attribute.

    Condition is not met if the attribute is not available, e.g. is hidden.

    Supported operators:
        - 'eq', 'neq': Value is (not) equal to condition value.
        - 'in', 'not_in': Value is (not) one of condition values.
        - 'contains', 'not_contains': Value, e.g. list of multiselection
            enum or text, does (not) contain condition value.
        - 'gt', 'gte', 'lt', 'lte': Value is greater than, greater or
            equal, lower than, lower or equal to condition value.

    Args:
        key (str): Key of compared attribute.
        value (Any): Value to compare with.
        operator (str): Comparison operator. Default 'eq'.

    """
    type: ClassVar[str] = "value"

    key: str
    value: Any
    operator: str = "eq"

    def __post_init__(self):
        if self.operator not in _OPERATORS:
            raise ValueError(
                f"Unknown operator '{self.operator}'."
                f" Available operators: {', '.join(_OPERATORS)}"
            )

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        if self.key not in values:
            return False
        return bool(_OPERATORS[self.operator](values[self.key], self.value))

    def get_keys(self) -> set[str]:
        return {self.key}

    def to_data(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "key": self.key,
            "value": copy.deepcopy(self.value),
            "operator": self.operator,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> ValueCondition:
        return cls(
            key=data["key"],
            value=data["value"],
            operator=data.get("operator", "eq"),
        )


@dataclass
class _GroupCondition(AttrDefCondition):
    conditions: list[AttrDefCondition] = field(default_factory=list)

    def __post_init__(self):
        self.conditions = [
            prepare_condition(condition)
            for condition in self.conditions
        ]

    def get_keys(self) -> set[str]:
        return {
            key
            for condition in self.conditions
            for key in condition.get_keys()
        }

    def to_data(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "conditions": [
                condition.to_data()
                for condition in self.conditions
            ],
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> _GroupCondition:
        return cls(conditions=data["conditions"])


@dataclass
class AndCondition(_GroupCondition):
    """All conditions must be met. Met if there are no conditions.

    Args:
        conditions (list[AttrDefCondition]): Conditions to combine.

    """
    type: ClassVar[str] = "and"

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return all(
            condition.evaluate(values)
            for condition in self.conditions
        )


@dataclass
class OrCondition(_GroupCondition):
    """At least one condition must be met. Not met if there are no
    conditions.

    Args:
        conditions (list[AttrDefCondition]): Conditions to combine.

    """
    type: ClassVar[str] = "or"

    def evaluate(self, values: Mapping[str, Any]) -> bool:
        return any(
            condition.evaluate(values)
            for condition in self.conditions
        )


def condition_from_data(data: dict[str, Any]) -> AttrDefCondition:
    """Create condition from serialized data.

    Args:
        data (dict[str, Any]): Data created with 'AttrDefCondition.to_data'.

    Returns:
        AttrDefCondition: Condition object.

    """
    cond_type = data.get("type")
    cls = _condition_classes_by_type.get(cond_type)
    if cls is None:
        raise ValueError(f"Unknown condition type '{cond_type}'.")
    return cls.from_data(data)


def prepare_condition(
    condition: AttrDefConditionInput | None,
) -> AttrDefCondition | None:
    """Convert condition input to condition object.

    Args:
        condition (AttrDefConditionInput | None): Condition object or its
            serialized data.

    Returns:
        AttrDefCondition | None: Condition object.

    """
    if condition is None or isinstance(condition, AttrDefCondition):
        return condition
    if isinstance(condition, dict):
        return condition_from_data(condition)
    raise TypeError(
        "Condition must be 'AttrDefCondition' or 'dict',"
        f" got '{type(condition)}'."
    )
