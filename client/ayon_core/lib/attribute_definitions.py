from __future__ import annotations

import os
import re
import collections
import uuid
import json
import copy
import warnings
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
import typing
from typing import (
    Any,
    TypeVar,
    Callable,
)
from collections.abc import Iterable

import clique

from .icon_definitions import (
    IconBase,
    MaterialSymbolsIcon,
    get_icon_def_from_data,
)

if typing.TYPE_CHECKING:
    from typing import Self, TypedDict, NotRequired
    from re import Pattern

    class EnumItemDict(TypedDict):
        label: str
        value: Any
        icon: NotRequired[IconBase | dict[str, str] | None]
        tooltip: NotRequired[str | None]

    EnumItemsInputType = (
        dict[Any, str]
        | list[tuple[Any, str]]
        | list[Any]
        | list[EnumItemDict]
    )

    class FileDefItemDict(TypedDict):
        directory: str
        filenames: list[str]
        frames: list[int] | None
        template: str | None
        is_sequence: bool | None

    class VisibilityRuleDict(TypedDict):
        values: list[Any]
        keys: list[str]


# Global variable which store attribute definitions by type
#   - default types are registered on import
_attr_defs_by_type = {}


class AbstractAttrDefMeta(ABCMeta):
    """Metaclass to validate the existence of 'key' attribute.

    Each object of `AbstractAttrDef` must have defined 'key' attribute.

    """
    def __call__(cls, *args, **kwargs):
        obj = super(AbstractAttrDefMeta, cls).__call__(*args, **kwargs)
        init_class = getattr(obj, "__init__class__", None)
        if init_class is not AbstractAttrDef:
            raise TypeError("{} super was not called in __init__.".format(
                type(obj)
            ))
        return obj


def _convert_reversed_attr(
    main_value: Any,
    depr_value: Any,
    main_label: str,
    depr_label: str,
    default: Any,
) -> Any:
    if main_value is not None and depr_value is not None:
        if main_value == depr_value:
            print(
                f"Got invalid '{main_label}' and '{depr_label}' arguments."
                f" Using '{main_label}' value."
            )
    elif depr_value is not None:
        warnings.warn(
            (
                "DEPRECATION WARNING: Using deprecated argument"
                f" '{depr_label}' please use '{main_label}' instead."
            ),
            DeprecationWarning,
            stacklevel=4,
        )
        main_value = not depr_value
    elif main_value is None:
        main_value = default
    return main_value


@dataclass
class VisibilityRule:
    """Rule controlling visibility of other attribute definitions.

    Attribute definitions with key in 'keys' are visible only if value of
    the attribute definition holding the rule matches one of 'values'.

    Args:
        values (list[Any]): Values for which are 'keys' visible.
        keys (list[str]): Keys of controlled attribute definitions.

    """
    values: list[Any]
    keys: list[str]

    def __post_init__(self):
        if isinstance(self.keys, str):
            self.keys = [self.keys]
        self.values = list(self.values)
        self.keys = list(self.keys)

    def to_data(self) -> VisibilityRuleDict:
        return {
            "values": copy.deepcopy(self.values),
            "keys": list(self.keys),
        }

    @classmethod
    def from_data(cls, data: VisibilityRuleDict) -> VisibilityRule:
        return cls(values=data["values"], keys=data["keys"])


def _prepare_visibility_rules(
    visibility_rules: Iterable[VisibilityRule | VisibilityRuleDict] | None,
) -> list[VisibilityRule]:
    output = []
    for rule in visibility_rules or []:
        if isinstance(rule, dict):
            rule = VisibilityRule.from_data(rule)
        elif not isinstance(rule, VisibilityRule):
            raise TypeError(
                "Visibility rule must be 'VisibilityRule' or 'dict',"
                f" got '{type(rule)}'."
            )
        output.append(rule)
    return output


