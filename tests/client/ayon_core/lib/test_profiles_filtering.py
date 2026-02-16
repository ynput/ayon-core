import logging
import unittest

from ayon_core.lib import profiles_filtering


log = logging.getLogger(__name__)


class TestRankProfile(unittest.TestCase):
    """Test `rank_profile` function."""

    def test_simple_match(self):
        profile = {
            "host": ["nuke"],
            "task": "render",
        }
        key_values = {
            "host": "nuke",
            "task": "render",
        }
        result = profiles_filtering.rank_profile(profile, key_values)
        expected = 0b11  # (both tests passed)
        self.assertEqual(result, expected)

    def test_no_match(self):
        profile = {"host": ["nuke"]}
        key_values = {"host": "maya"}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, -1)

    def test_wildcard_match(self):
        profile = {"host": ["*"]}
        key_values = {"host": "nuke"}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, 0)

    def test_implicit_wildcard_match(self):
        """Missing keys should be treated as wildcard."""
        profile = {"host": ["maya"]}
        key_values = {
            "host": "maya",
            "task": "modeling",  # missing key
        }
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, 0b10)  # match on host, wildcard on task

    def test_docstring_example_1(self):
        profile = {"a": ["A"], "b": ["B"]}
        values = {"a": "A", "b": "D"}
        result = profiles_filtering.rank_profile(profile, values)
        self.assertEqual(result, -1)

    def test_docstring_example_2(self):
        profile = {"a": ["A"], "b": ["B"]}
        values = {"a": "A", "b": "B"}
        result = profiles_filtering.rank_profile(profile, values)
        self.assertEqual(result, 0b11)  # match on both

    def test_docstring_example_3(self):
        profile = {"a": ["A"], "b": ["*"]}
        values = {"a": "A", "b": "B"}
        result = profiles_filtering.rank_profile(profile, values)
        self.assertEqual(result, 0b10)  # match on a, wildcard on b

    def test_docstring_example_4(self):
        profile = {"b": ["B"]}
        values = {"a": "A", "b": "B"}
        result = profiles_filtering.rank_profile(profile, values)
        self.assertEqual(result, 0b01)  # wildcard on a, match on b

    def test_many_conditions(self):
        profile = {
            "a": [],     # 0
            "b": ["y"],  # 1
            "c": ["y"],  # 1
            "d": [],     # 0
            "e": ["y"],  # 1
            "f": ["*"],  # 0
        }
        key_values = {
            "a": "y",
            "b": "y",
            "c": "y",
            "d": "y",
            "e": "y",
            "f": "y",
        }
        result = profiles_filtering.rank_profile(profile, key_values)
        expected = 0b011010
        self.assertEqual(result, expected)

    def test_empty_key_values_returns_zero(self):
        """No keys to match means score 0 (all wildcards)."""
        profile = {"host": "nuke", "task": "render"}
        key_values = {}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, 0)

    def test_profile_value_as_list_matches(self):
        """Profile value can be a list of allowed values (literal match)."""
        profile = {"host": ["nuke", "maya"], "task": "render"}
        key_values = {"host": "maya", "task": "render"}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, 0b11)

    def test_profile_value_as_list_no_match(self):
        profile = {"host": ["nuke", "maya"]}
        key_values = {"host": "houdini"}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, -1)

    def test_regex_in_profile_matches(self):
        profile = {"host": [r"nuke\d*"], "task": "*"}
        key_values = {"host": "nuke13", "task": "render"}
        result = profiles_filtering.rank_profile(profile, key_values)
        self.assertEqual(result, 0b10)  # host match (1), task wildcard (0)


class TestGetMatchingProfiles(unittest.TestCase):
    """Test `get_matching_profiles` function."""

    def test_no_match(self):
        profiles = [
            {"host": ["maya"]},
            {"host": ["houdini"]},
            {"host": ["nuke"]},
        ]
        key_values = {
            "host": "softimage",
        }
        matched_profiles = profiles_filtering.get_matching_profiles(profiles, key_values, log)  # noqa: E501
        self.assertEqual(len(matched_profiles), 0)

    def test_empty_profiles(self):
        profiles = []
        key_values = {
            "host": "houdini",
        }
        matched_profiles = profiles_filtering.get_matching_profiles(profiles, key_values, log)  # noqa: E501
        self.assertEqual(len(matched_profiles), 0)

    def test_single_match(self):
        """
        basic test
        - multiple profiles
        - a single clear winner

        """
        profiles = [
            {"host": "maya", "task": "modeling"},
            {"host": "maya", "task": "rigging"},     # match
            {"host": "maya", "task": "animation"},
        ]
        key_values = {
            "host": "maya",
            "task": "rigging",
        }
        matched_profiles = profiles_filtering.get_matching_profiles(profiles, key_values, log)  # noqa: E501
        self.assertEqual(len(matched_profiles), 1)

        matched_profile = matched_profiles[0]
        self.assertEqual(matched_profile["host"], "maya")
        self.assertEqual(matched_profile["task"], "rigging")

    def test_multiple_matches(self):
        """
        test with multiple matches
        - multiple profiles
        - multiple matches

        """
        profiles = [
            {"host": "maya", "task": "modeling"},
            {"host": "maya", "task": "rigging"},
            {"host": "maya", "task": "animation"},
            {"host": "houdini", "task": "fx"},      # match
            {"host": "houdini", "task": "render"},  # match
            {"host": "nuke", "task": "comp"},
        ]
        key_values = {
            "host": "houdini",
        }

        matched_profiles = profiles_filtering.get_matching_profiles(profiles, key_values, log)  # noqa: E501

        self.assertEqual(len(matched_profiles), 2)
        tasks = [profile["task"] for profile in matched_profiles]
        tasks = sorted(tasks)
        self.assertEqual(tasks, ["fx", "render"])

    def test_multiple_matches_with_wildcard(self):
        """
        test with multiple matches
        - multiple profiles
        - multiple matches

        """
        profiles = [
            {"host": "maya", "task": "modeling"},
            {"host": "maya", "task": "rigging"},
            {"host": "maya", "task": "animation"},
            {"host": "*", "task": "modeling"},      # match with wildcard
            {"host": "houdini", "task": "fx"},      # match
            {"host": "houdini", "task": "render"},  # match
            {"host": "nuke", "task": "comp"},
        ]
        key_values = {
            "host": "houdini",
        }

        matched_profiles = profiles_filtering.get_matching_profiles(
            profiles,
            key_values,
            log,
        )

        self.assertEqual(len(matched_profiles), 3)
        tasks = [profile["task"] for profile in matched_profiles]
        tasks = sorted(tasks)
        self.assertEqual(tasks, ["fx", "modeling", "render"])


