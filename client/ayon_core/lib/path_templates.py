from __future__ import annotations

import os
import re
import copy
import numbers
import warnings
import platform
from dataclasses import dataclass
from functools import lru_cache
from string import Formatter
from typing import Any, Callable, Union, Iterable, Optional

SUB_DICT_PATTERN = re.compile(r"([^\[\]]+)")
OPTIONAL_PATTERN = re.compile(r"(<.*?[^{0]*>)[^0-9]*?")
_IS_WINDOWS = platform.system().lower() == "windows"
_FORMATTER = Formatter()
_FIRST_CHAR_REGEX = re.compile(r"[a-zA-Z0-9]")
_FORMAT_SPEC_NAME_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]+$")
# Named format specs that can be used in templates, e.g. '{key:upper}'
_FORMAT_SPECS: dict[str, Callable[[str], str]] = {}


def register_template_format_spec(
    name: str, func: Callable[[str], str]
) -> None:
    """Register named format spec usable in templates.

    Registered name can be used as format spec of any template key
        formatted with 'StringTemplate' (that includes anatomy templates).

    Example:
        >>> register_template_format_spec("reverse", lambda v: v[::-1])
        >>> str(StringTemplate("{name:reverse}").format({"name": "abc"}))
        'cba'

    Args:
        name (str): Name of the format spec. Must start with a letter
            and contain at least 2 letters, digits or underscores so
            it cannot clash with the python format spec mini-language.
        func (Callable[[str], str]): Function that receives a value
            converted to string and returns the formatted string.

    Raises:
        ValueError: If the name is not valid.

    """
    if not isinstance(name, str) or not _FORMAT_SPEC_NAME_REGEX.match(name):
        raise ValueError(
            f"Invalid template format spec name \"{name}\"."
            " Name must start with a letter and contain at least"
            " 2 letters, digits or underscores."
        )
    _FORMAT_SPECS[name] = func


def get_template_format_specs() -> dict[str, Callable[[str], str]]:
    """Named format specs that can be used in templates.

    Returns:
        dict[str, Callable[[str], str]]: Format function by spec name.

    """
    return dict(_FORMAT_SPECS)


def _upper_first(value: str) -> str:
    """Uppercase first letter or digit, the rest is not changed.

    Leading symbols are skipped, 'str.capitalize' is not used because it
        does lowercase the rest of the string.

    Example:
        >>> _upper_first("mainBeauty")
        'MainBeauty'
        >>> _upper_first("_shot")
        '_Shot'

    """
    match = _FIRST_CHAR_REGEX.search(value)
    if match is None:
        return value
    idx = match.start()
    return f"{value[:idx]}{value[idx].upper()}{value[idx + 1:]}"


def _lower_first(value: str) -> str:
    """Lowercase first letter or digit, the rest is not changed."""
    match = _FIRST_CHAR_REGEX.search(value)
    if match is None:
        return value
    idx = match.start()
    return f"{value[:idx]}{value[idx].lower()}{value[idx + 1:]}"


def _split_words(value: str) -> list[str]:
    """Split string to words by symbols and by camel case.

    Example:
        >>> _split_words("char_SuperHero")
        ['char', 'Super', 'Hero']
        >>> _split_words("sh010 HTTPServer")
        ['sh010', 'HTTP', 'Server']

    """
    words = []
    word = ""
    for idx, char in enumerate(value):
        if not char.isalnum():
            if word:
                words.append(word)
                word = ""
            continue

        if (
            word
            and char.isupper()
            and (
                not word[-1].isupper()
                or value[idx + 1:idx + 2].islower()
            )
        ):
            words.append(word)
            word = ""
        word += char

    if word:
        words.append(word)
    return words


def _camel_case(value: str) -> str:
    words = _split_words(value)
    if not words:
        return ""
    first_word = words.pop(0).lower()
    return first_word + "".join(word.capitalize() for word in words)


def _pascal_case(value: str) -> str:
    return "".join(word.capitalize() for word in _split_words(value))


def _snake_case(value: str) -> str:
    return "_".join(word.lower() for word in _split_words(value))