class AbstractAttrDef(metaclass=AbstractAttrDefMeta):
    """Abstraction of attribute definition.

    Each attribute definition must have implemented validation and
    conversion method.

    Attribute definition should have ability to return "default" value. That
    can be based on passed data into `__init__` so is not abstracted to
    attribute.

    QUESTION:
    How to force to set `key` attribute?

    Args:
        key (str): Under which key will be attribute value stored.
        default (Any): Default value of an attribute.
        label (str | None): Attribute label.
        tooltip (str | None): Attribute tooltip.
        is_label_horizontal (bool | None): UI specific argument. Specify
            if label is next to value input or ahead.
        visible (bool | None): Item is shown to user (for UI purposes).
        enabled (bool | None): Item is enabled (for UI purposes).
        visibility_rules (list[VisibilityRule] | None): Rules controlling
            visibility of other attribute definitions based on value of
            this attribute definition (for UI purposes). Rules can be passed
            also as dictionaries with 'values' and 'keys'. Attribute
            definitions not mentioned in any rule are not affected.
        hidden (bool | None): DEPRECATED: Use 'visible' instead.
        disabled (bool | None): DEPRECATED: Use 'enabled' instead.

    Example:
        ```python
        attr_defs = [
            BoolDef(
                "use_custom_range",
                default=False,
                visibility_rules=[
                    VisibilityRule(
                        values=[True],
                        keys=["frame_start", "frame_end"],
                    ),
                ],
            ),
            NumberDef("frame_start"),
            NumberDef("frame_end"),
        ]
        ```

    """
    type_attributes = []

    is_value_def = True

    def __init__(
        self,
        key: str,
        default: Any,
        label: str | None = None,
        tooltip: str | None = None,
        is_label_horizontal: bool | None = None,
        visible: bool | None = None,
        enabled: bool | None = None,
        visibility_rules: (
            Iterable[VisibilityRule | VisibilityRuleDict] | None
        ) = None,
        hidden: bool | None = None,
        disabled: bool | None = None,
    ):
        if is_label_horizontal is None:
            is_label_horizontal = True

        enabled = _convert_reversed_attr(
            enabled, disabled, "enabled", "disabled", True
        )
        visible = _convert_reversed_attr(
            visible, hidden, "visible", "hidden", True
        )

        self.key: str = key
        self.label: str | None = label
        self.tooltip: str | None = tooltip
        self.default: Any = default
        self.is_label_horizontal: bool = is_label_horizontal
        self.visible: bool = visible
        self.enabled: bool = enabled
        self.visibility_rules: list[VisibilityRule] = (
            _prepare_visibility_rules(visibility_rules)
        )
        self._id: str = uuid.uuid4().hex

        self.__init__class__ = AbstractAttrDef

    @property
    def id(self) -> str:
        return self._id

    def clone(self) -> Self:
        data = self.serialize()
        data.pop("type")
        return self.deserialize(data)

    @property
    def hidden(self) -> bool:
        return not self.visible

    @hidden.setter
    def hidden(self, value: bool):
        self.visible = not value

    @property
    def disabled(self) -> bool:
        return not self.enabled

    @disabled.setter
    def disabled(self, value: bool):
        self.enabled = not value

    def __eq__(self, other: Any) -> bool:
        return self.compare_to_def(other)

    def __ne__(self, other: Any) -> bool:
        return not self.compare_to_def(other)

    def compare_to_def(
        self,
        other: Any,
        ignore_default: bool | None = False,
        ignore_enabled: bool | None = False,
        ignore_visible: bool | None = False,
        ignore_def_type_compare: bool | None = False,
    ) -> bool:
        if not isinstance(other, self.__class__) or self.key != other.key:
            return False
        if not ignore_def_type_compare and not self._def_type_compare(other):
            return False
        return (
            (ignore_default or self.default == other.default)
            and (ignore_visible or (
                self.visible == other.visible
                and self.visibility_rules == other.visibility_rules
            ))
            and (ignore_enabled or self.enabled == other.enabled)
        )

    def get_visibility_controlled_keys(self) -> set[str]:
        """Keys of attribute definitions controlled by visibility rules.

        Returns:
            set[str]: Keys of controlled attribute definitions.

        """
        return {
            key
            for rule in self.visibility_rules
            for key in rule.keys
        }

    def get_visible_keys_for_value(self, value: Any) -> set[str]:
        """Keys of controlled attribute definitions visible for a value.

        Args:
            value (Any): Value of this attribute definition.

        Returns:
            set[str]: Keys of controlled attribute definitions that should
                be visible for the value.

        """
        return {
            key
            for rule in self.visibility_rules
            if self._is_visibility_value_matching(value, rule.values)
            for key in rule.keys
        }

    def _is_visibility_value_matching(
        self, value: Any, rule_values: list[Any]
    ) -> bool:
        return value in rule_values

    @abstractmethod
    def is_value_valid(self, value: Any) -> bool:
        """Check if value is valid.

        This should return False if value is not valid based
            on definition type.

        Args:
            value (Any): Value to validate based on definition type.

        Returns:
            bool: True if value is valid.

        """
        pass

    @property
    @abstractmethod
    def type(self) -> str:
        """Attribute definition type also used as identifier of class.

        Returns:
            str: Type of attribute definition.

        """
        pass

    @abstractmethod
    def convert_value(self, value: Any) -> Any:
        """Convert value to a valid one.

        Convert passed value to a valid type. Use default if value can't be
        converted.

        """
        pass

    def serialize(self) -> dict[str, Any]:
        """Serialize object to data so it's possible to recreate it.

        Returns:
            dict[str, Any]: Serialized object that can be passed to
                'deserialize' method.

        """
        data = {
            "type": self.type,
            "key": self.key,
            "label": self.label,
            "tooltip": self.tooltip,
            "default": self.default,
            "is_label_horizontal": self.is_label_horizontal,
            "visible": self.visible,
            "enabled": self.enabled,
            "visibility_rules": [
                rule.to_data()
                for rule in self.visibility_rules
            ],
        }
        for attr in self.type_attributes:
            data[attr] = getattr(self, attr)
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> Self:
        """Recreate object from data.

        Data can be received using 'serialize' method.
        """
        if "type" in data:
            data = dict(data)
            data.pop("type")

        return cls(**data)

    def _def_type_compare(self, other: Self) -> bool:
        return True


