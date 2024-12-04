import os
import re
import copy
import numbers
import warnings
from string import Formatter
import typing
from typing import List, Dict, Any, Set

if typing.TYPE_CHECKING:
    from typing import Union

SUB_DICT_PATTERN = re.compile(r"([^\[\]]+)")
OPTIONAL_PATTERN = re.compile(r"(<.*?[^{0]*>)[^0-9]*?")


class TemplateUnsolved(Exception):
    """Exception for unsolved template when strict is set to True."""

    msg = "Template \"{0}\" is unsolved.{1}{2}"
    invalid_types_msg = " Keys with invalid data type: `{0}`."
    missing_keys_msg = " Missing keys: \"{0}\"."

    def __init__(self, template, missing_keys, invalid_types):
        invalid_type_items = []
        for _key, _type in invalid_types.items():
            invalid_type_items.append(f"\"{_key}\" {str(_type)}")

        invalid_types_msg = ""
        if invalid_type_items:
            invalid_types_msg = self.invalid_types_msg.format(
                ", ".join(invalid_type_items)
            )

        missing_keys_msg = ""
        if missing_keys:
            missing_keys_msg = self.missing_keys_msg.format(
                ", ".join(missing_keys)
            )
        super().__init__(
            self.msg.format(template, missing_keys_msg, invalid_types_msg)
        )


class StringTemplate:
    """String that can be formatted."""
    def __init__(self, template: str):
        if not isinstance(template, str):
            raise TypeError(
                f"<{self.__class__.__name__}> argument must be a string,"
                f" not {str(type(template))}."
            )

        self._template: str = template
        parts = []
        formatter = Formatter()

        for item in formatter.parse(template):
            literal_text, field_name, format_spec, conversion = item
            if literal_text:
                parts.append(literal_text)
            if field_name:
                parts.append(
                    FormattingPart(field_name, format_spec, conversion)
                )

        new_parts = []
        for part in parts:
            if not isinstance(part, str):
                new_parts.append(part)
                continue

            substr = ""
            for char in part:
                if char not in ("<", ">"):
                    substr += char
                else:
                    if substr:
                        new_parts.append(substr)
                    new_parts.append(char)
                    substr = ""
            if substr:
                new_parts.append(substr)

        self._parts: List["Union[str, OptionalPart, FormattingPart]"] = (
            self.find_optional_parts(new_parts)
        )

    def __str__(self) -> str:
        return self.template

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}> {self.template}"

    def __contains__(self, other: str) -> bool:
        return other in self.template

    def replace(self, *args, **kwargs):
        self._template = self.template.replace(*args, **kwargs)
        return self

    @property
    def template(self) -> str:
        return self._template

    def format(self, data: Dict[str, Any]) -> "TemplateResult":
        """ Figure out with whole formatting.

        Separate advanced keys (*Like '{project[name]}') from string which must
        be formatted separately in case of missing or incomplete keys in data.

        Args:
            data (dict): Containing keys to be filled into template.

        Returns:
            TemplateResult: Filled or partially filled template containing all
                data needed or missing for filling template.

        """
        result = TemplatePartResult()
        for part in self._parts:
            if isinstance(part, str):
                result.add_output(part)
            else:
                part.format(data, result)

        invalid_types = result.invalid_types
        invalid_types.update(result.invalid_optional_types)
        invalid_types = result.split_keys_to_subdicts(invalid_types)

        missing_keys = result.missing_keys
        missing_keys |= result.missing_optional_keys

        solved = result.solved
        used_values = result.get_clean_used_values()

        return TemplateResult(
            result.output,
            self.template,
            solved,
            used_values,
            missing_keys,
            invalid_types
        )

    def format_strict(self, data: Dict[str, Any]) -> "TemplateResult":
        result = self.format(data)
        result.validate()
        return result

    @classmethod
    def format_template(
        cls, template: str, data: Dict[str, Any]
    ) -> "TemplateResult":
        objected_template = cls(template)
        return objected_template.format(data)

    @classmethod
    def format_strict_template(
        cls, template: str, data: Dict[str, Any]
    ) -> "TemplateResult":
        objected_template = cls(template)
        return objected_template.format_strict(data)

    @staticmethod
    def find_optional_parts(
        parts: List["Union[str, FormattingPart]"]
    ) -> List["Union[str, OptionalPart, FormattingPart]"]:
        new_parts = []
        tmp_parts = {}
        counted_symb = -1
        for part in parts:
            if part == "<":
                counted_symb += 1
                tmp_parts[counted_symb] = []

            elif part == ">":
                if counted_symb > -1:
                    parts = tmp_parts.pop(counted_symb)
                    counted_symb -= 1
                    # If part contains only single string keep value
                    #   unchanged
                    if parts:
                        # Remove optional start char
                        parts.pop(0)

                    if not parts:
                        value = "<>"
                    elif (
                        len(parts) == 1
                        and isinstance(parts[0], str)
                    ):
                        value = "<{}>".format(parts[0])
                    else:
                        value = OptionalPart(parts)

                    if counted_symb < 0:
                        out_parts = new_parts
                    else:
                        out_parts = tmp_parts[counted_symb]
                    # Store value
                    out_parts.append(value)
                    continue

            if counted_symb < 0:
                new_parts.append(part)
            else:
                tmp_parts[counted_symb].append(part)

        if tmp_parts:
            for idx in sorted(tmp_parts.keys()):
                new_parts.extend(tmp_parts[idx])
        return new_parts


