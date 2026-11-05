"""Tests for natural sorting of names in the workfiles tool."""

from __future__ import annotations

import functools
from types import SimpleNamespace

import pytest
from qtpy import QtCore, QtGui

from ayon_core.tools.workfiles.widgets import (
    files_widget_workarea,
    utils,
)

UNSORTED_NAMES = [
    "sh010_comp_v10.hip",
    "sh010_comp_v2.hip",
    "SH010_comp_v1.hip",
    "sh010_comp_v100.hip",
    "sh010_comp_v9.hip",
]
SORTED_NAMES = [
    "SH010_comp_v1.hip",
    "sh010_comp_v2.hip",
    "sh010_comp_v9.hip",
    "sh010_comp_v10.hip",
    "sh010_comp_v100.hip",
]


class _Controller:
    def register_event_callback(self, topic, callback) -> None:
        pass

    def set_selected_workfile_path(self, *args) -> None:
        pass

    def get_user_items_by_name(self):
        return {}

    def get_workarea_file_items(self, folder_id, task_name):
        return [
            SimpleNamespace(
                filepath=f"/work/{name}",
                rootless_path=f"{{root}}/{name}",
                available=True,
                updated_by=None,
                workfile_entity_id=name,
                # Order by date is different than order by name
                file_modified=1000.0 * idx,
            )
            for idx, name in enumerate(UNSORTED_NAMES, 1)
        ]


def _proxy_values(proxy_model, column: int = 0) -> list:
    return [
        proxy_model.index(row, column).data(QtCore.Qt.DisplayRole)
        for row in range(proxy_model.rowCount())
    ]


@pytest.mark.parametrize("pure_python", [False, True])
def test_names_are_sorted_naturally(qapp, monkeypatch, pure_python):
    if pure_python:
        # Qt build that does not support numeric mode of 'QCollator'
        monkeypatch.setattr(
            utils, "_get_natural_compare", lambda: utils._natural_compare
        )
    model = QtGui.QStandardItemModel()
    for name in UNSORTED_NAMES:
        model.appendRow(QtGui.QStandardItem(name))
    proxy_model = utils.NaturalSortProxyModel()
    proxy_model.setSourceModel(model)

    proxy_model.sort(0, QtCore.Qt.AscendingOrder)
    assert _proxy_values(proxy_model) == SORTED_NAMES

    proxy_model.sort(0, QtCore.Qt.DescendingOrder)
    assert _proxy_values(proxy_model) == SORTED_NAMES[::-1]


def test_pure_python_compare():
    assert utils._natural_compare("v2", "v10") < 0
    assert utils._natural_compare("v10", "v2") > 0
    assert utils._natural_compare("V2", "v2") == 0
    # Names starting with a number and with a text can be compared
    names = ["b1", "10", "a", "9b", "9a", ""]
    assert sorted(
        names, key=functools.cmp_to_key(utils._natural_compare)
    ) == ["", "9a", "9b", "10", "a", "b1"]


def test_workarea_files_sorting(qtbot):
    widget = files_widget_workarea.WorkAreaFilesWidget(_Controller(), None)
    qtbot.addWidget(widget)
    widget._model._on_task_changed({"folder_id": "f", "task_name": "comp"})
    proxy_model = widget._proxy_model

    widget._view.sortByColumn(0, QtCore.Qt.AscendingOrder)
    assert _proxy_values(proxy_model) == SORTED_NAMES

    # Other columns are still sorted by their values
    date_col = widget._model.date_modified_col
    widget._view.sortByColumn(date_col, QtCore.Qt.AscendingOrder)
    assert _proxy_values(proxy_model) == UNSORTED_NAMES
