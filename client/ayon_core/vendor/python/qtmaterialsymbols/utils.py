import json
import copy
from typing import Dict, Union

from qtpy import QtWidgets, QtGui, QtCore

from .exceptions import ApplicationNotRunning, FontError
from .resources import get_mapping_filepath, get_font_filepath


class _Cache:
    mapping = None
    font_id = None
    font_name = None


def _load_font():
    if QtWidgets.QApplication.instance() is None:
        raise ApplicationNotRunning("No QApplication instance found.")

    if _Cache.font_id is not None:
        loaded_font_families = QtGui.QFontDatabase.applicationFontFamilies(
            _Cache.font_id
        )
        if loaded_font_families:
            return

    filepath = get_font_filepath()
    with open(filepath, "rb") as font_data:
        font_id = QtGui.QFontDatabase.addApplicationFontFromData(
            QtCore.QByteArray(font_data.read())
        )

    loaded_font_families = QtGui.QFontDatabase.applicationFontFamilies(
        font_id
    )
    if not loaded_font_families:
        raise FontError("Failed to load font.")

    _Cache.font_id = font_id
    _Cache.font_name = loaded_font_families[0]


def _load_mapping():
    if _Cache.mapping is not None:
        return

    filepath = get_mapping_filepath()
    with open(filepath, "r") as stream:
        mapping = json.load(stream)
    _Cache.mapping = {
        key: chr(value)
        for key, value in mapping.items()
    }


def _get_font_name():
    _load_font()
    return _Cache.font_name


def get_icon_name_char(icon_name: str) -> Union[int, None]:
    _load_mapping()
    return _Cache.mapping.get(icon_name, None)


def get_char_mapping() -> Dict[str, int]:
    _load_mapping()
    return copy.deepcopy(_Cache.mapping)
