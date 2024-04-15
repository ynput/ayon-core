# -*- coding: utf-8 -*-
"""AYON plugin tools."""
import os
import logging
import re
import collections

log = logging.getLogger(__name__)

CAPITALIZE_REGEX = re.compile(r"[a-zA-Z0-9]")


def _capitalize_value(value):
    """Capitalize first char of value.

    Function finds first available character or number in passed string
        and uppers the character.

    Example:
        >>> _capitalize_value("host")
        'Host'
        >>> _capitalize_value("01_shot")
        '01_shot'
        >>> _capitalize_value("_shot")
        '_Shot'

    Args:
        value (str): Value where to capitalize first character.
    """

    # - conditions are because of possible index errors
    # - regex is to skip symbols that are not chars or numbers
    #   - e.g. "{key}" which starts with curly bracket
    capitalized = ""
    for idx in range(len(value or "")):
        char = value[idx]
        if not CAPITALIZE_REGEX.match(char):
            capitalized += char
        else:
            capitalized += char.upper()
            capitalized += value[idx + 1:]
            break
    return capitalized


def _separate_keys_and_value(data):
    valid_items = []
    hierachy_queue = collections.deque()
    hierachy_queue.append((data, []))
    while hierachy_queue:
        item = hierachy_queue.popleft()
        src_data, keys = item
        if src_data is None:
            continue

        if isinstance(src_data, (list, tuple, set)):
            for idx, item in enumerate(src_data):
                hierachy_queue.append((item, keys + [idx]))
            continue

        if isinstance(src_data, dict):
            for key, value in src_data.items():
                hierachy_queue.append((value, keys + [key]))
            continue

        if keys:
            valid_items.append((keys, src_data))
    return valid_items


def prepare_template_data(fill_pairs):
    """Prepares formatted data for filling template.

    It produces multiple variants of keys (key, Key, KEY) to control
    format of filled template.

    Example:
        >>> src_data = {
        ...    "host": "maya",
        ... }
        >>> output = prepare_template_data(src_data)
        >>> sorted(list(output.items())) # sort & list conversion for tests
        [('HOST', 'MAYA'), ('Host', 'Maya'), ('host', 'maya')]

    Args:
        fill_pairs (Union[dict[str, Any], Iterable[Tuple[str, Any]]]): The
            value that are prepared for template.

    Returns:
        dict[str, str]: Prepared values for template.
    """

    valid_items = _separate_keys_and_value(fill_pairs)
    output = {}
    for item in valid_items:
        keys, value = item
        # Convert only string values
        if isinstance(value, str):
            upper_value = value.upper()
            capitalized_value = _capitalize_value(value)
        else:
            upper_value = capitalized_value = value

        first_key = keys.pop(0)
        if not keys:
            output[first_key] = value
            output[first_key.upper()] = upper_value
            output[first_key.capitalize()] = capitalized_value
            continue

        # Prepare 'normal', 'upper' and 'capitalized' variables
        normal = output.setdefault(first_key, {})
        capitalized = output.setdefault(first_key.capitalize(), {})
        upper = output.setdefault(first_key.upper(), {})

        keys_deque = collections.deque(keys)
        while keys_deque:
            key = keys_deque.popleft()
            upper_key = key
            if isinstance(key, str):
                upper_key = key.upper()

            if not keys_deque:
                # Fill value on last key
                upper[upper_key] = upper_value
                capitalized[key] = capitalized_value
                normal[key] = value
            else:
                normal = normal.setdefault(key, {})
                capitalized = capitalized.setdefault(key, {})
                upper = upper.setdefault(upper_key, {})
    return output


def source_hash(filepath, *args):
    """Generate simple identifier for a source file.
    This is used to identify whether a source file has previously been
    processe into the pipeline, e.g. a texture.
    The hash is based on source filepath, modification time and file size.
    This is only used to identify whether a specific source file was already
    published before from the same location with the same modification date.
    We opt to do it this way as opposed to Avalanch C4 hash as this is much
    faster and predictable enough for all our production use cases.
    Args:
        filepath (str): The source file path.
    You can specify additional arguments in the function
    to allow for specific 'processing' values to be included.
    """
    # We replace dots with comma because . cannot be a key in a pymongo dict.
    file_name = os.path.basename(filepath)
    time = str(os.path.getmtime(filepath))
    size = str(os.path.getsize(filepath))
    return "|".join([file_name, time, size] + list(args)).replace(".", ",")
