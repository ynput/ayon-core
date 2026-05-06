"""Tray UI package.

``main`` is loaded lazily so importing sibling modules (e.g.
``tray_menu_icons``) does not execute ``tray.py`` (and aiohttp) at import
time.
"""

from __future__ import annotations

__all__ = ("main",)


def __getattr__(name: str):
    if name == "main":
        from .tray import main as tray_main

        return tray_main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
