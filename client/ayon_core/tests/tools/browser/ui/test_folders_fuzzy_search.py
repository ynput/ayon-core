"""Fuzzy name filter of the shared FoldersProxyModel (path + label path)."""

from __future__ import annotations

import sys
import types

if "qargparse" not in sys.modules:
    sys.modules["qargparse"] = types.ModuleType("qargparse")

from qtpy import QtCore, QtGui

from ayon_core.tools.utils.folders_widget import (
    FOLDER_ID_ROLE,
    FOLDER_PATH_FILTER_ROLE,
    FoldersProxyModel,
)


def _build_proxy() -> FoldersProxyModel:
    model = QtGui.QStandardItemModel()
    assets = QtGui.QStandardItem("Assets")
    hero = QtGui.QStandardItem("Hero")
    shots = QtGui.QStandardItem("Shots")
    for item, folder_id, path_filter in (
        (assets, "assets", "/assets /assets"),
        (hero, "hero", "/assets/char/hero /assets/characters/hero"),
        (shots, "shots", "/shots /shots"),
    ):
        item.setData(folder_id, FOLDER_ID_ROLE)
        item.setData(path_filter, FOLDER_PATH_FILTER_ROLE)
    assets.appendRow(hero)
    model.appendRow(assets)
    model.appendRow(shots)
    proxy = FoldersProxyModel()
    proxy.setSourceModel(model)
    proxy._test_model = model
    return proxy


def _visible(proxy, parent=QtCore.QModelIndex()):
    labels = set()
    for row in range(proxy.rowCount(parent)):
        index = proxy.index(row, 0, parent)
        labels.add(index.data())
        labels |= _visible(proxy, index)
    return labels


def test_matches_label_path_not_only_name_path():
    proxy = _build_proxy()
    proxy.set_name_filter("characters")
    assert _visible(proxy) == {"Assets", "Hero"}


def test_all_terms_must_match_case_insensitive():
    proxy = _build_proxy()
    proxy.set_name_filter("ASSETS hero")
    assert _visible(proxy) == {"Assets", "Hero"}
    proxy.set_name_filter("shots hero")
    assert _visible(proxy) == set()


def test_empty_filter_shows_everything():
    proxy = _build_proxy()
    proxy.set_name_filter("hero")
    proxy.set_name_filter("")
    assert _visible(proxy) == {"Assets", "Hero", "Shots"}
