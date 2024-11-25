import os
import re
import collections
import uuid
import json
import copy
import warnings
from abc import ABCMeta, abstractmethod
import typing
from typing import (
    Any,
    Optional,
    List,
    Set,
    Dict,
    Iterable,
    TypeVar,
)

import clique

if typing.TYPE_CHECKING:
    from typing import Self, Tuple, Union, TypedDict, Pattern


    class EnumItemDict(TypedDict):
        label: str
        value: Any


    EnumItemsInputType = Union[
        Dict[Any, str],
        List[Tuple[Any, str]],
        List[Any],
        List[EnumItemDict]
    ]


    class FileDefItemDict(TypedDict):
        directory: str
        filenames: List[str]
        frames: Optional[List[int]]
        template: Optional[str]
        is_sequence: Optional[bool]


# Global variable which store attribute definitions by type
#   - default types are registered on import
_attr_defs_by_type = {}

# Type hint helpers
IntFloatType = "Union[int, float]"


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
        label (Optional[str]): Attribute label.
        tooltip (Optional[str]): Attribute tooltip.
        is_label_horizontal (Optional[bool]): UI specific argument. Specify
            if label is next to value input or ahead.
        visible (Optional[bool]): Item is shown to user (for UI purposes).
        enabled (Optional[bool]): Item is enabled (for UI purposes).
        hidden (Optional[bool]): DEPRECATED: Use 'visible' instead.
        disabled (Optional[bool]): DEPRECATED: Use 'enabled' instead.

    """
    type_attributes = []

    is_value_def = True

    def __init__(
        self,
        key: str,
        default: Any,
        label: Optional[str] = None,
        tooltip: Optional[str] = None,
        is_label_horizontal: Optional[bool] = None,
        visible: Optional[bool] = None,
        enabled: Optional[bool] = None,
        hidden: Optional[bool] = None,
        disabled: Optional[bool] = None,
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
        self.label: Optional[str] = label
        self.tooltip: Optional[str] = tooltip
        self.default: Any = default
        self.is_label_horizontal: bool = is_label_horizontal
        self.visible: bool = visible
        self.enabled: bool = enabled
        self._id: str = uuid.uuid4().hex

        self.__init__class__ = AbstractAttrDef

    @property
    def id(self) -> str:
        return self._id

    def clone(self) -> "Self":
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
        ignore_default: Optional[bool] = False,
        ignore_enabled: Optional[bool] = False,
        ignore_visible: Optional[bool] = False,
        ignore_def_type_compare: Optional[bool] = False,
    ) -> bool:
        if not isinstance(other, self.__class__) or self.key != other.key:
            return False
        if not ignore_def_type_compare and not self._def_type_compare(other):
            return False
        return (
            (ignore_default or self.default == other.default)
            and (ignore_visible or self.visible == other.visible)
            and (ignore_enabled or self.enabled == other.enabled)
        )

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

    def serialize(self) -> Dict[str, Any]:
        """Serialize object to data so it's possible to recreate it.

        Returns:
            Dict[str, Any]: Serialized object that can be passed to
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
            "enabled": self.enabled
        }
        for attr in self.type_attributes:
            data[attr] = getattr(self, attr)
        return data

    @classmethod
    def deserialize(cls, data: Dict[str, Any]) -> "Self":
        """Recreate object from data.

        Data can be received using 'serialize' method.
        """
        if "type" in data:
            data = dict(data)
            data.pop("type")

        return cls(**data)

    def _def_type_compare(self, other: "Self") -> bool:
        return True


AttrDefType = TypeVar("AttrDefType", bound=AbstractAttrDef)

# -----------------------------------------
# UI attribute definitions won't hold value
# -----------------------------------------

