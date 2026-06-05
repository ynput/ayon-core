from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ListType = Literal["generic", "review-session"]


@dataclass
class ListConfigFolder:
    label: str
    scope: list[str] = field(default_factory=list)
    color: str | None = None
    icon: str | None = None


@dataclass
class ListConfig:
    """Define a list."""
    name: str
    list_type: ListType = "generic"
    list_folders: list[ListConfigFolder] = field(default_factory=list)