AttrDefType = TypeVar("AttrDefType", bound=AbstractAttrDef)

# -----------------------------------------
# UI attribute definitions won't hold value
# -----------------------------------------


class UIDef(AbstractAttrDef):
    is_value_def = False

    def __init__(
        self,
        key: str | None = None,
        default: Any | None = None,
        *args,
        **kwargs
    ):
        super().__init__(key, default, *args, **kwargs)

    def is_value_valid(self, value: Any) -> bool:
        return True

    def convert_value(self, value: Any) -> Any:
        return value


class UISeparatorDef(UIDef):
    type = "separator"


class UILabelDef(UIDef):
    type = "label"

    def __init__(self, label, key=None, *args, **kwargs):
        super().__init__(label=label, key=key, *args, **kwargs)

    def _def_type_compare(self, other: UILabelDef) -> bool:
        return self.label == other.label


class ButtonDef(UIDef):
    """Button definition.

    UI element to allow to trigger a callback.
    """
    type = "button"

    def __init__(
        self,
        key: str,
        callback: Callable | None,
        text: str | None = None,
        icon: IconBase | None = None,
        **kwargs
    ):
        self._callback = callback
        if not text and not icon:
            icon = MaterialSymbolsIcon(name="left_click")
        self.icon = icon
        self.text = text
        super().__init__(key=key, **kwargs)

    def get_callback(self) -> Callable | None:
        return self._callback

    def set_callback(self, callback: Callable) -> None:
        self._callback = callback

    callback = property(get_callback, set_callback)

    def trigger(self) -> None:
        self._callback()

    def serialize(self) -> dict[str, Any]:
        """Serialize object to data so it's possible to recreate it.

        Serialization of button definition does not include callback function.
            Logic after deserialization has to be handled manually.

        """
        data = super().serialize()
        icon_data = None
        if self.icon is not None:
            icon_data = self.icon.to_data()
        data["callback"] = None
        data["icon"] = icon_data
        data["text"] = self.text
        return data

    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> Self:
        """Recreate object from data.

        Data can be received using 'serialize' method.
        """
        icon = data["icon"]
        if isinstance(icon, dict):
            data["icon"] = get_icon_def_from_data(icon)

        return cls(**data)

    def clone(self) -> Self:
        attr_def = super().clone()
        attr_def.set_callback(self._callback)
        return attr_def


# ---------------------------------------
# Attribute definitions should hold value
# ---------------------------------------

class UnknownDef(AbstractAttrDef):
    """Definition is not known because definition is not available.

    This attribute can be used to keep existing data unchanged but does not
    have known definition of type.

    """
    type = "unknown"

    def __init__(self, key: str, default: Any | None = None, **kwargs):
        kwargs["default"] = default
        super().__init__(key, **kwargs)

    def is_value_valid(self, value: Any) -> bool:
        return True

    def convert_value(self, value: Any) -> Any:
        return value


class HiddenDef(AbstractAttrDef):
    """Hidden value of Any type.

    This attribute can be used for UI purposes to pass values related
    to other attributes (e.g. in multi-page UIs).

    Keep in mind the value should be possible to parse by json parser.

    """
    type = "hidden"

    def __init__(self, key: str, default: Any | None = None, **kwargs):
        kwargs["default"] = default
        kwargs["visible"] = False
        super().__init__(key, **kwargs)

    def is_value_valid(self, value: Any) -> bool:
        return True

    def convert_value(self, value: Any) -> Any:
        return value


