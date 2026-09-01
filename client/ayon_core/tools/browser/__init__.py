from __future__ import annotations

from typing import TYPE_CHECKING

from .control import BrowserController, LoaderController

if TYPE_CHECKING:
    from .ui import BrowserWindow, LoaderWindow


__all__ = (
    "BrowserWindow",
    "BrowserController",
    "LoaderController",
    "LoaderWindow",
)


def __getattr__(name: str):
    if name in {"BrowserWindow", "LoaderWindow"}:
        from .ui import BrowserWindow, LoaderWindow

        return {
            "BrowserWindow": BrowserWindow,
            "LoaderWindow": LoaderWindow,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
