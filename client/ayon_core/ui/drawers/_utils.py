"""Shared utilities used by AYONStyle drawer modules."""

from __future__ import annotations

import os
import platform

from qtpy.QtGui import QFont
from qtpy.QtWidgets import QStyle, QWidget

try:
    from qtmaterialsymbols import get_icon  # type: ignore
except ImportError:
    from ..vendor.qtmaterialsymbols import get_icon  # noqa: F401


def do_nothing(*args, **kwargs):
    """No-op stub used to suppress default Qt drawing for certain elements."""


def enum_to_str(enum, enum_value: int, widget: str) -> str:
    """Convert enum value to string representation."""
    cachekey = f"{enum.__name__}_{enum_value}_{widget}"
    if not hasattr(enum_to_str, "_cache"):
        enum_to_str._cache = {}  # type: ignore
    value: str | None = enum_to_str._cache.get(cachekey)
    if value is not None:
        return value

    if hasattr(enum, "valueToKey"):
        value = enum.valueToKey(enum_value)
    else:
        meta_object = QStyle.staticMetaObject
        enum_index = meta_object.indexOfEnumerator(enum.__name__)
        meta_enum = meta_object.enumerator(enum_index)
        value = f"{meta_enum.valueToKey(enum_value)}-{widget}"

    enum_to_str._cache[cachekey] = value

    return value


def style_font(style: dict, w: QWidget | None) -> QFont:
    """Create a QFont from a style dictionary.

    Args:
        style: A dict with font-family, font-size, font-weight keys.
        w: Optional widget (unused, kept for API consistency).

    Returns:
        Configured QFont instance.

    """
    font = QFont()
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setFamily(style["font-family"])
    os_name = os.environ.get("AYON_CORE_UI_FONT_OS")
    if not os_name:
        os_name = platform.system()
    pt_size = style.get(f"font-size-{os_name.lower()}", style["font-size"])
    font.setPointSizeF(pt_size)
    font.setWeight(QFont.Weight(style["font-weight"]))
    return font
