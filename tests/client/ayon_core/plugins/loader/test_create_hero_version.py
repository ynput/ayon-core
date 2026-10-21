from __future__ import annotations

from ayon_core.plugins.loader.create_hero_version import (
    _get_representation_template_data,
)


def test_representation_template_data_keeps_output_for_same_extensions():
    template_data = {"ext": "source", "product": {"name": "image"}}
    first_representation = {"context": {"ext": "png", "output": "png"}}
    second_representation = {
        "context": {"ext": "png", "output": "png_png"}
    }

    first_data = _get_representation_template_data(
        template_data, first_representation
    )
    second_data = _get_representation_template_data(
        template_data, second_representation
    )

    assert first_data["ext"] == "png"
    assert first_data["output"] == "png"
    assert second_data["ext"] == "png"
    assert second_data["output"] == "png_png"
    assert "output" not in template_data
