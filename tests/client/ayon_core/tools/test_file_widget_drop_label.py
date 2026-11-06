"""Tests for the label of the empty file input."""

from __future__ import annotations

import pytest

from ayon_core.lib import FileDef
from ayon_core.tools.attribute_defs import create_widget_for_attr_def


@pytest.mark.unit
@pytest.mark.parametrize(
    "kwargs",
    [
        {"folders": True, "extensions": []},
        {"folders": False, "extensions": [".exr"]},
    ],
)
def test_drop_label_does_not_hint_files_or_folders(qtbot, kwargs) -> None:
    widget = create_widget_for_attr_def(FileDef("path", **kwargs))
    qtbot.addWidget(widget)

    label = widget._input_widget._empty_widget._drop_label_widget
    assert label.text() == "Drag & Drop here or"