for _name, _func in (
    ("upper", str.upper),
    ("lower", str.lower),
    ("upperfirst", _upper_first),
    ("lowerfirst", _lower_first),
    ("title", str.title),
    ("camel", _camel_case),
    ("pascal", _pascal_case),
    ("snake", _snake_case),
):
    register_template_format_spec(_name, _func)


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


class DefaultKeysDict(dict):
    """Dictionary that supports the default key to use for str conversion.

    Is helpful for changes of a key in a template from string to dictionary
        for example '{folder}' -> '{folder[name]}'.
        >>> data = DefaultKeysDict(
        >>>     "name",
        >>>     {"folder": {"name": "FolderName"}}
        >>> )
        >>> print("{folder[name]}".format_map(data))
        FolderName
        >>> print("{folder}".format_map(data))
        FolderName

    Args:
        default_key (Union[str, Iterable[str]]): Default key to use for str
            conversion. Can also expect multiple keys for more nested
            dictionary.

    """
    def __init__(
        self, default_keys: Union[str, Iterable[str]], *args, **kwargs
    ) -> None:
        if isinstance(default_keys, str):
            default_keys = [default_keys]
        else:
            default_keys = list(default_keys)
        if not default_keys:
            raise ValueError(
                "Default key must be set. Got empty default keys."
            )

        self._default_keys = default_keys
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        return str(self.get_default_value())

    def get_default_keys(self) -> list[str]:
        return list(self._default_keys)

    def get_default_value(self) -> Any:
        value = self
        for key in self._default_keys:
            value = value[key]
        return value


