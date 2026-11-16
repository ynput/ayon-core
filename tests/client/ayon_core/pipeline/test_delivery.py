"""Tests for delivery recipes and template resolution."""
from __future__ import annotations

from typing import Any

import pytest

from ayon_core.pipeline.delivery import (
    DeliveryRecipe,
    filter_delivery_template_names,
    get_delivery_recipes,
    resolve_delivery_template,
)

TEMPLATE_NAMES = ["client", "client_cdl", "client_plates", "internal"]


@pytest.mark.parametrize(
    "delivery_settings, expected",
    [
        # Empty deny list shows all templates
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


def test_get_delivery_recipes():
    project_settings = {"core": {"tools": {"delivery": {"recipes": [{
        "name": "Client delivery",
        "template_name": "client",
        "overrides": [_override("client_plates", extensions=["exr"])],
    }]}}}}

    recipes = get_delivery_recipes(project_settings)

    assert recipes == [
        DeliveryRecipe(
            name="Client delivery",
            template_name="client",
            overrides=[_override("client_plates", extensions=["exr"])],
        )
    ]


def _override(template_name: str, **filters: list[str]) -> dict[str, Any]:
    override = {
        "representation_names": [],
        "extensions": [],
        "product_base_types": [],
        "template_name": template_name,
    }
    override.update(filters)
    return override


def test_no_overrides_uses_default_template():
    match = resolve_delivery_template([], "client", "exr", extension="exr")

    assert match.template_name == "client"
    assert match.override is None
    assert match.override_index is None
    assert not match.is_override


def test_extension_match_overrides_template():
    overrides = [
        _override("client_cdl", extensions=["ccc", "cdl"]),
        _override("client_plates", extensions=["exr"]),
    ]

    match = resolve_delivery_template(
        overrides, "client", "plate", extension=".EXR"
    )

    assert match.template_name == "client_plates"
    assert match.default_template_name == "client"
    assert match.override_index == 1
    assert match.override is overrides[1]
    assert match.is_override


def test_unmatched_representation_uses_default_template():
    overrides = [_override("client_plates", extensions=["exr"])]

    match = resolve_delivery_template(
        overrides, "client", "h264", extension="mov"
    )

    assert match.template_name == "client"
    assert not match.is_override


def test_most_specific_override_wins():
    overrides = [
        _override("client_plates", extensions=["exr"]),
        _override(
            "client_renders",
            extensions=["exr"],
            product_base_types=["render"],
        ),
    ]

    render = resolve_delivery_template(
        overrides, "client", "exr", extension="exr", product_base_type="render"
    )
    plate = resolve_delivery_template(
        overrides, "client", "exr", extension="exr", product_base_type="plate"
    )

    assert render.template_name == "client_renders"
    assert plate.template_name == "client_plates"


def test_override_to_default_template_is_not_override():
    overrides = [
        _override("client_plates", extensions=["exr"]),
        _override(
            "client", representation_names=["exr_review"], extensions=["exr"]
        ),
    ]

    match = resolve_delivery_template(
        overrides, "client", "exr_review", extension="exr"
    )

    assert match.template_name == "client"
    assert match.override_index == 1
    assert not match.is_override


@pytest.mark.parametrize(
    "repre_name, expected",
    [
        ("camera_exr", "client_plates"),
        ("exr", "client"),
    ],
)
def test_representation_name_regex(repre_name: str, expected: str):
    overrides = [
        _override("client_plates", representation_names=[".*_exr"])
    ]

    match = resolve_delivery_template(overrides, "client", repre_name)

    assert match.template_name == expected


def test_product_base_type_filter_requires_value():
    overrides = [
        _override("client_renders", product_base_types=["render"])
    ]

    match = resolve_delivery_template(
        overrides, "client", "exr", extension="exr", product_base_type=None
    )

    assert match.template_name == "client"


def test_tie_prefers_representation_name_over_extension():
    overrides = [
        _override("client_plates", extensions=["exr"]),
        _override("client_review", representation_names=["exr_review"]),
    ]

    match = resolve_delivery_template(
        overrides, "client", "exr_review", extension="exr"
    )

    assert match.template_name == "client_review"
