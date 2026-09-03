from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .window import BrowserWindow


__all__ = (
    "BrowserWindow",
)


def __getattr__(name: str):
    if name in {"BrowserWindow"}:
        from .window import BrowserWindow

        return {
            "BrowserWindow": BrowserWindow,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
