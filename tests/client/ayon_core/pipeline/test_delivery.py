"""Tests for delivery recipes and template resolution."""
from __future__ import annotations

from typing import Any

import pytest

from ayon_core.pipeline.delivery import (
    DeliveryOverrideInfo,
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
    match = resolve_delivery_template(
        [], "client", "exr", "render", extension="exr"
    )

    assert match.template_name == "client"
    assert match.override_info is None


def test_extension_match_overrides_template():
    overrides = [
        _override("client_cdl", extensions=["ccc", "cdl"]),
        _override("client_plates", extensions=["exr"]),
    ]

    match = resolve_delivery_template(
        overrides, "client", "plate", "render", extension=".EXR"
    )

    assert match.template_name == "client_plates"
    assert match.override_info == DeliveryOverrideInfo(
        index=1,
        representation_names=[],
        extensions=["exr"],
        product_base_types=[],
    )


def test_override_to_default_template():
    overrides = [_override("client", extensions=["exr"])]

    match = resolve_delivery_template(
        overrides, "client", "exr", "render", extension="exr"
    )

    assert match.template_name == "client"
    assert match.override_info.index == 0
