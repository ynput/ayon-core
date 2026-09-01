from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

from qtpy import QtCore, QtWidgets

from ayon_core.tools.browser.ui._browser_slicer import BrowserSlicer


def test_select_folder_chain_expands_selects_and_scrolls():
    parent_index = Mock()
    parent_index.isValid.return_value = True
    folder_index = Mock()
    folder_index.isValid.return_value = True
    selection_model = Mock()
    tree_view = Mock()
    tree_view.selectionModel.return_value = selection_model
    indexes = {
        "parent-id": parent_index,
        "folder-id": folder_index,
    }
    slicer = SimpleNamespace(
        _tree_view=tree_view,
        _get_view_index_by_id=indexes.__getitem__,
        _folder_selection_chain=["parent-id", "folder-id"],
        _folder_selection_attempt=0,
        _folder_selection_timer=Mock(),
    )

    BrowserSlicer._select_folder_chain(
        slicer,
        ["parent-id", "folder-id"],
        0,
    )

    tree_view.expand.assert_called_once_with(parent_index)
    selection_model.select.assert_called_once_with(
        folder_index,
        QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect,
    )
    tree_view.setCurrentIndex.assert_called_once_with(folder_index)
    tree_view.scrollTo.assert_called_once_with(
        folder_index,
        QtWidgets.QAbstractItemView.ScrollHint.PositionAtCenter,
    )
    assert slicer._folder_selection_chain == []
