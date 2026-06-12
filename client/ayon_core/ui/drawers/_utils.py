"""Shared utilities used by AYONStyle drawer modules."""

from __future__ import annotations

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
    try:
        return enum_to_str._cache[cachekey]  # type: ignore
    except AttributeError:
        enum_to_str._cache = {}  # type: ignore
    except KeyError:
        pass

    try:
        enum_to_str._cache[cachekey] = enum.valueToKey(  # type: ignore
            enum_value
        )
    except AttributeError:
        meta_object = QStyle.staticMetaObject  # type: ignore
        enum_index = meta_object.indexOfEnumerator(enum.__name__)
        meta_enum = meta_object.enumerator(enum_index)
        enum_to_str._cache[cachekey] = (  # type: ignore
            f"{meta_enum.valueToKey(enum_value)}-{widget}"
        )

    return enum_to_str._cache[cachekey]  # type: ignore


def style_font(style: dict, w: QWidget | None) -> QFont:
    """Create a QFont from a style dictionary.

    Args:
        style: A dict with font-family, font-size, font-weight keys.
        w: Optional widget (unused, kept for API consistency).

    Returns:
        Configured QFont instance.
    """
    import os
    import platform

    font = QFont()
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setFamily(style["font-family"])
    env_val = os.environ.get("AYON_CORE_UI_FONT_OS")
    os_name = env_val.lower() if env_val else platform.system().lower()
    pt_size = style.get(f"font-size-{os_name}", style["font-size"])
    font.setPointSizeF(pt_size)
    font.setWeight(QFont.Weight(style["font-weight"]))
    return font
