import copy

import ayon_api

from ayon_core import resources
from ayon_core.lib import Logger, NestedCacheItem
from ayon_core.settings import get_studio_settings, get_project_settings
from ayon_core.pipeline.actions import LauncherAction

from .exceptions import (
    ApplicationExecutableNotFound,
    ApplicationLaunchFailed,
)


class ApplicationAction(LauncherAction):
    """Action to launch an application.

    Application action based on 'ApplicationManager' system.

    Handling of applications in launcher is not ideal and should be completely
    redone from scratch. This is just a temporary solution to keep backwards
    compatibility with AYON launcher.

    Todos:
        Move handling of errors to frontend.
    """

    # Application object
    application = None
    # Action attributes
    name = None
    label = None
    label_variant = None
    group = None
    icon = None
    color = None
    order = 0
    data = {}
    project_settings = {}
    project_entities = {}

    _log = None

    # --- For compatibility for combinations of new and old ayon-core ---
    project_settings_cache = NestedCacheItem(
        levels=1, default_factory=dict, lifetime=20
    )
    project_entities_cache = NestedCacheItem(
        levels=1, default_factory=dict, lifetime=20
    )

    @classmethod
    def _app_get_project_settings(cls, selection):
        project_name = selection.project_name
        if project_name in ApplicationAction.project_settings:
            return ApplicationAction.project_settings[project_name]

        if hasattr(selection, "get_project_settings"):
            return selection.get_project_settings()

        cache = ApplicationAction.project_settings_cache[project_name]
        if not cache.is_valid:
            if project_name:
                settings = get_project_settings(project_name)
            else:
                settings = get_studio_settings()
            cache.update_data(settings)
        return copy.deepcopy(cache.get_data())

    @classmethod
    def _app_get_project_entity(cls, selection):
        project_name = selection.project_name
        if project_name in ApplicationAction.project_entities:
            return ApplicationAction.project_entities[project_name]

        if hasattr(selection, "get_project_settings"):
            return selection.get_project_entity()

        cache = ApplicationAction.project_entities_cache[project_name]
        if not cache.is_valid:
            project_entity = None
            if project_name:
                project_entity = ayon_api.get_project(project_name)
            cache.update_data(project_entity)
        return copy.deepcopy(cache.get_data())

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    def is_compatible(self, selection):
        if not selection.is_task_selected:
            return False

        project_entity = self._app_get_project_entity(selection)
        apps = project_entity["attrib"].get("applications")
        if not apps or self.application.full_name not in apps:
            return False

        project_settings = self._app_get_project_settings(selection)
        only_available = project_settings["applications"]["only_available"]
        if only_available and not self.application.find_executable():
            return False
        return True

    def _show_message_box(self, title, message, details=None):
        from qtpy import QtWidgets, QtGui
        from ayon_core import style

        dialog = QtWidgets.QMessageBox()
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        dialog.setWindowIcon(icon)
        dialog.setStyleSheet(style.load_stylesheet())
        dialog.setWindowTitle(title)
        dialog.setText(message)
        if details:
            dialog.setDetailedText(details)
        dialog.exec_()

    def process(self, selection, **kwargs):
        """Process the full Application action"""
        try:
            self.application.launch(
                project_name=selection.project_name,
                folder_path=selection.folder_path,
                task_name=selection.task_name,
                **self.data
            )

        except ApplicationExecutableNotFound as exc:
            details = exc.details
            msg = exc.msg
            log_msg = str(msg)
            if details:
                log_msg += "\n" + details
            self.log.warning(log_msg)
            self._show_message_box(
                "Application executable not found", msg, details
            )

        except ApplicationLaunchFailed as exc:
            msg = str(exc)
            self.log.warning(msg, exc_info=True)
            self._show_message_box("Application launch failed", msg)
