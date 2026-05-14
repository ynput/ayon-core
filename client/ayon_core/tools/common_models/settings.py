from __future__ import annotations

import copy

from ayon_core.settings import get_studio_settings, get_project_settings


class SettingsModel:
    def __init__(self):
        self._settings = {}

    def reset(self) -> None:
        self._settings = {}

    def get_settings(self, project_name: str | None = None) -> dict:
        settings = self._settings.get(project_name)
        if settings is None:
            if project_name is None:
                settings = get_studio_settings()
            else:
                settings = get_project_settings(project_name)
            self._settings[project_name] = settings
        return copy.deepcopy(settings)
