"""Tests for delivery template profiles resolution."""
from __future__ import annotations

from typing import Any

import pytest

from ayon_core.pipeline.delivery import (
    filter_delivery_template_names,
    resolve_delivery_template,
)

TEMPLATE_NAMES = ["client", "client_cdl", "client_plates", "internal"]


@pytest.mark.parametrize(
    "delivery_settings, expected",
    [
        # Missing settings and empty deny list show all templates
        ({}, TEMPLATE_NAMES),
        (
            {"filter_type": "is_deny_list", "filter_templates": []},
            TEMPLATE_NAMES,
        ),
        (
            {
                "filter_type": "is_deny_list",
                "filter_templates": ["client_cdl", "client_plates"],
            },
            ["client", "internal"],
        ),
        (
            {
                "filter_type": "is_allow_list",
                "filter_templates": ["internal", "client"],
            },
            ["client", "internal"],
        ),
        ({"filter_type": "is_allow_list", "filter_templates": []}, []),
    ],
)
def test_filter_delivery_template_names(
    delivery_settings: dict[str, Any], expected: list[str]
):
    result = filter_delivery_template_names(
        TEMPLATE_NAMES, delivery_settings
    )

    assert result == expected


def _profile(template_name: str = "", **filters: list[str]) -> dict[str, Any]:
    profile = {
        "delivery_templates": [],
        "representation_names": [],
        "extensions": [],
        "product_base_types": [],
        "template_name": template_name,
    }
    profile.update(filters)
    return profile


def test_no_profiles_uses_picked_template():
    match = resolve_delivery_template([], "client", "exr", extension="exr")

    assert match.template_name == "client"
    assert match.profile is None
    assert match.profile_index is None
    assert not match.is_override


def test_extension_match_overrides_template():
    profiles = [
        _profile("client_cdl", extensions=["ccc", "cdl"]),
        _profile("client_plates", extensions=["exr"]),
    ]

    match = resolve_delivery_template(
        profiles, "client", "plate", extension=".EXR"
    )

    assert match.template_name == "client_plates"
    assert match.profile_index == 1
    assert match.profile is profiles[1]
    assert match.is_override


def test_unmatched_representation_uses_picked_template():
    profiles = [_profile("client_plates", extensions=["exr"])]

    match = resolve_delivery_template(
        profiles, "client", "h264", extension="mov"
    )

    assert match.template_name == "client"
    assert not match.is_override


def test_profile_limited_to_picked_templates():
    profiles = [
        _profile(
            "client_plates",
            delivery_templates=["client"],
            extensions=["exr"],
        )
    ]

    other = resolve_delivery_template(
        profiles, "internal", "exr", extension="exr"
    )
    client = resolve_delivery_template(
        profiles, "client", "exr", extension="exr"
    )

    assert other.template_name == "internal"
    assert client.template_name == "client_plates"


def test_most_specific_profile_wins():
    profiles = [
        _profile("client_plates", extensions=["exr"]),
        _profile(
            "client_renders",
            extensions=["exr"],
            product_base_types=["render"],
        ),
    ]

    render = resolve_delivery_template(
        profiles, "client", "exr", extension="exr", product_base_type="render"
    )
    plate = resolve_delivery_template(
        profiles, "client", "exr", extension="exr", product_base_type="plate"
    )

    assert render.template_name == "client_renders"
    assert plate.template_name == "client_plates"


def test_empty_template_name_keeps_picked_template():
    profiles = [
        _profile("client_plates", extensions=["exr"]),
        _profile(
            "", representation_names=["exr_review"], extensions=["exr"]
        ),
    ]

    match = resolve_delivery_template(
        profiles, "client", "exr_review", extension="exr"
    )

    assert match.template_name == "client"
    assert match.profile_index == 1
    assert not match.is_override


@pytest.mark.parametrize(
    "repre_name, expected",
    [
        ("camera_exr", "client_plates"),
        ("exr", "client"),
    ],
)
def test_representation_name_regex(repre_name: str, expected: str):
    profiles = [
        _profile("client_plates", representation_names=[".*_exr"])
    ]

    match = resolve_delivery_template(profiles, "client", repre_name)

    assert match.template_name == expected


def test_product_base_type_filter_requires_value():
    profiles = [_profile("client_renders", product_base_types=["render"])]

    match = resolve_delivery_template(
        profiles, "client", "exr", extension="exr", product_base_type=None
    )

    assert match.template_name == "client"
