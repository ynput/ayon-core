from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ListType = Literal["generic", "review-session"]


@dataclass
class ListConfig:
    """Define a list."""
    name: str
    list_type: ListType = "generic"
    list_folders: list[str] = field(default_factory=list)