class NumberDef(AbstractAttrDef):
    """Number definition.

    Number can have defined minimum/maximum value and decimal points. Value
    is integer if decimals are 0.

    Args:
        minimum(int, float): Minimum possible value.
        maximum(int, float): Maximum possible value.
        decimals(int): Maximum decimal points of value.
        default(int, float): Default value for conversion.

    """
    type = "number"
    type_attributes = [
        "minimum",
        "maximum",
        "decimals"
    ]

    def __init__(
        self,
        key: str,
        minimum: int | float | None = None,
        maximum: int | float | None = None,
        decimals: int | None = None,
        default: int | float | None = None,
        **kwargs
    ):
        minimum = 0 if minimum is None else minimum
        maximum = 999999 if maximum is None else maximum
        # Swap min/max when are passed in opposite order
        if minimum > maximum:
            maximum, minimum = minimum, maximum

        if default is None:
            default = 0

        elif not isinstance(default, (int, float)):
            raise TypeError((
                "'default' argument must be 'int' or 'float', not '{}'"
            ).format(type(default)))

        # Fix default value by mim/max values
        if default < minimum:
            default = minimum

        elif default > maximum:
            default = maximum

        super().__init__(key, default=default, **kwargs)

        self.minimum: int | float = minimum
        self.maximum: int | float = maximum
        self.decimals: int = 0 if decimals is None else decimals

    def is_value_valid(self, value: Any) -> bool:
        if self.decimals == 0:
            if not isinstance(value, int):
                return False
        elif not isinstance(value, float):
            return False
        if not self.minimum <= value <= self.maximum:
            return False
        return True

    def convert_value(self, value: Any) -> int | float:
        if isinstance(value, str):
            try:
                value = float(value)
            except Exception:
                pass

        if not isinstance(value, (int, float)):
            return self.default

        if self.decimals == 0:
            return int(value)
        return round(float(value), self.decimals)

    def _def_type_compare(self, other: NumberDef) -> bool:
        return (
            self.decimals == other.decimals
            and self.minimum == other.minimum
            and self.maximum == other.maximum
        )


class TextDef(AbstractAttrDef):
    """Text definition.

    Text can have multiline option so end-line characters are allowed regex
    validation can be applied placeholder for UI purposes and default value.

    Regex validation is not part of attribute implementation.

    Args:
        multiline(bool): Text has single or multiline support.
        regex(str, re.Pattern): Regex validation.
        placeholder(str): UI placeholder for attribute.
        default(str, None): Default value. Empty string used when not defined.

    """
    type = "text"
    type_attributes = [
        "multiline",
        "placeholder",
    ]

    def __init__(
        self,
        key: str,
        multiline: bool | None = None,
        regex: str | None = None,
        placeholder: str | None = None,
        default: str | None = None,
        **kwargs
    ):
        if default is None:
            default = ""

        super().__init__(key, default=default, **kwargs)

        if multiline is None:
            multiline = False

        elif not isinstance(default, str):
            raise TypeError((
                f"'default' argument must be a str, not '{type(default)}'"
            ))

        if isinstance(regex, str):
            regex = re.compile(regex)

        self.multiline: bool = multiline
        self.placeholder: str | None = placeholder
        self.regex: Pattern | None = regex

    def is_value_valid(self, value: Any) -> bool:
        if not isinstance(value, str):
            return False
        if self.regex and not self.regex.match(value):
            return False
        return True

    def convert_value(self, value: Any) -> str:
        if isinstance(value, str):
            return value
        return self.default

    def serialize(self) -> dict[str, Any]:
        data = super().serialize()
        regex = None
        if self.regex is not None:
            regex = self.regex.pattern
        data["regex"] = regex
        data["multiline"] = self.multiline
        data["placeholder"] = self.placeholder
        return data

    def _def_type_compare(self, other: TextDef) -> bool:
        return (
            self.multiline == other.multiline
            and self.regex == other.regex
        )