class TemplateResult(str):
    """Result of template format with most of the information in.

    Args:
        used_values (dict): Dictionary of template filling data with
            only used keys.
        solved (bool): For check if all required keys were filled.
        template (str): Original template.
        missing_keys (Iterable[str]): Missing keys that were not in the data.
            Include missing optional keys.
        invalid_types (dict): When key was found in data, but value had not
            allowed DataType. Allowed data types are `numbers`,
            `str`(`basestring`) and `dict`. Dictionary may cause invalid type
            when value of key in data is dictionary but template expect string
            of number.
    """

    used_values: Dict[str, Any] = None
    solved: bool = None
    template: str = None
    missing_keys: List[str] = None
    invalid_types: Dict[str, Any] = None

    def __new__(
        cls, filled_template, template, solved,
        used_values, missing_keys, invalid_types
    ):
        new_obj = super(TemplateResult, cls).__new__(cls, filled_template)
        new_obj.used_values = used_values
        new_obj.solved = solved
        new_obj.template = template
        new_obj.missing_keys = list(set(missing_keys))
        new_obj.invalid_types = invalid_types
        return new_obj

    def __copy__(self, *args, **kwargs):
        return self.copy()

    def __deepcopy__(self, *args, **kwargs):
        return self.copy()

    def validate(self):
        if not self.solved:
            raise TemplateUnsolved(
                self.template,
                self.missing_keys,
                self.invalid_types
            )

    def copy(self) -> "TemplateResult":
        cls = self.__class__
        return cls(
            str(self),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types
        )

    def normalized(self) -> "TemplateResult":
        """Convert to normalized path."""

        cls = self.__class__
        return cls(
            os.path.normpath(self.replace("\\", "/")),
            self.template,
            self.solved,
            self.used_values,
            self.missing_keys,
            self.invalid_types
        )


