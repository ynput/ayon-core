from __future__ import annotations

import re
import logging
import typing

log = logging.getLogger(__name__)


def compile_list_of_regexes(in_list):
    """Convert strings in entered list to compiled regex objects."""
    regexes = list()
    if not in_list:
        return regexes

    for item in in_list:
        if not item:
            continue
        try:
            regexes.append(re.compile(item))
        except TypeError:
            print((
                "Invalid type \"{}\" value \"{}\"."
                " Expected string based object. Skipping."
            ).format(str(type(item)), str(item)))
    return regexes


def fullmatch(regex, string, flags=0):
    """Emulate python-3.4 re.fullmatch()."""
    matched = re.match(regex, string, flags=flags)
    if matched and matched.span()[1] == len(string):
        return matched
    return None


def sort_dict(data: dict, keys_order: typing.Iterable[str]):
    """Sort dictionary by a given key order.

    Keys not included in `keys_order` are added to the end of the dictionary.

    Args:
        data (dict): Dictionary to sort.
        keys_order (Iterable[str]): Desired order of keys.

    Returns:
        dict: Sorted dictionary.

    """
    ordered = {k: data[k] for k in keys_order if k in data}
    rest = {k: data[k] for k in data if k not in ordered}
    return ordered | rest


def validate_value_by_regexes(value, in_list):
    """Validates in any regex from list match entered value.

    Args:
        value (str): String where regexes is checked.
        in_list (list): List with regexes.

    Returns:
        int: Returns `0` when list is not set, is empty or contain "*".
            Returns `1` when any regex match value and returns `-1`
            when none of regexes match entered value.
    """
    if not in_list:
        return 0

    if not isinstance(in_list, (list, tuple, set)):
        in_list = [in_list]

    if "*" in in_list:
        return 0

    # If value is not set and in list has specific values then resolve value
    #   as not matching.
    if not value:
        return -1

    regexes = compile_list_of_regexes(in_list)
    for regex in regexes:
        if hasattr(regex, "fullmatch"):
            result = regex.fullmatch(value)
        else:
            result = fullmatch(regex, value)
        if result:
            return 1
    return -1


def rank_profile(
    profile: dict[str, typing.Any],
    key_values: dict[str, typing.Any],
    logger: logging.Logger | None = None,
) -> int:
    """Compute a match score for a profile against the given key values.

    The score is calculated by the following rules:
    - If any key does not match: return -1.

    The score is a binary number where each bit represents a match or
    no match for a key.

    Examples:
        failed match:
        >>> rank_profile({"a": ["A"], "b": ["B"]}, {"a": "A", "b": "D"}),
        -1

        value match on both keys:
        >>> rank_profile({"a": ["A"], "b": ["B"]}, {"a": "A", "b": "B"}),
        3  # => binary: 11

        value match on first key, wildcard match on second key:
        >>> rank_profile({"a": ["A"], "b": ["*"]}, {"a": "a", "b": "B"}),
        2  # => binary: 10

        implicit wildcard match on "a", value match on "b":
        >>> rank_profile({"b": ["B"]}, {"a": "a", "b": "B"}),
        1  # => binary: 01

    Args:
        profile (dict): Profile to rank.
        key_values (dict): Key values to rank profile by.
        logger (logging.Logger | None): Logger for debug output.

    Returns:
        int: Rank of profile.

    """
    logger = logger or log

    score = 0
    for key, value in key_values.items():
        profile_value = profile.get(key) or []

        match = validate_value_by_regexes(value, profile_value)
        if match == -1:
            logger.debug(f"'{value}' not found in '{key}': {profile_value}")
            return -1

        score <<= 1     # shift score left by 1 bit
        score |= match  # set the current match bit in the score

    return score


def rank_profiles(
    profiles: list[dict[str, typing.Any]],
    key_values: dict[str, typing.Any],
    logger: logging.Logger,
) -> list[tuple[dict[str, typing.Any], int]]:
    """Rank profiles by the given filter criteria.

    Returns a list of (profile, score) tuples.
    """
    return [
        (profile, rank_profile(profile, key_values, logger))
        for profile in profiles
    ]


def get_matching_profiles(
    profiles: list[dict[str, typing.Any]],
    key_values: dict[str, typing.Any],
    logger: logging.Logger,
) -> list[dict[str, typing.Any]]:
    """Get all profiles matching the given filter criteria.

    Note:
        this returns ALL matching profiles, not just the highest score.
        Use `get_highest_score_profiles` to get only the highest-scoring
        profiles.

    Args:
        profiles (list[dict[str, typing.Any]]): List of profiles to rank.
        key_values (dict[str, typing.Any]): Key values to rank profiles by.
        logger (logging.Logger): Logger to use.

    Returns:
        list[dict[str, typing.Any]]: List of matching profiles.

    """
    return [
        profile
        for profile, score in rank_profiles(profiles, key_values, logger)
        if score >= 0
    ]


def get_highest_score_profiles(
    profiles: list[dict[str, typing.Any]],
    key_values: dict[str, typing.Any],
    logger: logging.Logger,
) -> list[dict[str, typing.Any]]:
    """Return all profiles that have the highest match score.

    Args:
        profiles (list[dict[str, typing.Any]]): List of profiles to rank.
        key_values (dict[str, typing.Any]): Key values to rank profiles by.
        logger (logging.Logger): Logger to use.

    Returns:
        list[dict[str, typing.Any]]: List of profiles with the highest score.
    """
    ranked_profiles = rank_profiles(profiles, key_values, logger)

    if not ranked_profiles:
        return []

    # get highest score
    scores = [score for _, score in ranked_profiles]
    highest_profile_points = max(scores)

    # get profiles with highest score
    return [
        profile
        for profile, score in ranked_profiles
        if score >= 0 and score == highest_profile_points
    ]


def filter_profiles(profiles_data, key_values, keys_order=None, logger=None):
    """Filter profiles by the given key-value pairs.

    Each profile is ranked based on the number of keys that match the
    `key_values`. If any key does not match, the profile is skipped.

    The profile with the highest number of exact matches (vs. wildcard matches)
    is returned.

    Args:
        profiles_data (list): Profile definitions as dictionaries.
        key_values (dict): Mapping of Key <-> Value. Key is checked if is
            available in profile and if Value is matching it's values.
        keys_order (list, tuple): Order of keys from `key_values` which matters
            only when multiple profiles have same score.
        logger (logging.Logger): Optionally can be passed different logger.

    Returns:
        dict/None: Return most matching profile or None if none of profiles
            match at least one criteria.

    """
    if not profiles_data:
        return None

    logger = logger or log

    if keys_order:
        key_values = sort_dict(key_values, keys_order)

    log_parts = " | ".join([f'{k}: "{v}"' for k, v in key_values.items()])

    logger.debug("Looking for matching profile for: {}".format(log_parts))
    profiles = get_highest_score_profiles(profiles_data, key_values, logger)

    if not profiles:
        logger.debug(f"None of profiles match your setup. {log_parts}")
        return None

    if len(profiles) > 1:
        logger.debug(f"More than one profile match your setup. {log_parts}")

    profile = profiles[0]
    logger.debug(f"Profile selected: {profile}")
    return profile
