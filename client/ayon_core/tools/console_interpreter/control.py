from __future__ import annotations

import os
import shutil
from typing import Optional

from ayon_core.lib import Logger, LocalPreferences, get_launcher_local_dir

from .abstract import (
    AbstractInterpreterController,
    TabItem,
    InterpreterConfig,
)


class InterpreterController(AbstractInterpreterController):
    def __init__(self, name: Optional[str] = None) -> None:
        if name is None:
            name = "python_interpreter_tool"
        self._preferences = LocalPreferences(name)
        self._copy_previous_registry()

    def get_config(self) -> InterpreterConfig:
        width = None
        height = None
        splitter_sizes = []
        tabs = []
        try:
            width = self._preferences.get_item("width")
            height = self._preferences.get_item("height")

        except (ValueError, KeyError):
            pass

        try:
            splitter_sizes = self._preferences.get_item("splitter_sizes")
        except (ValueError, KeyError):
            pass

        try:
            tab_defs = self._preferences.get_item("tabs") or []
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
        self._preferences.set_item("width", width)
        self._preferences.set_item("height", height)
        self._preferences.set_item("splitter_sizes", splitter_sizes)
        self._preferences.set_item("tabs", tabs)

    def _copy_previous_registry(self) -> None:
        """Use the registry of previous versions of the tool.

        It was in the root of the launcher local directory. It is copied
        and not moved, older versions of core in other bundles use it.
        """
        filepath = self._preferences.filepath
        previous_filepath = get_launcher_local_dir(
            f"{self._preferences.name}.json"
        )
        if (
            os.path.exists(filepath)
            or not os.path.exists(previous_filepath)
        ):
            return
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            shutil.copyfile(previous_filepath, filepath)
        except OSError:
            Logger.get_logger(self.__class__.__name__).warning(
                "Failed to copy previous registry '%s'.",
                previous_filepath,
                exc_info=True,
            )