class UIDef(AbstractAttrDef):
    is_value_def = False

    def __init__(
        self,
        key: Optional[str] = None,
        default: Optional[Any] = None,
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

    def _def_type_compare(self, other: "UILabelDef") -> bool:
        return self.label == other.label


# ---------------------------------------
# Attribute definitions should hold value
# ---------------------------------------

class UnknownDef(AbstractAttrDef):
    """Definition is not known because definition is not available.

    This attribute can be used to keep existing data unchanged but does not
    have known definition of type.

    """
    type = "unknown"

    def __init__(self, key: str, default: Optional[Any] = None, **kwargs):
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

    def __init__(self, key: str, default: Optional[Any] = None, **kwargs):
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
        minimum: Optional[IntFloatType] = None,
        maximum: Optional[IntFloatType] = None,
        decimals: Optional[int] = None,
        default: Optional[IntFloatType] = None,
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

        self.minimum: IntFloatType = minimum
        self.maximum: IntFloatType = maximum
        self.decimals: int = 0 if decimals is None else decimals

    def is_value_valid(self, value: Any) -> bool:
        if self.decimals == 0:
            if not isinstance(value, int):
                return False
        elif not isinstance(value, float):
            return False
        if self.minimum > value > self.maximum:
            return False
        return True

    def convert_value(self, value: Any) -> IntFloatType:
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

    def _def_type_compare(self, other: "NumberDef") -> bool:
        return (
            self.decimals == other.decimals
            and self.maximum == other.maximum
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
        multiline: Optional[bool] = None,
        regex: Optional[str] = None,
        placeholder: Optional[str] = None,
        default: Optional[str] = None,
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
        self.placeholder: Optional[str] = placeholder
        self.regex: Optional["Pattern"] = regex

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

    def serialize(self) -> Dict[str, Any]:
        data = super().serialize()
        regex = None
        if self.regex is not None:
            regex = self.regex.pattern
        data["regex"] = regex
        data["multiline"] = self.multiline
        data["placeholder"] = self.placeholder
        return data

    def _def_type_compare(self, other: "TextDef") -> bool:
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
        default (Optional[Any]): Default value. Must be one key(value) from
            passed items or list of values for multiselection.
        multiselection (Optional[bool]): If True, multiselection is allowed.
            Output is list of selected items.

    """
    type = "enum"

    def __init__(
        self,
        key: str,
        items: "EnumItemsInputType",
        default: "Union[str, List[Any]]" = None,
        multiselection: Optional[bool] = False,
        **kwargs
    ):
        if not items:
            raise ValueError((
                "Empty 'items' value. {} must have"
                " defined values on initialization."
            ).format(self.__class__.__name__))

        items = self.prepare_enum_items(items)
        item_values = [item["value"] for item in items]
        item_values_set = set(item_values)
        if multiselection is None:
            multiselection = False

        if multiselection:
            if default is None:
                default = []
            default = list(item_values_set.intersection(default))

        elif default not in item_values:
            default = next(iter(item_values), None)

        super().__init__(key, default=default, **kwargs)

        self.items: List["EnumItemDict"] = items
        self._item_values: Set[Any] = item_values_set
        self.multiselection: bool = multiselection

    def convert_value(self, value):
        if not self.multiselection:
            if value in self._item_values:
                return value
            return self.default

        if value is None:
            return copy.deepcopy(self.default)
        return list(self._item_values.intersection(value))

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
        data["items"] = copy.deepcopy(self.items)
        data["multiselection"] = self.multiselection
        return data

    @staticmethod
    def prepare_enum_items(
        items: "EnumItemsInputType"
    ) -> List["EnumItemDict"]:
        """Convert items to unified structure.

        Output is a list where each item is dictionary with 'value'
        and 'label'.

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
            List[EnumItemDict]: Unified structure of items.

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

                    if "label" not in item:
                        item["label"] = str(item["value"])
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

    def _def_type_compare(self, other: "EnumDef") -> bool:
        return (
            self.items == other.items
            and self.multiselection == other.multiselection
        )


class BoolDef(AbstractAttrDef):
    """Boolean representation.

    Args:
        default(bool): Default value. Set to `False` if not defined.

    """
    type = "bool"

    def __init__(self, key: str, default: Optional[bool] = None, **kwargs):
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
        filenames: List[str],
        frames: Optional[List[int]] = None,
        template: Optional[str] = None,
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
    def label(self) -> Optional[str]:
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

    def split_sequence(self) -> List["Self"]:
        if not self.is_sequence:
            raise ValueError("Cannot split single file item")

        paths = [
            os.path.join(self.directory, filename)
            for filename in self.filenames
        ]
        return self.from_paths(paths, False)

    @property
    def ext(self) -> Optional[str]:
        if self.is_empty:
            return None
        _, ext = os.path.splitext(self.filenames[0])
        if ext:
            return ext
        return None

    @property
    def lower_ext(self) -> Optional[str]:
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
        filenames: List[str],
        frames: Optional[List[int]] = None,
        template: Optional[str] = None,
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
    def create_empty_item(cls) -> "Self":
        return cls("", "")

    @classmethod
    def from_value(
        cls,
        value: "Union[List[FileDefItemDict], FileDefItemDict]",
        allow_sequences: bool,
    ) -> List["Self"]:
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
    def from_dict(cls, data: "FileDefItemDict") -> "Self":
        return cls(
            data["directory"],
            data["filenames"],
            data.get("frames"),
            data.get("template")
        )

    @classmethod
    def from_paths(
        cls,
        paths: List[str],
        allow_sequences: bool,
    ) -> List["Self"]:
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

    def to_dict(self) -> "FileDefItemDict":
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
        extensions(List[str]): Allow files with extensions. Empty list will
            allow all extensions and None will disable files completely.
        extensions_label(str): Custom label shown instead of extensions in UI.
        default(str, List[str]): Default value.
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
        single_item: Optional[bool] = True,
        folders: Optional[bool] = None,
        extensions: Optional[Iterable[str]] = None,
        allow_sequences: Optional[bool] = True,
        extensions_label: Optional[str] = None,
        default: Optional["Union[FileDefItemDict, List[str]]"] = None,
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
                    )[0]

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
        self.extensions: Set[str] = set(extensions)
        self.allow_sequences: bool = allow_sequences
        self.extensions_label: Optional[str] = extensions_label
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
    ) -> "Union[FileDefItemDict, List[FileDefItemDict]]":
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
    attribute_definitions: List[AttrDefType]
) -> Set[str]:
    """Collect keys from list of attribute definitions.

    Args:
        attribute_definitions (List[AttrDefType]): Objects of attribute
            definitions.

    Returns:
        Set[str]: Keys that will be created using passed attribute definitions.

    """
    keys = set()
    if not attribute_definitions:
        return keys

    for attribute_def in attribute_definitions:
        if not isinstance(attribute_def, UIDef):
            keys.add(attribute_def.key)
    return keys


