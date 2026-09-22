"""Folders hierarchy model used by the browser slicer.

Loading, refresh and filtering are implemented by the shared
'FoldersQtModel' and 'FoldersProxyModel', this module only adapts them to
the browser controller.
"""
from __future__ import annotations

from ayon_core.lib import MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.folders_widget import (
    FOLDERS_MODEL_SENDER_NAME,
    FOLDER_ID_ROLE,
    FOLDER_NAME_ROLE,
    FOLDER_PATH_ROLE,
    FOLDER_TYPE_ROLE,
    FOLDER_PATH_FILTER_ROLE,
    FOLDER_STATUS_ROLE,
    FOLDER_STATUS_ICON_ROLE,
    FoldersQtModel,
    FoldersProxyModel,
)

__all__ = (
    "FOLDERS_MODEL_SENDER_NAME",
    "FOLDER_ID_ROLE",
    "FOLDER_NAME_ROLE",
    "FOLDER_PATH_ROLE",
    "FOLDER_TYPE_ROLE",
    "FOLDER_PATH_FILTER_ROLE",
    "FOLDER_STATUS_ROLE",
    "FOLDER_STATUS_ICON_ROLE",
    "BrowserFoldersModel",
    "BrowserFoldersProxyModel",
)


class BrowserFoldersProxyModel(FoldersProxyModel):
    """Sorting and filtering of browser folders."""


class BrowserFoldersModel(FoldersQtModel):
    """Folders of the project selected in the browser.

    Args:
        ui_controller: Browser widget controller providing current project.
        controller: The control object providing folder items.
    """
    _default_folder_icon = None

    FILTER_ROLE = FOLDER_PATH_FILTER_ROLE

    def __init__(self, ui_controller, controller):
        super().__init__(controller)
        self._ui_controller = ui_controller

    def reset(self):
        """Refresh folders for the project selected in the browser.

        This may or may not trigger query from server, that's based on
        controller's cache.
        """
        self.set_project_name(self._ui_controller.current_project)

    @classmethod
    def _get_default_folder_icon(cls):
        if cls._default_folder_icon is None:
            cls._default_folder_icon = get_qt_icon(MaterialSymbolsIcon(
                "folder", color=get_default_entity_icon_color()
            ))
        return cls._default_folder_icon
