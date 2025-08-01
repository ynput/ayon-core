import os

import ayon_api

from ayon_core.host import IWorkfileHost
from ayon_core.lib import Logger
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import Anatomy, registered_host
from ayon_core.pipeline.context_tools import get_global_context

from ayon_core.tools.common_models import (
    HierarchyModel,
    HierarchyExpectedSelection,
    ProjectsModel,
    UsersModel,
)

from .abstract import (
    AbstractWorkfilesFrontend,
    AbstractWorkfilesBackend,
)
from .models import SelectionModel, WorkfilesModel


class WorkfilesToolExpectedSelection(HierarchyExpectedSelection):
    def __init__(self, controller):
        super(WorkfilesToolExpectedSelection, self).__init__(
            controller,
            handle_project=False,
            handle_folder=True,
            handle_task=True,
        )

        self._workfile_name = None
        self._representation_id = None

        self._workfile_selected = True
        self._representation_selected = True

    def set_expected_selection(
        self,
        project_name=None,
        folder_id=None,
        task_name=None,
        workfile_name=None,
        representation_id=None,
    ):
        self._workfile_name = workfile_name
        self._representation_id = representation_id

        self._workfile_selected = False
        self._representation_selected = False

        super(WorkfilesToolExpectedSelection, self).set_expected_selection(
            project_name,
            folder_id,
            task_name,
        )

    def get_expected_selection_data(self):
        data = super(
            WorkfilesToolExpectedSelection, self
        ).get_expected_selection_data()

        _is_current = (
            self._project_selected
            and self._folder_selected
            and self._task_selected
        )
        workfile_is_current = False
        repre_is_current = False
        if _is_current:
            workfile_is_current = not self._workfile_selected
            repre_is_current = not self._representation_selected

        data["workfile"] = {
            "name": self._workfile_name,
            "current": workfile_is_current,
            "selected": self._workfile_selected,
        }
        data["representation"] = {
            "id": self._representation_id,
            "current": repre_is_current,
            "selected": self._workfile_selected,
        }
        return data

    def is_expected_workfile_selected(self, workfile_name):
        return (
            workfile_name == self._workfile_name
            and self._workfile_selected
        )

    def is_expected_representation_selected(self, representation_id):
        return (
            representation_id == self._representation_id
            and self._representation_selected
        )

    def expected_workfile_selected(self, folder_id, task_name, workfile_name):
        if folder_id != self._folder_id:
            return False

        if task_name != self._task_name:
            return False

        if workfile_name != self._workfile_name:
            return False
        self._workfile_selected = True
        self._emit_change()
        return True

    def expected_representation_selected(
        self, folder_id, task_name, representation_id
    ):
        if folder_id != self._folder_id:
            return False

        if task_name != self._task_name:
            return False

        if representation_id != self._representation_id:
            return False
        self._representation_selected = True
        self._emit_change()
        return True


