"""Tests for the optional ``drop_label`` of ``FileDef``."""

from __future__ import annotations

import pytest

from ayon_core.lib import FileDef
from ayon_core.tools.attribute_defs import create_widget_for_attr_def

CUSTOM_LABEL = "Drop files or folders here or"


def _drop_label_text(widget) -> str:
    # FileAttrWidget -> FilesWidget -> DropEmpty -> drop label
    return widget._input_widget._empty_widget._drop_label_widget.text()


@pytest.mark.unit
def test_file_def_drop_label_default_and_serialized() -> None:
    assert FileDef("path").drop_label is None

    attr_def = FileDef("path", drop_label=CUSTOM_LABEL)
    assert attr_def.drop_label == CUSTOM_LABEL
    assert attr_def.serialize()["drop_label"] == CUSTOM_LABEL


@pytest.mark.unit
def test_file_widget_keeps_default_drop_label(qtbot) -> None:
    widget = create_widget_for_attr_def(FileDef("path"))
    qtbot.addWidget(widget)

    assert _drop_label_text(widget) == "Drop files here or"


@pytest.mark.unit
def test_file_widget_shows_custom_drop_label(qtbot) -> None:
    widget = create_widget_for_attr_def(
        FileDef("path", drop_label=CUSTOM_LABEL)
    )
    qtbot.addWidget(widget)

    assert _drop_label_text(widget) == CUSTOM_LABEL
