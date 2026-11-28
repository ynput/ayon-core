"""Conversion of legacy template keys to named format specs.

Product name and product group templates used keys like '{Task[name]}'
    or '{TASK[NAME]}' where the case of the key defined case of the value.
    Data for the templates had to contain all variants of each key. Templates
    can use named format specs instead, e.g. '{task[name]:upperfirst}' and
    '{task[name]:upper}'.

Note:
    This module must not import from 'ayon_server' so it can be tested
    without the server.

"""
from __future__ import annotations

import re

_FIELD_REGEX = re.compile(
    r"(?<!\{)\{"
    r"(?P<field>[^{}!:]+)"
    r"(?P<conversion>![^{}:]*)?"
    r"(?P<spec>:[^{}]*)?"
    r"\}(?!\})"
)
_KEYS_REGEX = re.compile(r"[^\[\]]+")


def _convert_field(match: re.Match) -> str:
    field = match.group("field")
    # Field with conversion or format spec cannot get named format spec
    if match.group("conversion") or match.group("spec"):
        return match.group(0)

    keys = _KEYS_REGEX.findall(field)
    if not keys:
        return match.group(0)

    first_key = keys[0]
    lower_first_key = first_key.lower()
    if first_key == lower_first_key:
        return match.group(0)

    # Same priority as 'prepare_template_data' had, capitalized key wins
    #   for single character keys
    if first_key == first_key.capitalize():
        sub_keys = "".join(f"[{key}]" for key in keys[1:])
        return f"{{{lower_first_key}{sub_keys}:upperfirst}}"

    if all(key == key.upper() for key in keys):
        sub_keys = "".join(f"[{key.lower()}]" for key in keys[1:])
        return f"{{{lower_first_key}{sub_keys}:upper}}"

    return match.group(0)


def convert_legacy_template_keys(template: str) -> str:
    """Convert legacy '{Key}' and '{KEY}' template keys.

    Example:
        >>> convert_legacy_template_keys("{product[type]}{Task[name]}")
        '{product[type]}{task[name]:upperfirst}'
        >>> convert_legacy_template_keys("{FOLDER[NAME]}<_{Variant}>")
        '{folder[name]:upper}<_{variant:upperfirst}>'

    Keys that are lowercase, already use a format spec or do not match
        any legacy variant are kept as they are.

    Args:
        template (str): Template that may contain legacy keys.

    Returns:
        str: Template with named format specs instead of legacy keys.

    """
    if not template or not isinstance(template, str):
        return template
    return _FIELD_REGEX.sub(_convert_field, template)
