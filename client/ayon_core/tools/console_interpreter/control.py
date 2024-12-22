from typing import List, Dict

from ayon_core.lib import JSONSettingRegistry
from ayon_core.lib.local_settings import get_launcher_local_dir

from .abstract import (
    AbstractInterpreterController,
    TabItem,
    InterpreterConfig,
)


class InterpreterController(AbstractInterpreterController):
    def __init__(self):
        self._registry = JSONSettingRegistry(
            "python_interpreter_tool",
            get_launcher_local_dir(),
        )

    def get_config(self):
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
        splitter_sizes: List[int],
        tabs: List[Dict[str, str]],
    ):
        self._registry.set_item("width", width)
        self._registry.set_item("height", height)
        self._registry.set_item("splitter_sizes", splitter_sizes)
        self._registry.set_item("tabs", tabs)
