from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ListType = Literal["generic", "review-session"]


@dataclass
class ListConfig:
    """Define a list."""
    name: str
    parent_folders: list[str] = field(default_factory=list)
    list_type: ListType = "generic"
