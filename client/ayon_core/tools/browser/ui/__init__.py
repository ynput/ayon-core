from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .window import BrowserWindow, LoaderWindow


__all__ = (
    "BrowserWindow",
    "LoaderWindow",
)


def __getattr__(name: str):
    if name in {"BrowserWindow", "LoaderWindow"}:
        from .window import BrowserWindow, LoaderWindow

        return {
            "BrowserWindow": BrowserWindow,
            "LoaderWindow": LoaderWindow,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
