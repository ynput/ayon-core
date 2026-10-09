"""Tests for 'get_publish_template_name_for_instance'."""
from __future__ import annotations

from typing import Any

import pyblish.api
import pytest

from ayon_core.pipeline.publish import (
    get_publish_template_name_for_instance,
)


def _profile(template_name: str, **filters: list[str]) -> dict[str, Any]:
    profile = {
        "host_names": [],
        "product_base_types": [],
        "task_names": [],
        "task_types": [],
        "template_name": template_name,
    }
    profile.update(filters)
    return profile


@pytest.fixture
def instance() -> pyblish.api.Instance:
    context = pyblish.api.Context()
    context.data.update({
        "projectName": "project",
        "hostName": "maya",
        "project_settings": {"core": {"tools": {"publish": {
            "template_name_profiles": [
                _profile("render", product_base_types=["render"]),
                _profile("animation", task_types=["Animation"]),
                _profile("modeling", task_types=["Modeling"]),
            ],
            "hero_template_name_profiles": [
                _profile("heroAnimation", task_types=["Animation"]),
            ],
        }}}},
    })
    instance = context.create_instance("modelMain")
    instance.data["productType"] = "model"
    return instance


def test_default_template(instance: pyblish.api.Instance) -> None:
    assert get_publish_template_name_for_instance(instance) == "default"
    assert (
        get_publish_template_name_for_instance(instance, hero=True)
        == "default"
    )


def test_product_base_type(instance: pyblish.api.Instance) -> None:
    # Product type is used only if product base type is not available
    instance.data["productType"] = "render"
    assert get_publish_template_name_for_instance(instance) == "render"

    instance.data["productBaseType"] = "model"
    assert get_publish_template_name_for_instance(instance) == "default"

    assert get_publish_template_name_for_instance(
        instance, product_base_type="render"
    ) == "render"


def test_task_from_anatomy_data(instance: pyblish.api.Instance) -> None:
    # Anatomy data are preferred over task entity
    instance.data["taskEntity"] = {"name": "model", "taskType": "Modeling"}
    instance.data["anatomyData"] = {
        "task": {"name": "anim", "type": "Animation", "short": "anim"}
    }
    assert get_publish_template_name_for_instance(instance) == "animation"
    assert (
        get_publish_template_name_for_instance(instance, hero=True)
        == "heroAnimation"
    )

    # Task is optional in anatomy data
    instance.data["anatomyData"] = {}
    assert get_publish_template_name_for_instance(instance) == "default"


def test_task_from_task_entity(instance: pyblish.api.Instance) -> None:
    instance.data["taskEntity"] = {"name": "model", "taskType": "Modeling"}
    assert get_publish_template_name_for_instance(instance) == "modeling"

    instance.data["taskEntity"] = None
    assert get_publish_template_name_for_instance(instance) == "default"
