"""Legacy template keys are converted by server settings validators.

Requires 'ayon_server' (AYON backend environment), skipped otherwise.
"""
from __future__ import annotations

import copy

import pytest

pytest.importorskip("ayon_server")

# Addon must be imported before 'ayon_server.settings.overrides'
#   to avoid circular imports in 'ayon_server'
from server.settings import CoreSettings, DEFAULT_VALUES  # noqa: E402
from server.settings.publish_plugins import (  # noqa: E402
    IntegrateProductGroupProfile,
)
from server.settings.tools import ProductNameProfile  # noqa: E402
from ayon_server.settings.overrides import apply_overrides  # noqa: E402

LEGACY_TEMPLATE = "{product[type]}{Task[name]}{Variant}<_{AOV}>"
CONVERTED_TEMPLATE = (
    "{product[type]}{task[name]:upperfirst}{variant:upperfirst}"
    "<_{aov:upper}>"
)


@pytest.mark.parametrize(
    "model_cls", [ProductNameProfile, IntegrateProductGroupProfile]
)
@pytest.mark.parametrize(
    "template, expected",
    [
        (LEGACY_TEMPLATE, CONVERTED_TEMPLATE),
        (CONVERTED_TEMPLATE, CONVERTED_TEMPLATE),
        ("{product[type]}{variant}", "{product[type]}{variant}"),
        ("{folder[name]:pascal}_v{version:0>3}", None),
    ],
)
def test_profile_template(model_cls, template, expected):
    if expected is None:
        expected = template
    assert model_cls(template=template).template == expected


def test_default_values_are_converted():
    """Defaults do not contain legacy keys."""
    settings = CoreSettings(**DEFAULT_VALUES)
    profiles = settings.tools.creator.product_name_profiles
    for profile, src_profile in zip(
        profiles,
        DEFAULT_VALUES["tools"]["creator"]["product_name_profiles"]
    ):
        assert profile.template == src_profile["template"]


def test_overrides_are_converted():
    """Legacy templates stored in overrides are converted on load."""
    defaults = CoreSettings(**DEFAULT_VALUES)
    profile = copy.deepcopy(
        DEFAULT_VALUES["tools"]["creator"]["product_name_profiles"][0]
    )
    profile["template"] = LEGACY_TEMPLATE
    overrides = {
        "tools": {"creator": {"product_name_profiles": [profile]}},
        "publish": {
            "IntegrateProductGroup": {
                "product_grouping_profiles": [{
                    "product_types": [],
                    "hosts": [],
                    "task_types": [],
                    "tasks": [],
                    "template": "{PRODUCT[TYPE]}_{Task}",
                }]
            }
        },
    }
    settings = apply_overrides(defaults, overrides)

    profiles = settings.tools.creator.product_name_profiles
    assert [profile.template for profile in profiles] == [CONVERTED_TEMPLATE]

    group_profiles = (
        settings.publish.IntegrateProductGroup.product_grouping_profiles
    )
    assert [profile.template for profile in group_profiles] == [
        "{product[type]:upper}_{task:upperfirst}"
    ]
