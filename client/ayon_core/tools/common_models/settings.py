from __future__ import annotations

import copy
from typing import Literal

from ayon_core.settings import get_studio_settings, get_project_settings

TaskSortMode = Literal["name", "type"]


class SettingsModel:
    def __init__(self):
        self._settings = {}
        self._task_sorting_mode: dict[str, TaskSortMode] = {}

    def reset(self) -> None:
        self._settings = {}
        self._task_sorting_mode = {}

    def get_settings(self, project_name: str | None = None) -> dict:
        settings = self._settings.get(project_name)
        if settings is None:
            if project_name is None:
                settings = get_studio_settings()
            else:
                settings = get_project_settings(project_name)
            self._settings[project_name] = settings
        return copy.deepcopy(settings)

    def get_task_sorting_mode(
        self, project_name: str | None = None
    ) -> TaskSortMode:
        mode = self._task_sorting_mode.get(project_name)
        if mode is not None:
            return mode

        settings = self.get_settings(project_name)
        use_task_type_sorting = (
            settings["core"]["tools"]["general"]["use_task_type_sorting"]
        )
        mode: TaskSortMode = "type" if use_task_type_sorting else "name"
        self._task_sorting_mode[project_name] = mode
        return mode
