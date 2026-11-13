"""Tests of profiles filtering."""
import pytest

from ayon_core.lib.profiles_filtering import (
    filter_profiles,
    validate_value_by_regexes,
)


@pytest.mark.parametrize(
    ("value", "filters", "expected"),
    [
        # Empty filters or wildcard always score 0
        ("modeling", None, 0),
        ("modeling", [], 0),
        ("modeling", ["*"], 0),
        ("", [], 0),
        ("", ["*"], 0),
        (None, ["*"], 0),
        # Regular matching
        ("modeling", ["modeling"], 1),
        ("modeling", ["model.*"], 1),
        ("modeling", "modeling", 1),
        ("modeling", ["rigging"], -1),
        ("modeling", ["model"], -1),
        # Empty string is matched against the filters
        ("", [".*"], 1),
        ("", ["a*"], 1),
        ("", ["modeling"], -1),
        # Empty item in filters targets empty value
        ("", [""], 1),
        ("", ["maya", ""], 1),
        ("", "", 0),
        ("maya", [""], -1),
        ("maya", ["maya", ""], 1),
        (None, [""], -1),
        # None does not match specific filters
        (None, [".*"], -1),
        (None, ["modeling"], -1),
    ],
)
def test_validate_value_by_regexes(value, filters, expected):
    assert validate_value_by_regexes(value, filters) == expected


def test_filter_profiles_highest_score():
    profiles = [
        {"name": "generic", "task_names": []},
        {"name": "specific", "task_names": ["modeling"]},
        {"name": "other", "task_names": ["rigging"]},
    ]
    profile = filter_profiles(profiles, {"task_names": "modeling"})
    assert profile["name"] == "specific"


def test_filter_profiles_empty_string_value():
    profiles = [
        {"name": "specific", "task_names": ["modeling"]},
        {"name": "any", "task_names": [".*"]},
    ]
    profile = filter_profiles(profiles, {"task_names": ""})
    assert profile["name"] == "any"


@pytest.mark.parametrize(
    ("host_name", "expected"),
    [
        ("", "no host"),
        ("maya", "maya"),
        ("nuke", "generic"),
        (None, "generic"),
    ],
)
def test_filter_profiles_profile_for_empty_value(host_name, expected):
    """Profile with empty filter item targets empty value.

    For example a profile for tray, where there is no host.
    """
    profiles = [
        {"name": "generic", "host_names": []},
        {"name": "no host", "host_names": [""]},
        {"name": "maya", "host_names": ["maya"]},
    ]
    profile = filter_profiles(profiles, {"host_names": host_name})
    assert profile["name"] == expected


def test_filter_profiles_none_value():
    profiles = [
        {"name": "specific", "task_names": ["modeling"]},
        {"name": "any", "task_names": [".*"]},
    ]
    assert filter_profiles(profiles, {"task_names": None}) is None


def test_filter_profiles_empty_string_falls_back_to_generic():
    profiles = [
        {"name": "specific", "task_names": ["modeling"]},
        {"name": "generic", "task_names": []},
    ]
    profile = filter_profiles(profiles, {"task_names": ""})
    assert profile["name"] == "generic"


def test_filter_profiles_no_profiles():
    assert filter_profiles([], {"task_names": "modeling"}) is None
    assert filter_profiles(None, {"task_names": "modeling"}) is None