class StringTemplate:
    """String that can be formatted.

    Template keys use python formatting syntax with a few additions.

    Optional parts are wrapped in '<' and '>', the part is skipped if any
        of its keys is not available in the data.
        >>> template = StringTemplate("{name}<_{comment}>")
        >>> str(template.format({"name": "review"}))
        'review'

    Named format specs change the formatted value, more can be added
        with 'register_template_format_spec'. Available by default are:
        - 'upper': 'char_superHero' -> 'CHAR_SUPERHERO'
        - 'lower': 'char_superHero' -> 'char_superhero'
        - 'upperfirst': 'char_superHero' -> 'Char_superHero'
        - 'lowerfirst': 'Char_superHero' -> 'char_superHero'
        - 'title': 'char_superHero' -> 'Char_Superhero'
        - 'camel': 'char_superHero' -> 'charSuperHero'
        - 'pascal': 'char_superHero' -> 'CharSuperHero'
        - 'snake': 'char_superHero' -> 'char_super_hero'
        >>> data = {"task": {"name": "lightRig"}}
        >>> str(StringTemplate("{task[name]:upper}").format(data))
        'LIGHTRIG'
        >>> str(StringTemplate("{task[name]:snake}").format(data))
        'light_rig'

    Legacy keys '{Key}' and '{KEY}' are resolved as '{key:upperfirst}' and
        '{key:upper}' if the data does not contain 'Key' or 'KEY', so
        the data does not have to contain all 3 variants of each key.
        >>> str(StringTemplate("{Task[name]}_{TASK[NAME]}").format(data))
        'LightRig_LIGHTRIG'

    """
    def __init__(self, template: str):
        if not isinstance(template, str):
            raise TypeError(
                f"<{self.__class__.__name__}> argument must be a string,"
                f" not {str(type(template))}."
            )

        self._template: str = template
        self._parts: list[str | OptionalPart | FormattingPart] = (
            self._parse_parts(template)
        )

    @classmethod
    def _parse_parts(
        cls, template: str
    ) -> list[str | OptionalPart | FormattingPart]:
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

        return cls.find_optional_parts(new_parts)

    def __str__(self) -> str:
        return self.template

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}> {self.template}"

    def __contains__(self, other: str) -> bool:
        return other in self.template

    def replace(self, *args, **kwargs):
        self._template = self.template.replace(*args, **kwargs)
        self._parts = self._parse_parts(self._template)
        return self

    @property
    def template(self) -> str:
        return self._template

    def format(self, data: dict[str, Any]) -> "TemplateResult":
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

    def format_map(self, data: dict[str, Any]) -> "TemplateResult":
        """Format the template using a mapping of replacement values.

        This mirrors :meth:`str.format_map`.

        Args:
            data (dict): Containing keys to be filled into the template.

        Returns:
            TemplateResult: Filled or partially filled template.
        """
        return self.format(data)

    def format_strict(self, data: dict[str, Any]) -> "TemplateResult":
        result = self.format(data)
        result.validate()
        return result

    def remove_optional_parts_for_data(
        self,
        data: Optional[dict[str, Any]] = None,
    ) -> str:
        """Remove optional parts from template for data.

        This method does not modify the template object itself.

        Note:
            At this moment the functionality is not 1:1 with 'format' where
                lists are supported and the values are validated.

        Args:
            data (Optional[dict[str, Any]]): Template data for template.

        Returns:
            str: Template without optional parts that are not available
                in passed data.

        """
        if data is None:
            data = {}

        output = ""
        for part in self._parts:
            if isinstance(part, str):
                output += part
            elif isinstance(part, FormattingPart):
                output += part.template
            elif isinstance(part, OptionalPart):
                output += part.remove_optional_parts_for_data(data)
            else:
                raise TypeError(
                    f"Got invalid type in template parts '{type(part)}'"
                )
        return output

    @classmethod
    def format_template(
        cls, template: str, data: dict[str, Any]
    ) -> "TemplateResult":
        objected_template = cls(template)
        return objected_template.format(data)

    @classmethod
    def format_strict_template(
        cls, template: str, data: dict[str, Any]
    ) -> "TemplateResult":
        objected_template = cls(template)
        return objected_template.format_strict(data)

    @staticmethod
    def find_optional_parts(
        parts: list[Union[str, FormattingPart]]
    ) -> list[Union[str, OptionalPart, FormattingPart]]:
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
                        value = f"<{parts[0]}>"
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
        missing_keys (list[str]): Missing keys that were not in the data.
            Include missing optional keys.
        invalid_types (dict): When key was found in data, but value had not
            allowed DataType. Allowed data types are `numbers`,
            `str`(`basestring`) and `dict`. Dictionary may cause invalid type
            when value of key in data is dictionary but template expect string
            of number.
    """

    used_values: dict[str, Any] = None
    solved: bool = None
    template: str = None
    missing_keys: list[str] = None
    invalid_types: dict[str, Any] = None

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
        path = str(self)
        if _IS_WINDOWS:
            path = path.replace("\\", "/")
        return cls(
            os.path.normpath(path),
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
        self._missing_keys: set[str] = set()
        self._invalid_types: dict[str, Any] = {}
        # Missing keys or invalid value types of optional keys
        self._missing_optional_keys: set[str] = set()
        self._invalid_optional_types: dict[str, Any] = {}

        # Used values stored by key with origin type
        #   - key without any padding or key modifiers
        #   - value from filling data
        #   Example: {"version": 1}
        self._used_values: dict[str, Any] = {}
        # Used values stored by key with all modifirs
        #   - value is already formatted string
        #   Example: {"version:0>3": "001"}
        self._really_used_values: dict[str, Any] = {}
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
            raise TypeError(
                f"Cannot add data from \"{type(other)}\""
                f" to \"{self.__class__.__name__}\""
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
    def missing_keys(self) -> set[str]:
        return self._missing_keys

    @property
    def missing_optional_keys(self) -> set[str]:
        return self._missing_optional_keys

    @property
    def invalid_types(self) -> dict[str, Any]:
        return self._invalid_types

    @property
    def invalid_optional_types(self) -> dict[str, Any]:
        return self._invalid_optional_types

    @property
    def really_used_values(self) -> dict[str, Any]:
        return self._really_used_values

    @property
    def realy_used_values(self) -> dict[str, Any]:
        warnings.warn(
            "Property 'realy_used_values' is deprecated."
            " Use 'really_used_values' instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return self._really_used_values

    @property
    def used_values(self) -> dict[str, Any]:
        return self._used_values

    @staticmethod
    def split_keys_to_subdicts(values: dict[str, Any]) -> dict[str, Any]:
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

    def get_clean_used_values(self) -> dict[str, Any]:
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
            DeprecationWarning,
            stacklevel=2,
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


@dataclass
class _LegacyCase:
    """Definition of legacy key variant, '{Key}' or '{KEY}'.

    Data used to contain all variants of each key, e.g. 'task', 'Task'
        and 'TASK'. The variants are resolved from the lowercase key
        during formatting instead.

    Attributes:
        keys (tuple[str, ...]): Lowercase keys used for lookup in data.
        only_first_key (bool): Only first key has changed case.
        key_func (Callable[[str], str]): Function to convert key in data
            to the variant.
        value_func (Callable[[str], str]): Function to convert the value.

    """
    keys: tuple[str, ...]
    only_first_key: bool
    key_func: Callable[[str], str]
    value_func: Callable[[str], str]


@lru_cache(maxsize=1024)
def _get_legacy_cases(keys: tuple[str, ...]) -> tuple[_LegacyCase, ...]:
    """Legacy variants that template keys can be.

    Example:
        'Task[name]' -> first letter of 'task[name]' value is uppercased
        'TASK[NAME]' -> value of 'task[name]' is uppercased
        'task[name]' -> not a legacy variant

    Args:
        keys (tuple[str, ...]): Keys of the template, e.g. ('Task', 'name').

    Returns:
        tuple[_LegacyCase, ...]: Possible variants of the keys.

    """
    if not keys:
        return ()

    first_key = keys[0]
    lower_first_key = first_key.lower()
    if first_key == lower_first_key:
        return ()

    output = []
    if first_key == first_key.capitalize():
        output.append(_LegacyCase(
            (lower_first_key, ) + keys[1:], True, str.capitalize, _upper_first
        ))

    if all(key == key.upper() for key in keys):
        output.append(_LegacyCase(
            tuple(key.lower() for key in keys), False, str.upper, str.upper
        ))
    return tuple(output)


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
        conversion: Union[str, None],
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
        # Name of possible named format spec, e.g. 'upper'
        self._format_spec_name: Optional[str] = format_spec or None
        self._conversion_char: Optional[str] = conversion or None

        template_base = f"{field_name}{conversion_v}{format_spec_v}"
        self._template_base: str = template_base
        self._template: str = f"{{{template_base}}}"

        # Template is parsed once and can be formatted many times
        self._keys: tuple[str, ...] = tuple(
            SUB_DICT_PATTERN.findall(field_name)
        )
        # Validated on first formatting
        self._key_is_matched: Optional[bool] = None

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
    def keys_to_template_base(keys: list[str]):
        if not keys:
            return None
        # Create copy of keys
        keys = list(keys)
        template_base = keys.pop(0)
        joined_keys = "".join([f"[{key}]" for key in keys])
        return f"{template_base}{joined_keys}"

    def keys(self) -> tuple[str]:
        """Return keys of the template.

        Returns:
            tuple[str]: Keys of the template.

        """
        return self._keys

    def _find_legacy_case_value(
        self, data: dict[str, Any]
    ) -> Optional[tuple[list[str], Any, Callable[[str], str]]]:
        """Find value of legacy '{Key}' or '{KEY}' key in data.

        Args:
            data (dict[str, Any]): Data that should be used for formatting.

        Returns:
            Optional[tuple[list[str], Any, Callable[[str], str]]]: Real
                keys to the value in data, the value and function that
                should be used to modify the value if is string.

        """
        for legacy_case in _get_legacy_cases(self._keys):
            value = data
            used_keys = []
            for idx, key in enumerate(self._keys):
                if not hasattr(value, "items"):
                    break

                if idx > 0 and legacy_case.only_first_key:
                    if key not in value:
                        break
                    data_key = key
                else:
                    data_key = legacy_case.keys[idx]
                    if data_key not in value:
                        # Key in data may not be lowercase
                        for data_key in value:
                            if (
                                isinstance(data_key, str)
                                and legacy_case.key_func(data_key) == key
                            ):
                                break
                        else:
                            break

                used_keys.append(data_key)
                value = value[data_key]
            else:
                return used_keys, value, legacy_case.value_func
        return None

    def format(
        self, data: dict[str, Any], result: TemplatePartResult
    ) -> TemplatePartResult:
        """Format the formattings string.

        Args:
            data(dict): Data that should be used for formatting.
            result(TemplatePartResult): Object where result is stored.

        """
        key = self._template_base

        # ensure key is properly formed [({})] properly closed.
        key_is_matched = self._key_is_matched
        if key_is_matched is None:
            key_is_matched = self.validate_key_is_matched(key)
            self._key_is_matched = key_is_matched

        if not key_is_matched:
            result.add_missing_key(key)
            result.add_output(self.template)
            return result

        # check if key expects subdictionary keys (e.g. project[name])
        key_subdict = self._keys

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

                valid = 0 <= sub_key < len(value)
                if not valid:
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

        # Legacy '{Key}' and '{KEY}' are filled with value of 'key'
        #   if data do not contain them
        legacy_value_func = None
        if missing_key and len(used_keys) == 1:
            legacy_item = self._find_legacy_case_value(data)
            if legacy_item is not None:
                used_keys, value, legacy_value_func = legacy_item
                field_name = self.keys_to_template_base(used_keys)
                missing_key = False

        if missing_key or invalid_type:
            if missing_key:
                result.add_missing_key(field_name)

            elif invalid_type:
                result.add_invalid_type(field_name, value)

            result.add_output(self.template)
            return result

        if isinstance(value, DefaultKeysDict):
            try:
                value = value.get_default_value()
            except KeyError:
                pass

        if legacy_value_func is not None and isinstance(value, str):
            value = legacy_value_func(value)

        if not self.validate_value_type(value):
            result.add_invalid_type(key, value)
            result.add_output(self.template)
            return result

        format_func = None
        if self._format_spec_name is not None:
            format_func = _FORMAT_SPECS.get(self._format_spec_name)

        if format_func is not None:
            return self._format_named_spec(
                value, format_func, keys_to_value, used_value, result
            )

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

        template = f"{{{field_name}{self._conversion}{self._format_spec}}}"
        formatted_value = template.format_map(root_fill_data)
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

    def _format_named_spec(
        self,
        value: Any,
        format_func: Callable[[str], str],
        keys_to_value: Optional[list[Any]],
        used_value: Any,
        result: TemplatePartResult,
    ) -> TemplatePartResult:
        """Format value using named format spec, e.g. '{key:upper}'.

        Args:
            value (Any): Value that should be formatted.
            format_func (Callable[[str], str]): Function of the format spec.
            keys_to_value (Optional[list[Any]]): Keys to the list in which
                is the value stored.
            used_value (Any): The list in which is the value stored.
            result (TemplatePartResult): Object where result is stored.

        """
        str_value = value
        if self._conversion_char is not None:
            str_value = _FORMATTER.convert_field(
                str_value, self._conversion_char
            )
        if not isinstance(str_value, str):
            str_value = format(str_value, "")

        used_key = self._template_base
        if keys_to_value is not None:
            used_key = self.keys_to_template_base(keys_to_value)

        # Used value is the source value, the format spec is not applied
        if used_value is None:
            if isinstance(value, numbers.Number):
                used_value = value
            else:
                used_value = str_value
        result.add_really_used_value(self._field_name, used_value)
        result.add_used_value(used_key, used_value)
        result.add_output(format_func(str_value))
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
        parts: list[Union[str, OptionalPart, FormattingPart]]
    ):
        self._parts: list[Union[str, OptionalPart, FormattingPart]] = parts

    @property
    def parts(self) -> list[Union[str, OptionalPart, FormattingPart]]:
        return self._parts

    def remove_optional_parts_for_data(self, data: dict[str, Any]) -> str:
        if not data:
            return ""

        output = ""
        for part in self._parts:
            if isinstance(part, str):
                output += part
            elif isinstance(part, OptionalPart):
                output += part.remove_optional_parts_for_data(data)

            elif isinstance(part, FormattingPart):
                data_v = data
                for key in part.keys():
                    if key not in data_v:
                        return ""
                    try:
                        data_v = data_v[key]
                    except (KeyError, IndexError, TypeError):
                        return ""
                output += part.template

            else:
                raise TypeError(
                    f"Got invalid type in template parts '{type(part)}'"
                )
        return output

    def __str__(self) -> str:
        joined_parts = "".join([str(p) for p in self._parts])
        return f"<{joined_parts}>"

    def __repr__(self) -> str:
        joined_parts = "".join([str(p) for p in self._parts])
        return f"<Optional:{joined_parts}>"

    def format(
        self,
        data: dict[str, Any],
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