class TemplatePartResult:
    """Result to store result of template parts."""
    def __init__(self, optional: bool = False):
        # Missing keys or invalid value types of required keys
        self._missing_keys: Set[str] = set()
        self._invalid_types: Dict[str, Any] = {}
        # Missing keys or invalid value types of optional keys
        self._missing_optional_keys: Set[str] = set()
        self._invalid_optional_types: Dict[str, Any] = {}

        # Used values stored by key with origin type
        #   - key without any padding or key modifiers
        #   - value from filling data
        #   Example: {"version": 1}
        self._used_values: Dict[str, Any] = {}
        # Used values stored by key with all modifirs
        #   - value is already formatted string
        #   Example: {"version:0>3": "001"}
        self._really_used_values: Dict[str, Any] = {}
        # Concatenated string output after formatting
        self._output: str = ""
        # Is this result from optional part
        # TODO find out why we don't use 'optional' from args
        self._optional: bool = True

    def add_output(self, other):
        if isinstance(other, str):
            self._output += other

        elif isinstance(other, TemplatePartResult):
            self._output += other.output

            self._missing_keys |= other.missing_keys
            self._missing_optional_keys |= other.missing_optional_keys

            self._invalid_types.update(other.invalid_types)
            self._invalid_optional_types.update(other.invalid_optional_types)

            if other.optional and not other.solved:
                return
            self._used_values.update(other.used_values)
            self._really_used_values.update(other.really_used_values)

        else:
            raise TypeError("Cannot add data from \"{}\" to \"{}\"".format(
                str(type(other)), self.__class__.__name__)
            )

    @property
    def solved(self) -> bool:
        if self.optional:
            if (
                len(self.missing_optional_keys) > 0
                or len(self.invalid_optional_types) > 0
            ):
                return False
        return (
            len(self.missing_keys) == 0
            and len(self.invalid_types) == 0
        )

    @property
    def optional(self) -> bool:
        return self._optional

    @property
    def output(self) -> str:
        return self._output

    @property
    def missing_keys(self) -> Set[str]:
        return self._missing_keys

    @property
    def missing_optional_keys(self) -> Set[str]:
        return self._missing_optional_keys

    @property
    def invalid_types(self) -> Dict[str, Any]:
        return self._invalid_types

    @property
    def invalid_optional_types(self) -> Dict[str, Any]:
        return self._invalid_optional_types

    @property
    def really_used_values(self) -> Dict[str, Any]:
        return self._really_used_values

    @property
    def realy_used_values(self) -> Dict[str, Any]:
        warnings.warn(
            "Property 'realy_used_values' is deprecated."
            " Use 'really_used_values' instead.",
            DeprecationWarning
        )
        return self._really_used_values

    @property
    def used_values(self) -> Dict[str, Any]:
        return self._used_values

    @staticmethod
    def split_keys_to_subdicts(values: Dict[str, Any]) -> Dict[str, Any]:
        output = {}
        formatter = Formatter()
        for key, value in values.items():
            _, field_name, _, _ = next(formatter.parse(f"{{{key}}}"))
            key_subdict = list(SUB_DICT_PATTERN.findall(field_name))
            data = output
            last_key = key_subdict.pop(-1)
            for subkey in key_subdict:
                if subkey not in data:
                    data[subkey] = {}
                data = data[subkey]
            data[last_key] = value
        return output

    def get_clean_used_values(self) -> Dict[str, Any]:
        new_used_values = {}
        for key, value in self.used_values.items():
            if isinstance(value, FormatObject):
                value = str(value)
            new_used_values[key] = value

        return self.split_keys_to_subdicts(new_used_values)

    def add_really_used_value(self, key: str, value: Any):
        self._really_used_values[key] = value

    def add_realy_used_value(self, key: str, value: Any):
        warnings.warn(
            "Method 'add_realy_used_value' is deprecated."
            " Use 'add_really_used_value' instead.",
            DeprecationWarning
        )
        self.add_really_used_value(key, value)

    def add_used_value(self, key: str, value: Any):
        self._used_values[key] = value

    def add_missing_key(self, key: str):
        if self._optional:
            self._missing_optional_keys.add(key)
        else:
            self._missing_keys.add(key)

    def add_invalid_type(self, key: str, value: Any):
        if self._optional:
            self._invalid_optional_types[key] = type(value)
        else:
            self._invalid_types[key] = type(value)


class FormatObject:
    """Object that can be used for formatting.

    This is base that is valid for to be used in 'StringTemplate' value.
    """
    def __init__(self):
        self.value = ""

    def __format__(self, *args, **kwargs):
        return self.value.__format__(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.value)

    def __repr__(self) -> str:
        return self.__str__()