class EnumDef(AbstractAttrDef):
    """Enumeration of items.

    Enumeration of single item from items. Or list of items if multiselection
    is enabled.

    Args:
        key (str): Key under which value is stored.
        items (EnumItemsInputType): Items definition that can be converted
            using 'prepare_enum_items'.
        default (Any | None): Default value. Must be one key(value) from
            passed items or list of values for multiselection.
        multiselection (bool | None): If True, multiselection is allowed.
            Output is list of selected items.
        placeholder (str | None): Placeholder for UI purposes, only for
            multiselection enumeration.

    Items defined as dictionaries can optionally define an 'icon'
    (`IconBase` or its serialized data) and a 'tooltip' to show in UI.

    """
    type = "enum"

    type_attributes = [
        "multiselection",
        "placeholder",
    ]

    def __init__(
        self,
        key: str,
        items: EnumItemsInputType,
        default: str | list[Any] = None,
        multiselection: bool | None = False,
        placeholder: str | None = None,
        **kwargs
    ):
        if multiselection is None:
            multiselection = False

        if not items and not multiselection:
            raise ValueError(
                f"Empty 'items' value. {self.__class__.__name__} must have"
                " defined values on initialization."
            )

        items = self.prepare_enum_items(items)
        item_values = [item["value"] for item in items]
        item_values_set = set(item_values)

        if multiselection:
            if default is None:
                default = []
            default = list(item_values_set.intersection(default))

        elif default not in item_values:
            default = next(iter(item_values), None)

        super().__init__(key, default=default, **kwargs)

        self.items: list[EnumItemDict] = items
        self._item_values: set[Any] = item_values_set
        self.multiselection: bool = multiselection
        self.placeholder: str | None = placeholder

    def convert_value(self, value):
        if not self.multiselection:
            if value in self._item_values:
                return value
            return self.default

        if value is None:
            return copy.deepcopy(self.default)
        return [
            v
            for v in value
            if v in self._item_values
        ]

    def is_value_valid(self, value: Any) -> bool:
        """Check if item is available in possible values."""
        if isinstance(value, list):
            if not self.multiselection:
                return False
            return all(value in self._item_values for value in value)

        if self.multiselection:
            return False
        return value in self._item_values

    def serialize(self):
        data = super().serialize()
        items = []
        for item in self.items:
            item = copy.deepcopy(item)
            icon = item.get("icon")
            if isinstance(icon, IconBase):
                item["icon"] = icon.to_data()
            items.append(item)
        data["items"] = items
        return data

    @staticmethod
    def prepare_enum_items(
        items: EnumItemsInputType
    ) -> list[EnumItemDict]:
        """Convert items to unified structure.

        Output is a list where each item is dictionary with 'value'
        and 'label'. Optional 'icon' is converted to `IconBase` if it was
        passed as serialized icon data.

        ```python
        # Example output
        [
            {"label": "Option 1", "value": 1},
            {"label": "Option 2", "value": 2},
            {"label": "Option 3", "value": 3}
        ]
        ```

        Args:
            items (EnumItemsInputType): The items to convert.

        Returns:
            list[EnumItemDict]: Unified structure of items.

        """
        output = []
        if isinstance(items, dict):
            for value, label in items.items():
                output.append({"label": label, "value": value})

        elif isinstance(items, (tuple, list, set)):
            for item in items:
                if isinstance(item, dict):
                    # Validate if 'value' is available
                    if "value" not in item:
                        raise KeyError("Item does not contain 'value' key.")

                    item = dict(item)
                    if "label" not in item:
                        item["label"] = str(item["value"])

                    icon = item.get("icon")
                    if isinstance(icon, dict):
                        item["icon"] = get_icon_def_from_data(icon)
                elif isinstance(item, (list, tuple)):
                    if len(item) == 2:
                        value, label = item
                    elif len(item) == 1:
                        value = item[0]
                        label = str(value)
                    else:
                        raise ValueError((
                            "Invalid items count {}."
                            " Expected 1 or 2. Value: {}"
                        ).format(len(item), str(item)))

                    item = {"label": label, "value": value}
                else:
                    item = {"label": str(item), "value": item}
                output.append(item)

        else:
            raise TypeError(
                "Unknown type for enum items '{}'".format(type(items))
            )

        return output

    def _def_type_compare(self, other: EnumDef) -> bool:
        return (
            self.items == other.items
            and self.multiselection == other.multiselection
        )

    def _is_visibility_value_matching(
        self, value: Any, rule_values: list[Any]
    ) -> bool:
        if self.multiselection and isinstance(value, (list, tuple, set)):
            return any(item in rule_values for item in value)
        return super()._is_visibility_value_matching(value, rule_values)