def get_default_values(
    attribute_definitions: List[AttrDefType]
) -> Dict[str, Any]:
    """Receive default values for attribute definitions.

    Args:
        attribute_definitions (List[AttrDefType]): Attribute definitions
            for which default values should be collected.

    Returns:
        Dict[str, Any]: Default values for passed attribute definitions.

    """
    output = {}
    if not attribute_definitions:
        return output

    for attr_def in attribute_definitions:
        # Skip UI definitions
        if not isinstance(attr_def, UIDef):
            output[attr_def.key] = attr_def.default
    return output


def serialize_attr_def(attr_def: AttrDefType) -> Dict[str, Any]:
    """Serialize attribute definition to data.

    Args:
        attr_def (AttrDefType): Attribute definition to serialize.

    Returns:
        Dict[str, Any]: Serialized data.

    """
    return attr_def.serialize()


def serialize_attr_defs(
    attr_defs: List[AttrDefType]
) -> List[Dict[str, Any]]:
    """Serialize attribute definitions to data.

    Args:
        attr_defs (List[AttrDefType]): Attribute definitions to serialize.

    Returns:
        List[Dict[str, Any]]: Serialized data.

    """
    return [
        serialize_attr_def(attr_def)
        for attr_def in attr_defs
    ]


def deserialize_attr_def(attr_def_data: Dict[str, Any]) -> AttrDefType:
    """Deserialize attribute definition from data.

    Args:
        attr_def_data (Dict[str, Any]): Attribute definition data to
            deserialize.

    """
    attr_type = attr_def_data.pop("type")
    cls = _attr_defs_by_type[attr_type]
    return cls.deserialize(attr_def_data)


def deserialize_attr_defs(
    attr_defs_data: List[Dict[str, Any]]
) -> List[AttrDefType]:
    """Deserialize attribute definitions.

    Args:
        List[Dict[str, Any]]: List of attribute definitions.

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