class FormattingPart:
    """String with formatting template.

    Containt only single key to format e.g. "{project[name]}".

    Args:
        field_name (str): Name of key.
        format_spec (str): Format specification.
        conversion (Union[str, None]): Conversion type.

    """
    def __init__(
        self,
        field_name: str,
        format_spec: str,
        conversion: "Union[str, None]",
    ):
        format_spec_v = ""
        if format_spec:
            format_spec_v = f":{format_spec}"
        conversion_v = ""
        if conversion:
            conversion_v = f"!{conversion}"

        self._field_name: str = field_name
        self._format_spec: str = format_spec_v
        self._conversion: str = conversion_v

        template_base = f"{field_name}{format_spec_v}{conversion_v}"
        self._template_base: str = template_base
        self._template: str = f"{{{template_base}}}"

    @property
    def template(self) -> str:
        return self._template

    def __repr__(self) -> str:
        return "<Format:{}>".format(self._template)

    def __str__(self) -> str:
        return self._template

    @staticmethod
    def validate_value_type(value: Any) -> bool:
        """Check if value can be used for formatting of single key."""
        if isinstance(value, (numbers.Number, FormatObject)):
            return True

        for inh_class in type(value).mro():
            if inh_class is str:
                return True
        return False

    @staticmethod
    def validate_key_is_matched(key: str) -> bool:
        """Validate that opening has closing at correct place.
        Future-proof, only square brackets are currently used in keys.

        Example:
            >>> is_matched("[]()()(((([])))")
            False
            >>> is_matched("[](){{{[]}}}")
            True

        Returns:
            bool: Openings and closing are valid.

        """
        mapping = dict(zip("({[", ")}]"))
        opening = set(mapping.keys())
        closing = set(mapping.values())
        queue = []

        for letter in key:
            if letter in opening:
                queue.append(mapping[letter])
            elif letter in closing:
                if not queue or letter != queue.pop():
                    return False
        return not queue

    @staticmethod
    def keys_to_template_base(keys: List[str]):
        if not keys:
            return None
        # Create copy of keys
        keys = list(keys)
        template_base = keys.pop(0)
        joined_keys = "".join([f"[{key}]" for key in keys])
        return f"{template_base}{joined_keys}"

    def format(
        self, data: Dict[str, Any], result: TemplatePartResult
    ) -> TemplatePartResult:
        """Format the formattings string.

        Args:
            data(dict): Data that should be used for formatting.
            result(TemplatePartResult): Object where result is stored.

        """
        key = self._template_base
        if key in result.really_used_values:
            result.add_output(result.really_used_values[key])
            return result

        # ensure key is properly formed [({})] properly closed.
        if not self.validate_key_is_matched(key):
            result.add_missing_key(key)
            result.add_output(self.template)
            return result

        # check if key expects subdictionary keys (e.g. project[name])
        key_subdict = list(SUB_DICT_PATTERN.findall(self._field_name))

        value = data
        missing_key = False
        invalid_type = False
        used_keys = []
        keys_to_value = None
        used_value = None

        for sub_key in key_subdict:
            if isinstance(value, list):
                if not sub_key.lstrip("-").isdigit():
                    invalid_type = True
                    break
                sub_key = int(sub_key)
                if sub_key < 0:
                    sub_key = len(value) + sub_key

                invalid = 0 > sub_key < len(data)
                if invalid:
                    used_keys.append(sub_key)
                    missing_key = True
                    break

                used_keys.append(sub_key)
                if keys_to_value is None:
                    keys_to_value = list(used_keys)
                    keys_to_value.pop(-1)
                    used_value = copy.deepcopy(value)
                value = value[sub_key]
                continue

            if (
                value is None
                or (hasattr(value, "items") and sub_key not in value)
            ):
                missing_key = True
                used_keys.append(sub_key)
                break

            if not hasattr(value, "items"):
                invalid_type = True
                break

            used_keys.append(sub_key)
            value = value.get(sub_key)

        field_name = key_subdict[0]
        if used_keys:
            field_name = self.keys_to_template_base(used_keys)

        if missing_key or invalid_type:
            if missing_key:
                result.add_missing_key(field_name)

            elif invalid_type:
                result.add_invalid_type(field_name, value)

            result.add_output(self.template)
            return result

        if not self.validate_value_type(value):
            result.add_invalid_type(key, value)
            result.add_output(self.template)
            return result

        fill_data = root_fill_data = {}
        parent_fill_data = None
        parent_key = None
        fill_value = data
        value_filled = False
        for used_key in used_keys:
            if isinstance(fill_value, list):
                parent_fill_data[parent_key] = fill_value
                value_filled = True
                break
            fill_value = fill_value[used_key]
            parent_fill_data = fill_data
            fill_data = parent_fill_data.setdefault(used_key, {})
            parent_key = used_key

        if not value_filled:
            parent_fill_data[used_keys[-1]] = value

        template = f"{{{field_name}{self._format_spec}{self._conversion}}}"
        formatted_value = template.format(**root_fill_data)
        used_key = key
        if keys_to_value is not None:
            used_key = self.keys_to_template_base(keys_to_value)

        if used_value is None:
            if isinstance(value, numbers.Number):
                used_value = value
            else:
                used_value = formatted_value
        result.add_really_used_value(self._field_name, used_value)
        result.add_used_value(used_key, used_value)
        result.add_output(formatted_value)
        return result


class OptionalPart:
    """Template part which contains optional formatting strings.

    If this part can't be filled the result is empty string.

    Args:
        parts(list): Parts of template. Can contain 'str', 'OptionalPart' or
            'FormattingPart'.
    """

    def __init__(
        self,
        parts: List["Union[str, OptionalPart, FormattingPart]"]
    ):
        self._parts: List["Union[str, OptionalPart, FormattingPart]"] = parts

    @property
    def parts(self) -> List["Union[str, OptionalPart, FormattingPart]"]:
        return self._parts

    def __str__(self) -> str:
        return "<{}>".format("".join([str(p) for p in self._parts]))

    def __repr__(self) -> str:
        return "<Optional:{}>".format("".join([str(p) for p in self._parts]))

    def format(
        self,
        data: Dict[str, Any],
        result: TemplatePartResult,
    ) -> TemplatePartResult:
        new_result = TemplatePartResult(True)
        for part in self._parts:
            if isinstance(part, str):
                new_result.add_output(part)
            else:
                part.format(data, new_result)

        if new_result.solved:
            result.add_output(new_result)
        return result