class BoolDef(AbstractAttrDef):
    """Boolean representation.

    Args:
        default(bool): Default value. Set to `False` if not defined.

    """
    type = "bool"

    def __init__(self, key: str, default: bool | None = None, **kwargs):
        if default is None:
            default = False
        super().__init__(key, default=default, **kwargs)

    def is_value_valid(self, value: Any) -> bool:
        return isinstance(value, bool)

    def convert_value(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return self.default


class FileDefItem:
    def __init__(
        self,
        directory: str,
        filenames: list[str],
        frames: list[int] | None = None,
        template: str | None = None,
    ):
        self.directory = directory

        self.filenames = []
        self.is_sequence = False
        self.template = None
        self.frames = []
        self.is_empty = True

        self.set_filenames(filenames, frames, template)

    def __str__(self):
        return json.dumps(self.to_dict())

    def __repr__(self):
        if self.is_empty:
            filename = "< empty >"
        elif self.is_sequence:
            filename = self.template
        else:
            filename = self.filenames[0]

        return "<{}: \"{}\">".format(
            self.__class__.__name__,
            os.path.join(self.directory, filename)
        )

    @property
    def label(self) -> str | None:
        if self.is_empty:
            return None

        if not self.is_sequence:
            return self.filenames[0]

        frame_start = self.frames[0]
        filename_template = os.path.basename(self.template)
        if len(self.frames) == 1:
            return "{} [{}]".format(filename_template, frame_start)

        frame_end = self.frames[-1]
        expected_len = (frame_end - frame_start) + 1
        if expected_len == len(self.frames):
            return "{} [{}-{}]".format(
                filename_template, frame_start, frame_end
            )

        ranges = []
        _frame_start = None
        _frame_end = None
        for frame in range(frame_start, frame_end + 1):
            if frame not in self.frames:
                add_to_ranges = _frame_start is not None
            elif _frame_start is None:
                _frame_start = _frame_end = frame
                add_to_ranges = frame == frame_end
            else:
                _frame_end = frame
                add_to_ranges = frame == frame_end

            if add_to_ranges:
                if _frame_start != _frame_end:
                    _range = "{}-{}".format(_frame_start, _frame_end)
                else:
                    _range = str(_frame_start)
                ranges.append(_range)
                _frame_start = _frame_end = None
        return "{} [{}]".format(
            filename_template, ",".join(ranges)
        )

    def split_sequence(self) -> list[Self]:
        if not self.is_sequence:
            raise ValueError("Cannot split single file item")

        paths = [
            os.path.join(self.directory, filename)
            for filename in self.filenames
        ]
        return self.from_paths(paths, False)

    @property
    def ext(self) -> str | None:
        if self.is_empty:
            return None
        _, ext = os.path.splitext(self.filenames[0])
        if ext:
            return ext
        return None

    @property
    def lower_ext(self) -> str | None:
        ext = self.ext
        if ext is not None:
            return ext.lower()
        return ext

    @property
    def is_dir(self) -> bool:
        if self.is_empty:
            return False

        # QUESTION a better way how to define folder (in init argument?)
        if self.ext:
            return False
        return True

    def set_directory(self, directory: str):
        self.directory = directory

    def set_filenames(
        self,
        filenames: list[str],
        frames: list[int] | None = None,
        template: str | None = None,
    ):
        if frames is None:
            frames = []
        is_sequence = False
        if frames:
            is_sequence = True

        if is_sequence and not template:
            raise ValueError("Missing template for sequence")

        self.is_empty = len(filenames) == 0
        self.filenames = filenames
        self.template = template
        self.frames = frames
        self.is_sequence = is_sequence

    @classmethod
    def create_empty_item(cls) -> Self:
        return cls("", "")

    @classmethod
    def from_value(
        cls,
        value: list[FileDefItemDict] | FileDefItemDict,
        allow_sequences: bool,
    ) -> list[Self]:
        """Convert passed value to FileDefItem objects.

        Returns:
            list: Created FileDefItem objects.

        """
        # Convert single item to iterable
        if not isinstance(value, (list, tuple, set)):
            value = [value]

        output = []
        str_filepaths = []
        for item in value:
            if isinstance(item, dict):
                item = cls.from_dict(item)

            if isinstance(item, FileDefItem):
                if not allow_sequences and item.is_sequence:
                    output.extend(item.split_sequence())
                else:
                    output.append(item)

            elif isinstance(item, str):
                str_filepaths.append(item)
            else:
                raise TypeError(
                    "Unknown type \"{}\". Can't convert to {}".format(
                        str(type(item)), cls.__name__
                    )
                )

        if str_filepaths:
            output.extend(cls.from_paths(str_filepaths, allow_sequences))

        return output

    @classmethod
    def from_dict(cls, data: FileDefItemDict) -> Self:
        return cls(
            data["directory"],
            data["filenames"],
            data.get("frames"),
            data.get("template")
        )

    @classmethod
    def from_paths(
        cls,
        paths: list[str],
        allow_sequences: bool,
    ) -> list[Self]:
        filenames_by_dir = collections.defaultdict(list)
        for path in paths:
            normalized = os.path.normpath(path)
            directory, filename = os.path.split(normalized)
            filenames_by_dir[directory].append(filename)

        output = []
        for directory, filenames in filenames_by_dir.items():
            if allow_sequences:
                cols, remainders = clique.assemble(filenames)
            else:
                cols = []
                remainders = filenames

            for remainder in remainders:
                output.append(cls(directory, [remainder]))

            for col in cols:
                frames = list(col.indexes)
                paths = [filename for filename in col]
                template = col.format("{head}{padding}{tail}")

                output.append(cls(
                    directory, paths, frames, template
                ))

        return output

    def to_dict(self) -> FileDefItemDict:
        output = {
            "is_sequence": self.is_sequence,
            "directory": self.directory,
            "filenames": list(self.filenames),
        }
        if self.is_sequence:
            output.update({
                "template": self.template,
                "frames": list(sorted(self.frames)),
            })

        return output


class FileDef(AbstractAttrDef):
    """File definition.
    It is possible to define filters of allowed file extensions and if supports
    folders.
    Args:
        single_item(bool): Allow only single path item.
        folders(bool): Allow folder paths.
        extensions(list[str]): Allow files with extensions. Empty list will
            allow all extensions and None will disable files completely.
        extensions_label(str): Custom label shown instead of extensions in UI.
        default(str, list[str]): Default value.
    """

    type = "path"
    type_attributes = [
        "single_item",
        "folders",
        "extensions",
        "allow_sequences",
        "extensions_label",
    ]

    def __init__(
        self,
        key: str,
        single_item: bool | None = True,
        folders: bool | None = None,
        extensions: Iterable[str] | None = None,
        allow_sequences: bool | None = True,
        extensions_label: str | None = None,
        default: FileDefItemDict | list[str] | None = None,
        **kwargs
    ):
        if folders is None and extensions is None:
            folders = True
            extensions = []

        if default is None:
            if single_item:
                default = FileDefItem.create_empty_item().to_dict()
            else:
                default = []
        else:
            if single_item:
                if isinstance(default, dict):
                    FileDefItem.from_dict(default)

                elif isinstance(default, str):
                    default = FileDefItem.from_paths(
                        [default.strip()], allow_sequences
                    )[0].to_dict()

                else:
                    raise TypeError((
                        "'default' argument must be 'str' or 'dict' not '{}'"
                    ).format(type(default)))

            else:
                if not isinstance(default, (tuple, list, set)):
                    raise TypeError((
                        "'default' argument must be 'list', 'tuple' or 'set'"
                        ", not '{}'"
                    ).format(type(default)))

        # Change horizontal label
        is_label_horizontal = kwargs.get("is_label_horizontal")
        if is_label_horizontal is None:
            kwargs["is_label_horizontal"] = False

        self.single_item: bool = single_item
        self.folders: bool = folders
        self.extensions: set[str] = set(extensions)
        self.allow_sequences: bool = allow_sequences
        self.extensions_label: str | None = extensions_label
        super().__init__(key, default=default, **kwargs)

    def __eq__(self, other: Any) -> bool:
        if not super().__eq__(other):
            return False

        return (
            self.single_item == other.single_item
            and self.folders == other.folders
            and self.extensions == other.extensions
            and self.allow_sequences == other.allow_sequences
        )

    def serialize(self) -> dict[str, Any]:
        data = super().serialize()
        # Make sure output is JSON serializable
        data["extensions"] = sorted(self.extensions)
        return data

    def is_value_valid(self, value: Any) -> bool:
        if self.single_item:
            if not isinstance(value, dict):
                return False
            try:
                FileDefItem.from_dict(value)
                return True
            except (ValueError, KeyError):
                return False

        if not isinstance(value, list):
            return False

        for item in value:
            if not isinstance(item, dict):
                return False

            try:
                FileDefItem.from_dict(item)
            except (ValueError, KeyError):
                return False
        return True

    def convert_value(
        self, value: Any
    ) -> FileDefItemDict | list[FileDefItemDict]:
        if isinstance(value, (str, dict)):
            value = [value]

        if isinstance(value, (tuple, list, set)):
            string_paths = []
            dict_items = []
            for item in value:
                if isinstance(item, str):
                    string_paths.append(item.strip())
                elif isinstance(item, dict):
                    try:
                        FileDefItem.from_dict(item)
                        dict_items.append(item)
                    except (ValueError, KeyError):
                        pass

            if string_paths:
                file_items = FileDefItem.from_paths(
                    string_paths, self.allow_sequences
                )
                dict_items.extend([
                    file_item.to_dict()
                    for file_item in file_items
                ])

            if not self.single_item:
                return dict_items

            if not dict_items:
                return self.default
            return dict_items[0]

        if self.single_item:
            return FileDefItem.create_empty_item().to_dict()
        return []


def register_attr_def_class(cls: AttrDefType):
    """Register attribute definition.

    Currently registered definitions are used to deserialize data to objects.

    Attrs:
        cls (AttrDefType): Non-abstract class to be registered with unique
            'type' attribute.

    Raises:
        KeyError: When type was already registered.

    """
    if cls.type in _attr_defs_by_type:
        raise KeyError("Type \"{}\" was already registered".format(cls.type))
    _attr_defs_by_type[cls.type] = cls


def get_attributes_keys(
    attribute_definitions: list[AttrDefType]
) -> set[str]:
    """Collect keys from list of attribute definitions.

    Args:
        attribute_definitions (list[AttrDefType]): Objects of attribute
            definitions.

    Returns:
        set[str]: Keys that will be created using passed attribute definitions.

    """
    keys = set()
    if not attribute_definitions:
        return keys

    for attribute_def in attribute_definitions:
        if not isinstance(attribute_def, UIDef):
            keys.add(attribute_def.key)
    return keys


def get_default_values(
    attribute_definitions: list[AttrDefType]
) -> dict[str, Any]:
    """Receive default values for attribute definitions.

    Args:
        attribute_definitions (list[AttrDefType]): Attribute definitions
            for which default values should be collected.

    Returns:
        dict[str, Any]: Default values for passed attribute definitions.

    """
    output = {}
    if not attribute_definitions:
        return output

    for attr_def in attribute_definitions:
        # Skip UI definitions
        if not isinstance(attr_def, UIDef):
            output[attr_def.key] = attr_def.default
    return output


def get_attr_defs_visibility(
    attr_defs: Iterable[AttrDefType],
    values: dict[str, Any],
) -> dict[str, bool]:
    """Resolve visibility of attribute definitions.

    Takes into account 'visible' of each attribute definition and
    'visibility_rules' of controlling attribute definitions. Attribute
    definition controlled by a hidden attribute definition is hidden too.

    Args:
        attr_defs (Iterable[AttrDefType]): Attribute definitions.
        values (dict[str, Any]): Current values by attribute definition key.
            Default value of attribute definition is used if key is missing.

    Returns:
        dict[str, bool]: Visibility by attribute definition id.

    """
    attr_defs = list(attr_defs)
    controllers_by_key = collections.defaultdict(list)
    for attr_def in attr_defs:
        if not attr_def.is_value_def:
            continue
        for key in attr_def.get_visibility_controlled_keys():
            controllers_by_key[key].append(attr_def)

    visibility_by_id = {}

    def _is_visible(attr_def: AttrDefType, processing: set[str]) -> bool:
        if attr_def.id in visibility_by_id:
            return visibility_by_id[attr_def.id]

        visible = attr_def.visible
        # Skip controllers already being resolved to avoid cycles
        processing = processing | {attr_def.id}
        for controller in controllers_by_key.get(attr_def.key, []):
            if not visible:
                break
            if controller.id in processing:
                continue
            if not _is_visible(controller, processing):
                visible = False
                break

            value = values.get(controller.key, controller.default)
            visible = (
                attr_def.key in controller.get_visible_keys_for_value(value)
            )

        visibility_by_id[attr_def.id] = visible
        return visible

    for attr_def in attr_defs:
        _is_visible(attr_def, set())
    return visibility_by_id


def serialize_attr_def(attr_def: AttrDefType) -> dict[str, Any]:
    """Serialize attribute definition to data.

    Args:
        attr_def (AttrDefType): Attribute definition to serialize.

    Returns:
        dict[str, Any]: Serialized data.

    """
    return attr_def.serialize()


def serialize_attr_defs(
    attr_defs: list[AttrDefType]
) -> list[dict[str, Any]]:
    """Serialize attribute definitions to data.

    Args:
        attr_defs (list[AttrDefType]): Attribute definitions to serialize.

    Returns:
        list[dict[str, Any]]: Serialized data.

    """
    return [
        serialize_attr_def(attr_def)
        for attr_def in attr_defs
    ]


def deserialize_attr_def(attr_def_data: dict[str, Any]) -> AttrDefType:
    """Deserialize attribute definition from data.

    Args:
        attr_def_data (dict[str, Any]): Attribute definition data to
            deserialize.

    """
    attr_type = attr_def_data.pop("type")
    cls = _attr_defs_by_type[attr_type]
    return cls.deserialize(attr_def_data)


def deserialize_attr_defs(
    attr_defs_data: list[dict[str, Any]]
) -> list[AttrDefType]:
    """Deserialize attribute definitions.

    Args:
        list[dict[str, Any]]: List of attribute definitions.

    """
    return [
        deserialize_attr_def(attr_def_data)
        for attr_def_data in attr_defs_data
    ]


# Register attribute definitions
for _attr_class in (
    UISeparatorDef,
    UILabelDef,
    UnknownDef,
    NumberDef,
    TextDef,
    EnumDef,
    BoolDef,
    FileDef
):
    register_attr_def_class(_attr_class)
