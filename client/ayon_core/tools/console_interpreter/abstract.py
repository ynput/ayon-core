from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class TabItem:
    name: str
    code: str


@dataclass
class InterpreterConfig:
    width: Optional[int]
    height: Optional[int]
    splitter_sizes: List[int] = field(default_factory=list)
    tabs: List[TabItem] = field(default_factory=list)


class AbstractInterpreterController(ABC):
    @abstractmethod
    def get_config(self) -> InterpreterConfig:
        pass

    @abstractmethod
    def save_config(
        self,
        width: int,
        height: int,
        splitter_sizes: List[int],
        tabs: List[Dict[str, str]],
    ):
        pass
