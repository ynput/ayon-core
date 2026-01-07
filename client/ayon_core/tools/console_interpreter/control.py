from __future__ import annotations
from typing import Optional

from ayon_core.lib import JSONSettingRegistry
from ayon_core.lib.local_settings import get_launcher_local_dir

from .abstract import (
    AbstractInterpreterController,
    TabItem,
    InterpreterConfig,
)


class InterpreterController(AbstractInterpreterController):
    def __init__(self, name: Optional[str] = None) -> None:
        if name is None:
            name = "python_interpreter_tool"
        self._registry = JSONSettingRegistry(
            name,
            get_launcher_local_dir(),
        )

    def get_config(self) -> InterpreterConfig:
        width = None
        height = None
        splitter_sizes = []
        tabs = []
        try:
            width = self._registry.get_item("width")
            height = self._registry.get_item("height")

        except (ValueError, KeyError):
            pass

        try:
            splitter_sizes = self._registry.get_item("splitter_sizes")
        except (ValueError, KeyError):
            pass

        try:
            tab_defs = self._registry.get_item("tabs") or []
            for tab_def in tab_defs:
                tab_name = tab_def.get("name")
                if not tab_name:
                    continue
                code = tab_def.get("code") or ""
                tabs.append(TabItem(tab_name, code))

        except (ValueError, KeyError):
            pass

        return InterpreterConfig(
            width, height, splitter_sizes, tabs
        )

    def save_config(
        self,
        width: int,
        height: int,
        splitter_sizes: list[int],
        tabs: list[dict[str, str]],
    ) -> None:
        self._registry.set_item("width", width)
        self._registry.set_item("height", height)
        self._registry.set_item("splitter_sizes", splitter_sizes)
        self._registry.set_item("tabs", tabs)