class BaseWorkfileController(
    AbstractWorkfilesFrontend, AbstractWorkfilesBackend
):
    def __init__(self, host=None):
        if host is None:
            host = registered_host()

        host_is_valid = isinstance(host, IWorkfileHost)

        self._host = host
        self._host_is_valid = host_is_valid

        self._project_anatomy = None
        self._project_settings = None
        self._event_system = None
        self._log = None

        self._current_project_name = None
        self._current_folder_path = None
        self._current_folder_id = None
        self._current_task_name = None
        self._save_is_enabled = True

        # Expected selected folder and task
        self._users_model = self._create_users_model()
        self._expected_selection = self._create_expected_selection_obj()
        self._selection_model = self._create_selection_model()
        self._projects_model = self._create_projects_model()
        self._hierarchy_model = self._create_hierarchy_model()
        self._workfiles_model = self._create_workfiles_model()

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger("WorkfilesUI")
        return self._log

    def is_host_valid(self):
        return self._host_is_valid

    def _create_users_model(self):
        return UsersModel(self)

    def _create_workfiles_model(self):
        return WorkfilesModel(self._host, self)

    def _create_expected_selection_obj(self):
        return WorkfilesToolExpectedSelection(self)

    def _create_projects_model(self):
        return ProjectsModel(self)

    def _create_selection_model(self):
        return SelectionModel(self)

    def _create_hierarchy_model(self):
        return HierarchyModel(self)

    @property
    def event_system(self):
        """Inner event system for workfiles tool controller.

        Is used for communication with UI. Event system is created on demand.

        Returns:
            QueuedEventSystem: Event system which can trigger callbacks
                for topics.
        """

        if self._event_system is None:
            self._event_system = QueuedEventSystem()
        return self._event_system

    # ----------------------------------------------------
    # Implementation of methods required for backend logic
    # ----------------------------------------------------
    @property
    def project_settings(self):
        if self._project_settings is None:
            self._project_settings = get_project_settings(
                self.get_current_project_name())
        return self._project_settings

    @property
    def project_anatomy(self):
        if self._project_anatomy is None:
            self._project_anatomy = Anatomy(self.get_current_project_name())
        return self._project_anatomy

    def get_project_entity(self, project_name):
        return self._projects_model.get_project_entity(
            project_name)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def get_task_type_items(self, project_name, sender=None):
        return self._projects_model.get_task_type_items(
            project_name, sender
        )

    def get_folder_entity(self, project_name, folder_id):
        return self._hierarchy_model.get_folder_entity(
            project_name, folder_id)

    def get_task_entity(self, project_name, task_id):
        return self._hierarchy_model.get_task_entity(
            project_name, task_id)

    # ---------------------------------
    # Implementation of abstract methods
    # ---------------------------------
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self.event_system.add_callback(topic, callback)

    def is_save_enabled(self):
        """Is workfile save enabled.

        Returns:
            bool: True if save is enabled.
        """

        return self._save_is_enabled

    def set_save_enabled(self, enabled):
        """Enable or disabled workfile save.

        Args:
            enabled (bool): Enable save workfile when True.
        """

        if self._save_is_enabled == enabled:
            return

        self._save_is_enabled = enabled
        self._emit_event(
            "workfile_save_enable.changed",
            {"enabled": enabled}
        )

    def get_user_items_by_name(self):
        project_name = self.get_current_project_name()
        return self._users_model.get_user_items_by_name(project_name)

    # Host information
    def get_workfile_extensions(self):
        return self._host.get_workfile_extensions()

    def has_unsaved_changes(self):
        return self._host.workfile_has_unsaved_changes()

    # Current context
    def get_host_name(self):
        return self._host.name

    def get_current_project_name(self):
        return self._current_project_name

    def get_current_folder_id(self):
        return self._current_folder_id

    def get_current_task_name(self):
        return self._current_task_name

    def get_current_workfile(self):
        return self._workfiles_model.get_current_workfile()

    # Selection information
    def get_selected_folder_id(self):
        return self._selection_model.get_selected_folder_id()

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)

    def get_selected_task_id(self):
        return self._selection_model.get_selected_task_id()

    def get_selected_task_name(self):
        return self._selection_model.get_selected_task_name()

    def set_selected_task(self, task_id, task_name):
        return self._selection_model.set_selected_task(task_id, task_name)

    def get_selected_workfile_path(self):
        return self._selection_model.get_selected_workfile_path()

    def set_selected_workfile_path(
        self, rootless_path, path, workfile_entity_id
    ):
        self._selection_model.set_selected_workfile_path(
            rootless_path, path, workfile_entity_id
        )

    def get_selected_representation_id(self):
        return self._selection_model.get_selected_representation_id()

    def set_selected_representation_id(self, representation_id):
        self._selection_model.set_selected_representation_id(
            representation_id)

    def set_expected_selection(
        self,
        folder_id,
        task_name,
        workfile_name=None,
        representation_id=None
    ):
        self._expected_selection.set_expected_selection(
            self.get_current_project_name(),
            folder_id,
            task_name,
            workfile_name,
            representation_id
        )
        self._trigger_expected_selection_changed()

    def expected_folder_selected(self, folder_id):
        if self._expected_selection.expected_folder_selected(folder_id):
            self._trigger_expected_selection_changed()

    def expected_task_selected(self, folder_id, task_name):
        if self._expected_selection.expected_task_selected(
            folder_id, task_name
        ):
            self._trigger_expected_selection_changed()

    def expected_workfile_selected(self, folder_id, task_name, workfile_name):
        if self._expected_selection.expected_workfile_selected(
            folder_id, task_name, workfile_name
        ):
            self._trigger_expected_selection_changed()

    def expected_representation_selected(
        self, folder_id, task_name, representation_id
    ):
        if self._expected_selection.expected_representation_selected(
            folder_id, task_name, representation_id
        ):
            self._trigger_expected_selection_changed()

    def get_expected_selection_data(self):
        return self._expected_selection.get_expected_selection_data()

    def go_to_current_context(self):
        self.set_expected_selection(
            self._current_folder_id, self._current_task_name
        )

    # Model functions
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_id, sender=None):
        return self._hierarchy_model.get_task_items(
            project_name, folder_id, sender
        )

    def get_workarea_dir_by_context(self, folder_id, task_id):
        return self._workfiles_model.get_workarea_dir_by_context(
            folder_id, task_id)

    def get_workarea_file_items(self, folder_id, task_name, sender=None):
        task_id = self._get_task_id(folder_id, task_name)
        return self._workfiles_model.get_workarea_file_items(
            folder_id, task_id
        )

    def get_workarea_save_as_data(self, folder_id, task_id):
        return self._workfiles_model.get_workarea_save_as_data(
            folder_id, task_id)

    def fill_workarea_filepath(
        self,
        folder_id,
        task_id,
        extension,
        use_last_version,
        version,
        comment,
    ):
        return self._workfiles_model.fill_workarea_filepath(
            folder_id,
            task_id,
            extension,
            use_last_version,
            version,
            comment,
        )

    def get_published_file_items(self, folder_id, task_id):
        return self._workfiles_model.get_published_file_items(
            folder_id, task_id
        )

    def get_workfile_info(self, folder_id, task_id, rootless_path):
        return self._workfiles_model.get_workfile_info(
            folder_id, task_id, rootless_path
        )

    def save_workfile_info(
        self,
        task_id,
        rootless_path,
        version=None,
        comment=None,
        description=None,
    ):
        self._workfiles_model.save_workfile_info(
            task_id,
            rootless_path,
            version,
            comment,
            description,
        )

    def get_workfile_entities(self, task_id):
        return self._workfiles_model.get_workfile_entities(task_id)

    def reset(self):
        if not self._host_is_valid:
            self._emit_event("controller.reset.started")
            self._emit_event("controller.reset.finished")
            return
        expected_folder_id = self.get_selected_folder_id()
        expected_task_name = self.get_selected_task_name()
        expected_work_path = self.get_selected_workfile_path()
        expected_repre_id = self.get_selected_representation_id()
        expected_work_name = None
        if expected_work_path:
            expected_work_name = os.path.basename(expected_work_path)

        self._emit_event("controller.reset.started")

        context = self._get_host_current_context()

        project_name = context["project_name"]
        folder_path = context["folder_path"]
        task_name = context["task_name"]
        current_file = self.get_current_workfile()
        folder_id = None
        if folder_path:
            folder = ayon_api.get_folder_by_path(project_name, folder_path)
            if folder:
                folder_id = folder["id"]

        self._project_settings = None
        self._project_anatomy = None

        self._current_project_name = project_name
        self._current_folder_path = folder_path
        self._current_folder_id = folder_id
        self._current_task_name = task_name

        self._projects_model.reset()
        self._hierarchy_model.reset()
        self._workfiles_model.reset()

        if not expected_folder_id:
            expected_folder_id = folder_id
            expected_task_name = task_name
            if current_file:
                expected_work_name = os.path.basename(current_file)

        self._emit_event("controller.reset.finished")

        self._expected_selection.set_expected_selection(
            project_name,
            expected_folder_id,
            expected_task_name,
            expected_work_name,
            expected_repre_id,
        )

    # Controller actions
    def open_workfile(self, folder_id, task_id, filepath):
        self._workfiles_model.open_workfile(folder_id, task_id, filepath)

    def save_current_workfile(self):
        self._workfiles_model.save_current_workfile()

    def save_as_workfile(
        self,
        folder_id,
        task_id,
        rootless_workdir,
        workdir,
        filename,
        version,
        comment,
        description,
    ):
        self._workfiles_model.save_as_workfile(
            folder_id,
            task_id,
            rootless_workdir,
            workdir,
            filename,
            version,
            comment,
            description,
        )

    def copy_workfile_representation(
        self,
        representation_id,
        representation_filepath,
        folder_id,
        task_id,
        workdir,
        filename,
        rootless_workdir,
        version,
        comment,
        description,
    ):
        self._workfiles_model.copy_workfile_representation(
            representation_id,
            representation_filepath,
            folder_id,
            task_id,
            workdir,
            filename,
            rootless_workdir,
            version,
            comment,
            description,
        )

    def duplicate_workfile(
        self,
        folder_id,
        task_id,
        src_filepath,
        rootless_workdir,
        workdir,
        filename,
        version,
        comment,
        description
    ):
        self._workfiles_model.duplicate_workfile(
            folder_id,
            task_id,
            src_filepath,
            rootless_workdir,
            workdir,
            filename,
            version,
            comment,
            description,
        )

    def _emit_event(self, topic, data=None):
        self.emit_event(topic, data, "controller")

    def _get_task_id(self, folder_id, task_name, sender=None):
        task_item = self._hierarchy_model.get_task_item_by_name(
            self.get_current_project_name(),
            folder_id,
            task_name,
            sender
        )
        if not task_item:
            return None
        return task_item.id

    def _get_host_current_context(self):
        if hasattr(self._host, "get_current_context"):
            return self._host.get_current_context()
        return get_global_context()

    # Expected selection
    # - expected selection is used to restore selection after refresh
    #   or when current context should be used
    def _trigger_expected_selection_changed(self):
        self._emit_event(
            "expected_selection_changed",
            self._expected_selection.get_expected_selection_data(),
        )
