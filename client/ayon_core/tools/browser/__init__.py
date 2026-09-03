from __future__ import annotations

from typing import TYPE_CHECKING

from .control import BrowserController

if TYPE_CHECKING:
    from .ui import BrowserWindow


__all__ = (
    "BrowserWindow",
    "BrowserController",
)


def __getattr__(name: str):
    if name in {"BrowserWindow"}:
        from .ui import BrowserWindow

        return {
            "BrowserWindow": BrowserWindow,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
