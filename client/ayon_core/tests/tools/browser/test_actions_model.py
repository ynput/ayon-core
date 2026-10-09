"""Tests for the loader action items of the Browser actions model."""

from __future__ import annotations

import sys
import types
from unittest.mock import Mock

import pytest

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from ayon_core.tools.browser.abstract import ActionItem, LoadersGrouping
from ayon_core.tools.browser.models import actions as actions_module
from ayon_core.tools.browser.models.actions import (
    LOADER_PLUGIN_ID,
    LoaderActionsModel,
)
from ayon_core.tools.browser.ui.actions_utils import _get_group_key


class _ImageLoader:
    label = "Load image"
    order = 0
    icon = None

    @classmethod
    def get_options(cls, contexts):
        return []


class _ReferenceLoader:
    label = "Reference"
    order = -10
    icon = None

    @classmethod
    def get_options(cls, contexts):
        return []


class _OtherImageLoader:
    """Different loader with the label of the image loader."""

    label = "Load image"
    order = 20
    icon = None

    @classmethod
    def get_options(cls, contexts):
        return []


class _ProductLoader:
    label = "Delete old versions"
    order = 35
    icon = None

    @classmethod
    def get_options(cls, contexts):
        return []


def _repre_context(repre_id: str, repre_name: str) -> dict:
    return {"representation": {"id": repre_id, "name": repre_name}}


@pytest.fixture
def model(monkeypatch):
    model = LoaderActionsModel(Mock())
    monkeypatch.setattr(
        model,
        "_get_loaders",
        lambda project_name: (
            [_ProductLoader],
            [_ImageLoader, _ReferenceLoader],
        ),
    )
    # The reference loader is only compatible with the 'exr' representation
    monkeypatch.setattr(
        actions_module,
        "filter_repre_contexts_by_loader",
        lambda repre_contexts, loader: [
            repre_context
            for repre_context in repre_contexts
            if loader is not _ReferenceLoader
            or repre_context["representation"]["name"] == "exr"
        ],
    )
    return model


def _get_items(model, *args):
    version_context_by_id = {
        "version1": {
            "product": {"id": "product1"},
            "folder": {"id": "folder1"},
        }
    }
    repre_context_by_id = {
        "repre1": _repre_context("repre1", "exr"),
        "repre2": _repre_context("repre2", "png"),
    }
    return model._get_action_items_for_contexts(
        "demo", version_context_by_id, repre_context_by_id, *args
    )


def _labels(items: list[ActionItem]) -> list[tuple[str, str]]:
    return sorted((item.group_label or "", item.label) for item in items)


def test_repre_loader_items_are_ungrouped_by_default(model):
    expected_labels = [
        ("", "Delete old versions"),
        ("", "Load image (exr)"),
        ("", "Load image (png)"),
        ("", "Reference (exr)"),
    ]

    assert _labels(_get_items(model)) == expected_labels
    assert (
        _labels(_get_items(model, LoadersGrouping.UNGROUPED))
        == expected_labels
    )


def test_repre_loader_items_grouped_by_loader(model):
    items = _get_items(model, LoadersGrouping.GROUPED)

    # Loaders that load a whole version have no representation to list
    assert _labels(items) == [
        ("", "Delete old versions"),
        ("Load image", "exr"),
        ("Load image", "png"),
        ("Reference", "exr"),
    ]


def test_repre_loader_items_grouped_if_multiple(model):
    items = _get_items(model, LoadersGrouping.GROUPED_IF_MULTIPLE)

    # The reference loader matches a single representation
    assert _labels(items) == [
        ("", "Delete old versions"),
        ("", "Reference (exr)"),
        ("Load image", "exr"),
        ("Load image", "png"),
    ]


@pytest.mark.parametrize("loaders_grouping", list(LoadersGrouping))
def test_grouping_does_not_change_what_is_loaded(model, loaders_grouping):
    def _trigger_data(items):
        return sorted(
            (
                item.identifier,
                item.data["loader"],
                item.data["entity_type"],
                sorted(item.data["entity_ids"]),
                item.order,
            )
            for item in items
        )

    ungrouped_items = _get_items(model)
    items = _get_items(model, loaders_grouping)

    assert _trigger_data(items) == _trigger_data(ungrouped_items)
    assert {item.identifier for item in items} == {LOADER_PLUGIN_ID}


def test_loaders_with_same_label_get_their_own_submenu(model, monkeypatch):
    monkeypatch.setattr(
        model,
        "_get_loaders",
        lambda project_name: ([], [_ImageLoader, _OtherImageLoader]),
    )

    items = _get_items(model, LoadersGrouping.GROUPED)

    assert {item.group_label for item in items} == {"Load image"}
    orders_by_group_key = {}
    for item in items:
        orders_by_group_key.setdefault(_get_group_key(item), set()).add(
            item.order
        )
    # A submenu per loader, each at the position of its own order
    assert sorted(orders_by_group_key.values(), key=min) == [{0}, {20}]


def test_loader_actions_with_same_group_label_share_a_submenu():
    items = [
        ActionItem(
            f"action.{idx}",
            label=f"Action {idx}",
            group_label="Group",
            icon=None,
            tooltip=None,
            order=idx,
            data={"loader": idx},
            options=None,
        )
        for idx in range(2)
    ]

    assert len({_get_group_key(item) for item in items}) == 1