class TestGetHighestScoreProfiles(unittest.TestCase):
    """Test `get_highest_score_profiles` function."""

    def test_single_match(self):
        profiles = [
            {"host": "nuke", "task": "modeling"},   # -1: host no match
            {"host": "*", "task": "modeling"},     # 1: task matches
            {"host": "maya", "task": "*"},         # 1: host matches
            {"host": "maya", "task": "modeling"},  # 2: both => winner
        ]
        key_values = {
            "host": "maya",
            "task": "modeling",
        }
        matched_profiles = profiles_filtering.get_highest_score_profiles(
            profiles,
            key_values,
            log,
        )
        self.assertEqual(len(matched_profiles), 1, matched_profiles)

        matched_profile = matched_profiles[0]
        expected_profile = {"host": "maya", "task": "modeling"}
        self.assertEqual(matched_profile, expected_profile)

    def test_exact_match_wins_over_wildcard_match(self):
        # both match on a and b, but exact match wins
        profiles = [
            {"a": "X", "b": "X", "d": 0},
            {"a": "X", "b": "*", "d": 1},
        ]
        key_values = {"a": "X", "b": "X"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(profiles, key_values, log)  # noqa: E501
        self.assertEqual(len(matched_profiles), 1, matched_profiles)
        self.assertEqual(matched_profiles[0]["d"], 0)

    def test_order_of_keys_matters(self):
        # both have 2 exact matches and one wildcard match but the first
        # profile wins because it has an exact match on an earlier key
        profiles = [
            {"a": "X", "b": "X", "c": "*", "d": 0},  # match on a and b => winner
            {"a": "X", "b": "*", "c": "X", "d": 1},  # match on a and c
        ]
        key_values = {"a": "X", "b": "X", "c": "X"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(profiles, key_values, log)  # noqa: E501
        self.assertEqual(len(matched_profiles), 1, matched_profiles)
        self.assertEqual(matched_profiles[0]["d"], 0)

    def test_multiple_matches(self):
        profiles = [
            {"a": "A", "b": "B", "c": "0", "d": 0},
            {"a": "B", "b": "A", "c": "2", "d": 1},
            {"a": "B", "b": "B", "c": "4", "d": 2},
            {"a": "B", "b": "B", "c": "8", "d": 3},
            {"a": "B", "b": "B", "c": "8", "d": 4},
            {"a": "B", "b": "B", "c": "8", "d": 5},
        ]

        key_values = {"a": "B"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(
            profiles, key_values, log
        )
        self.assertEqual(len(matched_profiles), 5, matched_profiles)

        # test without order
        key_values = {"b": "B"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(
            profiles, key_values, log
        )
        self.assertEqual(len(matched_profiles), 5, matched_profiles)

        key_values = {"a": "B", "b": "B"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(
            profiles, key_values, log
        )
        self.assertEqual(len(matched_profiles), 4, matched_profiles)

        key_values = {"a": "B", "b": "B", "c": "8"}
        matched_profiles = profiles_filtering.get_highest_score_profiles(
            profiles, key_values, log
        )
        self.assertEqual(len(matched_profiles), 3, matched_profiles)

    def test_empty_profiles_returns_empty_list(self):
        matched = profiles_filtering.get_highest_score_profiles(
            [], {"host": "maya"}, log
        )
        self.assertEqual(matched, [])

    def test_all_no_match_returns_empty_list(self):
        profiles = [
            {"host": "nuke"},
            {"host": "houdini"},
        ]
        key_values = {"host": "maya"}
        matched = profiles_filtering.get_highest_score_profiles(
            profiles, key_values, log
        )
        self.assertEqual(matched, [])


if __name__ == "__main__":
    unittest.main()
