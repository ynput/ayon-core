# -*- coding: utf-8 -*-
"""AYON plugin tools."""
import os
import logging
import re
import collections
from typing import Optional, Any
import clique
import speedcopy

from ayon_api import get_last_version_by_product_name, get_representations


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


def fill_sequence_gaps_with_previous(
    collection: str,
    staging_dir: str,
    instance: pyblish.plugin.Instance,
    current_repre_name: str,
    start_frame: int,
    end_frame: int
) -> tuple[Optional[dict[str, Any]], Optional[dict[int, str]]]:
    """Tries to replace missing frames from ones from last version"""
    used_version_entity, repre_file_paths = _get_last_version_files(
        instance, current_repre_name
    )
    if repre_file_paths is None:
        # issues in getting last version files
        return (None, None)

    prev_collection = clique.assemble(
        repre_file_paths,
        patterns=[clique.PATTERNS["frames"]],
        minimum_items=1
    )[0][0]
    prev_col_format = prev_collection.format("{head}{padding}{tail}")

    added_files = {}
    anatomy = instance.context.data["anatomy"]
    col_format = collection.format("{head}{padding}{tail}")
    for frame in range(start_frame, end_frame + 1):
        if frame in collection.indexes:
            continue
        hole_fpath = os.path.join(staging_dir, col_format % frame)

        previous_version_path = prev_col_format % frame
        previous_version_path = anatomy.fill_root(previous_version_path)
        if not os.path.exists(previous_version_path):
            log.warning(
                "Missing frame should be replaced from "
                f"'{previous_version_path}' but that doesn't exist. "
            )
            return (None, None)

        log.warning(
            f"Replacing missing '{hole_fpath}' with "
            f"'{previous_version_path}'"
        )
        speedcopy.copyfile(previous_version_path, hole_fpath)
        added_files[frame] = hole_fpath

    return (used_version_entity, added_files)


def _get_last_version_files(
    instance: pyblish.plugin.Instance,
    current_repre_name: str,
) -> tuple[Optional[dict[str, Any], Optional[list[str]]]:
    product_name = instance.data["productName"]
    project_name = instance.data["projectEntity"]["name"]
    folder_entity = instance.data["folderEntity"]

    version_entity = get_last_version_by_product_name(
        project_name,
        product_name,
        folder_entity["id"],
        fields={"id", "attrib"}
    )

    if not version_entity:
        return None, None

    matching_repres = get_representations(
        project_name,
        version_ids=[version_entity["id"]],
        representation_names=[current_repre_name],
        fields={"files"}
    )

    matching_repre = next(matching_repres, None)
    if not matching_repre:
        return None, None
    

    repre_file_paths = [
        file_info["path"]
        for file_info in matching_repre["files"]
    ]

    return (version_entity, repre_file_paths)
