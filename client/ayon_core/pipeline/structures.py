from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ListType = Literal["generic", "review-session"]


@dataclass
class ListConfig:
    """Define a list."""
    name: str
    parent_folders: list[str] | None = None
    list_type: ListType = "generic"
