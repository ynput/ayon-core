from __future__ import annotations

import json
from typing import Optional

from ayon_api import get_workfiles_info

from ayon_core.lib import Logger, JSONSettingRegistry, get_launcher_local_dir
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.addon import AddonsManager
from ayon_core.settings import get_project_settings, get_studio_settings
from ayon_core.tools.common_models import (
    ProjectsModel,
    HierarchyModel,
    UsersModel,
)

from .abstract import (
    AbstractLauncherFrontEnd,
    AbstractLauncherBackend,
    WorkfileItem,
)
from .models import (
    LauncherSelectionModel,
    ActionsModel,
    WorkfilesModel,
)
from .launcher_open_publish import (
    host_name_for_path_from_ext_map,
    run_open_published_representation_local,
)

NOT_SET = object()


class BaseLauncherController(
    AbstractLauncherFrontEnd, AbstractLauncherBackend
):
    def __init__(self):
        self._project_settings = {}
        self._event_system = None
        self._log = None

        self._launcher_registry = JSONSettingRegistry(
            "launcher",
            get_launcher_local_dir("tools")
        )

        self._addons_manager = None

        self._selection_model = LauncherSelectionModel(self)
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)
        self._actions_model = ActionsModel(self)
        self._workfiles_model = WorkfilesModel(self)
        self._users_model = UsersModel(self)

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def event_system(self):
        """Inner event system for launcher tool controller.

        Is used for communication with UI. Event system is created on demand.

        Returns:
            QueuedEventSystem: Event system which can trigger callbacks
                for topics.
        """

        if self._event_system is None:
            self._event_system = QueuedEventSystem()
        return self._event_system

    # ---------------------------------
    # Implementation of abstract methods
    # ---------------------------------
    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self.event_system.add_callback(topic, callback)

    def set_run_on_main_thread(self, executor):
        """Set executor(fn) to run `fn` on the main UI thread."""
        self._run_on_main_thread = executor

    def run_on_main_thread(self, fn):
        """Run `fn` on the main thread (defer if executor set)."""
        if getattr(self, "_run_on_main_thread", None):
            self._run_on_main_thread(fn)
        else:
            fn()

    def get_addons_manager(self) -> AddonsManager:
        if self._addons_manager is None:
            self._addons_manager = AddonsManager()
        return self._addons_manager

    def get_extension_to_host_map(self) -> dict[str, str]:
        """Normalized extension -> host_name (from cached applications index)."""
        return self._workfiles_model.get_extension_to_host_map()

    def get_tray_workfile_extensions(self) -> list[str]:
        """Extensions from installed host addons (tray `IWorkfileHost` / workfile UI)."""
        return self._workfiles_model.get_all_workfile_extensions()

    def _warn_launcher_open(self, message: str) -> None:
        """Show a modal warning on the UI thread (Launcher window may be hidden)."""
        from qtpy import QtWidgets

        def show() -> None:
            QtWidgets.QMessageBox.warning(None, "Launcher", message)

        self.run_on_main_thread(show)

    def get_grouped_host_names(self) -> list[str | None]:
        try:
            value = self._launcher_registry.get_item(
                "grouped_hosts", default="[]"
            )
            return json.loads(value)
        except Exception:
            # NOTE This is future-guarding in case we'd change the stored data
            self.log.warning("Failed to get grouped hosts", exc_info=True)
            return []

    def set_grouped_host_names(self, host_names: list[str | None]):
        value = json.dumps(host_names)
        self._launcher_registry.set_item("grouped_hosts", value)

    def get_show_published_workfiles(self) -> bool:
        try:
            raw = self._launcher_registry.get_item(
                "show_published_workfiles", default="false"
            )
            return raw in ("true", "1", "True")
        except Exception:
            self.log.warning(
                "Failed to read registry key show_published_workfiles",
                exc_info=True,
            )
            return False

    def set_show_published_workfiles(self, enabled: bool) -> None:
        self._launcher_registry.set_item(
            "show_published_workfiles", "true" if enabled else "false"
        )

    # Entity items for UI
    def get_project_items(self, sender=None):
        return self._projects_model.get_project_items(sender)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def get_task_type_items(self, project_name, sender=None):
        return self._projects_model.get_task_type_items(
            project_name, sender
        )

    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_id, sender=None):
        return self._hierarchy_model.get_task_items(
            project_name, folder_id, sender
        )

    def get_task_ids_with_workfiles(self, project_name: str, folder_id: str):
        """Task ids in folder that have at least one workfile."""
        task_items = self._hierarchy_model.get_task_items(
            project_name, folder_id, sender=None
        )
        if not task_items:
            return set()
        task_ids = {str(t.id) for t in task_items}
        workfiles = get_workfiles_info(
            project_name, task_ids=task_ids, fields={"taskId"}
        )
        return {
            str(w["taskId"])
            for w in workfiles
            if w.get("taskId") is not None
        }

    # Project settings for applications actions
    def get_project_settings(self, project_name):
        if project_name in self._project_settings:
            return self._project_settings[project_name]
        if project_name:
            settings = get_project_settings(project_name)
        else:
            settings = get_studio_settings()
        self._project_settings[project_name] = settings
        return settings

    # Entity for backend
    def get_project_entity(self, project_name):
        return self._projects_model.get_project_entity(project_name)

    def get_folder_entity(self, project_name, folder_id):
        return self._hierarchy_model.get_folder_entity(
            project_name, folder_id)

    def get_task_entity(self, project_name, task_id):
        return self._hierarchy_model.get_task_entity(project_name, task_id)

    # Selection methods
    def get_selected_project_name(self):
        return self._selection_model.get_selected_project_name()

    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)

    def get_selected_folder_id(self):
        return self._selection_model.get_selected_folder_id()

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)

    def get_selected_task_id(self):
        return self._selection_model.get_selected_task_id()

    def get_selected_task_name(self):
        return self._selection_model.get_selected_task_name()

    def set_selected_task(self, task_id, task_name):
        self._selection_model.set_selected_task(task_id, task_name)

    def set_selected_workfile(self, workfile_id):
        self._selection_model.set_selected_workfile(workfile_id)

    def get_selected_context(self):
        return {
            "project_name": self.get_selected_project_name(),
            "folder_id": self.get_selected_folder_id(),
            "task_id": self.get_selected_task_id(),
            "task_name": self.get_selected_task_name(),
        }

    # Workfiles
    def get_workfile_items(
        self,
        project_name: Optional[str],
        task_id: Optional[str],
    ) -> list[WorkfileItem]:
        return self._workfiles_model.get_workfile_items(
            project_name,
            task_id,
        )

    def get_workfile_tooltip_data(self, workfile_id: Optional[str]) -> str:
        """On-demand tooltip string for a workfile (size, users, dates, comment)."""
        if not workfile_id:
            return ""
        return self._workfiles_model.get_workfile_tooltip_data(
            self.get_selected_project_name(),
            self.get_selected_task_id(),
            workfile_id,
        )

    def get_published_workfile_tooltip_data(
        self,
        representation_id: Optional[str],
        representation_filepath: Optional[str],
    ) -> str:
        """On-demand tooltip for a published representation row."""
        if not representation_id:
            return ""
        return self._workfiles_model.get_published_representation_tooltip_data(
            self.get_selected_project_name(),
            self.get_selected_task_id(),
            representation_id,
            representation_filepath,
        )

    # Actions
    def get_action_items(
        self, project_name, folder_id, task_id, workfile_id
    ):
        return self._actions_model.get_action_items(
            project_name, folder_id, task_id, workfile_id
        )

    def get_launch_action_ids_for_host(self, host_name: str):
        return self._actions_model.get_launch_action_ids_for_host(host_name)

    def get_preferred_launch_action_id_for_host(self, host_name: str):
        return (
            self._actions_model.get_preferred_launch_action_id_for_host(
                host_name
            )
        )

    def trigger_action(
        self,
        identifier,
        project_name,
        folder_id,
        task_id,
        workfile_id,
    ):
        self._actions_model.trigger_action(
            identifier,
            project_name,
            folder_id,
            task_id,
            workfile_id,
        )

    def open_published_representation_local(
        self,
        _representation_id: str,
        representation_filepath: str,
    ) -> None:
        """Copy published file to a temporary folder and launch DCC.

        Delegates to ``launcher_open_publish.run_open_published_representation_local``.
        Does not register a workfile on the server; the artist saves/version
        from the host application when ready.
        """
        run_open_published_representation_local(
            self.get_selected_project_name(),
            self.get_selected_folder_id(),
            self.get_selected_task_id(),
            representation_filepath,
            get_project_entity=self.get_project_entity,
            get_extension_to_host_map=self.get_extension_to_host_map,
            warn_user=self._warn_launcher_open,
            log=self.log,
            launch=lambda host_name, project_name, folder_id, task_id, path: (
                self._actions_model.trigger_launch_by_host_with_workfile_path(
                    host_name,
                    project_name,
                    folder_id,
                    task_id,
                    path,
                )
            ),
        )

    def open_workfile_with_app(
        self, workfile_id: str, host_name: Optional[str]
    ) -> None:
        """Launch preferred app for host with this workfile selected."""
        from ayon_api import get_server_api_connection

        project_name = self.get_selected_project_name()
        if not project_name:
            return

        ext_map = self.get_extension_to_host_map()
        conn = get_server_api_connection()
        entity = conn.get_workfile_entity_by_id(
            project_name, workfile_id, fields=("data", "path")
        )
        if not entity:
            self._warn_launcher_open("Workfile not found; cannot open.")
            return

        data = entity.get("data") or {}
        path = entity.get("path")
        path_host = (
            host_name_for_path_from_ext_map(path, ext_map) if path else None
        )

        # Prefer host inferred from filename extension when known; published or
        # legacy workfile records can have a wrong data.host_name (e.g. default
        # to a DCC that does not match the file on disk).
        if path_host:
            host_name = path_host
        else:
            if not host_name or host_name == "launcher":
                host_name = data.get("host_name")
            if (not host_name) or host_name == "launcher":
                host_name = None

        if not host_name:
            self._warn_launcher_open(
                "Could not determine which application to use for this "
                "workfile."
            )
            return

        preferred = self.get_preferred_launch_action_id_for_host(host_name)
        effective_id = preferred or host_name
        self.trigger_action(
            effective_id,
            project_name,
            self.get_selected_folder_id(),
            self.get_selected_task_id(),
            workfile_id,
        )

    def trigger_webaction(self, context, action_label, form_data=None):
        self._actions_model.trigger_webaction(
            context, action_label, form_data
        )

    def get_action_config_values(self, context):
        return self._actions_model.get_action_config_values(context)

    def set_action_config_values(self, context, values):
        return self._actions_model.set_action_config_values(context, values)

    # General methods
    def refresh(self):
        self._emit_event("controller.refresh.started")

        self._project_settings = {}

        self._projects_model.reset()
        self._hierarchy_model.reset()
        self._users_model.reset()

        self._actions_model.refresh()
        self._projects_model.refresh()

        self._emit_event("controller.refresh.finished")

    def refresh_actions(self):
        self._emit_event("controller.refresh.actions.started")

        # Refresh project settings (used for actions discovery)
        self._project_settings = {}
        # Refresh projects - they define applications
        self._projects_model.reset()
        # Refresh actions
        self._actions_model.refresh()
        # Reset workfiles model
        self._workfiles_model.reset()

        self._emit_event("controller.refresh.actions.finished")

    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        username = self._users_model.get_current_username()
        assignees = []
        if username:
            assignees.append(username)
        return self._hierarchy_model.get_entity_ids_for_assignees(
            project_name, assignees
        )

    def _emit_event(self, topic, data=None):
        self.emit_event(topic, data, "controller")
