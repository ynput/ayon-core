from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TabItem:
    name: str
    code: str


@dataclass
class InterpreterConfig:
    width: Optional[int]
    height: Optional[int]
    splitter_sizes: list[int] = field(default_factory=list)
    tabs: list[TabItem] = field(default_factory=list)


class AbstractInterpreterController(ABC):
    @abstractmethod
    def get_config(self) -> InterpreterConfig:
        pass

    @abstractmethod
    def save_config(
        self,
        width: int,
        height: int,
        splitter_sizes: list[int],
        tabs: list[dict[str, str]],
    ) -> None:
        pass
