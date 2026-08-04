from __future__ import annotations

import typing
from typing import Any, Callable

from qtpy import QtCore

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.ipc_api import WaitCallback
from ayon_core.tools.ipc_utils.utils import execute_in_main_thread

from .abstract import FrontendLoaderController
from .ui.window import LoaderWindow

if typing.TYPE_CHECKING:
    from ayon_core.tools.ipc_utils.utils import CommunicationInfo
    from ayon_core.ipc_api import RequestMessage
    from ayon_core.tools.common_models import (
        TagItem,
        ProductTypeIconMapping,
        ProjectItem,
        StatusItem,
    )
    from ayon_core.tools.common_models import (
        FolderItem,
        TaskItem,
        FolderTypeItem,
        TaskTypeItem,
    )

    from .abstract import (
        ProductItem,
        ProductTypeItem,
        RepreItem,
        ActionItem,
        ProductTypesFilter,
    )


class WorkerTask(QtCore.QObject, QtCore.QRunnable):
    def __init__(self, func, *args, **kwargs):
        QtCore.QObject.__init__(self)
        QtCore.QRunnable.__init__(self)
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.func(*self.args, **self.kwargs)


class IPCLoaderFrontend(FrontendLoaderController):
    channel_name = "loader"

    def __init__(self, com_info: CommunicationInfo) -> None:
        com_info.register_channel_handler(
            self.channel_name, self._handle_request
        )
        self._window = None
        self._event_system = QueuedEventSystem()
        self._com_info: CommunicationInfo = com_info
        self._thread_pool = QtCore.QThreadPool()
        self._thread_pool.setMaxThreadCount(1)

    def _handle_request(self, req: RequestMessage):
        if req.method == "show":
            execute_in_main_thread(self._show_window)

        elif req.method == "emit_event":
            execute_in_main_thread(self.emit_event, **req.params)

    def _show_window(self):
        if self._window is None:
            self._window = LoaderWindow(controller=self)
            self._window.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)

        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] | None,
        source: str | None,
    ) -> None:
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic: str, callback: Callable) -> None:
        self._event_system.add_callback(topic, callback)

    def get_window_subtitle(self) -> str | None:
        return self._trigger_getter("get_window_subtitle")

    def reset(self) -> None:
        self._trigger_method("reset")

    def get_expected_selection_data(self) -> dict[str, Any]:
        return self._trigger_getter("get_expected_selection_data")

    def set_expected_selection(
        self,
        project_name: str,
        folder_id: str,
    ) -> None:
        self._trigger_method(
            "set_expected_selection",
            project_name=project_name,
            folder_id=folder_id,
        )

    def expected_project_selected(self, project_name: str) -> bool:
        return self._trigger_getter(
            "expected_project_selected",
            project_name=project_name
        )

    def expected_folder_selected(self, folder_id: str) -> bool:
        return self._trigger_getter(
            "expected_folder_selected",
            folder_id=folder_id,
        )

    def get_project_items(
        self, sender: str | None = None
    ) -> list[ProjectItem]:
        return self._trigger_getter(
            "get_project_items",
            sender=sender,
        )

    def get_project_status_items(
        self, project_name: str | None
    ) -> list[StatusItem]:
        return self._trigger_getter(
            "get_project_status_items",
            project_name=project_name,
        )

    def get_product_type_icons_mapping(
        self,
        project_name: str,
        sender: str | None = None
    ) -> ProductTypeIconMapping:
        return self._trigger_getter(
            "get_product_type_icons_mapping",
            project_name=project_name,
            sender=sender,
        )

    def get_project_settings(self, project_name: str | None) -> dict[str, Any]:
        return self._trigger_getter(
            "get_project_settings",
            project_name=project_name,
        )

    def get_project_anatomy_tags(self, project_name: str) -> list[TagItem]:
        return self._trigger_getter(
            "get_project_anatomy_tags",
            project_name=project_name,
        )

    def get_folder_type_items(
        self, project_name: str, sender: str | None = None
    ) -> list[FolderTypeItem]:
        return self._trigger_getter(
            "get_folder_type_items",
            project_name=project_name,
            sender=sender,
        )

    def get_folder_items(
        self, project_name: str, sender: str | None = None
    ) -> dict[str, FolderItem]:
        return self._trigger_getter(
            "get_folder_items",
            project_name=project_name,
            sender=sender,
        )

    def get_task_items(
        self,
        project_name: str,
        folder_ids: set[str],
        sender: str | None = None,
    ) -> list[TaskItem]:
        return self._trigger_getter(
            "get_task_items",
            project_name=project_name,
            folder_ids=folder_ids,
            sender=sender,
        )

    def get_task_type_items(
        self, project_name: str, sender: str | None = None
    ) -> list[TaskTypeItem]:
        return self._trigger_getter(
            "get_task_type_items",
            project_name=project_name,
            sender=sender,
        )

    def get_folder_labels(
        self, project_name: str, folder_ids: set[str]
    ) -> dict[str, str]:
        return self._trigger_getter(
            "get_folder_labels",
            project_name=project_name,
            folder_ids=folder_ids,
        )

    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        return self._trigger_getter(
            "get_my_tasks_entity_ids",
            project_name=project_name,
        )

    def get_available_tags_by_entity_type(
        self, project_name: str
    ) -> dict[str, list[str]]:
        return self._trigger_getter(
            "get_available_tags_by_entity_type",
            project_name=project_name,
        )

    def get_product_items(
        self,
        project_name: str,
        folder_ids: set[str],
        sender: str | None = None,
    ) -> list[ProductItem]:
        return self._trigger_getter(
            "get_product_items",
            project_name=project_name,
            folder_ids=folder_ids,
            sender=sender,
        )

    def get_product_item(
        self, project_name: str, product_id: str
    ) -> ProductItem | None:
        return self._trigger_getter(
            "get_product_item",
            project_name=project_name,
            product_id=product_id,
        )

    def get_product_type_items(
        self, project_name: str
    ) -> list[ProductTypeItem]:
        return self._trigger_getter(
            "get_product_type_items",
            project_name=project_name,
        )

    def get_representation_items(
        self,
        project_name: str,
        version_ids: set[str],
        sender: str | None = None,
    ) -> list[RepreItem]:
        return self._trigger_getter(
            "get_representation_items",
            project_name=project_name,
            version_ids=version_ids,
            sender=sender,
        )

    def get_version_thumbnail_ids(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, str | None]:
        return self._trigger_getter(
            "get_version_thumbnail_ids",
            project_name=project_name,
            version_ids=version_ids,
        )

    def get_folder_thumbnail_ids(
        self, project_name: str, folder_ids: set[str]
    ) -> dict[str, str | None]:
        return self._trigger_getter(
            "get_folder_thumbnail_ids",
            project_name=project_name,
            folder_ids=folder_ids,
        )

    def get_versions_representation_count(
        self,
        project_name: str,
        version_ids: list[str] | set[str],
        sender: str | None=None
    ) -> dict[str, int]:
        return self._trigger_getter(
            "get_versions_representation_count",
            project_name=project_name,
            version_ids=version_ids,
            sender=sender,
        )

    def get_thumbnail_paths(
        self,
        project_name: str,
        entity_type: str,
        entity_ids: set[str],
    ) -> dict[str, str | None]:
        return self._trigger_getter(
            "get_thumbnail_paths",
            project_name=project_name,
            entity_type=entity_type,
            entity_ids=entity_ids,
        )

    def get_selected_project_name(self) -> str | None:
        return self._trigger_getter("get_selected_project_name")

    def get_selected_folder_ids(self) -> set[str]:
        return self._trigger_getter("get_selected_folder_ids")

    def get_selected_task_ids(self) -> set[str]:
        return self._trigger_getter("get_selected_task_ids",)

    def get_selected_version_ids(self) -> set[str]:
        return self._trigger_getter("get_selected_version_ids")

    def get_selected_representation_ids(self) -> set[str]:
        return self._trigger_getter(
            "get_selected_representation_ids"
        )

    def set_selected_project(self, project_name: str | None) -> None:
        self._trigger_method(
            "set_selected_project",
            project_name=project_name,
        )

    def set_selected_folders(self, folder_ids: list[str]) -> None:
        self._trigger_method(
            "set_selected_folders",
            folder_ids=folder_ids,
        )

    def set_selected_tasks(self, task_ids: set[str | None]) -> None:
        self._trigger_method(
            "set_selected_tasks",
            task_ids=task_ids,
        )

    def set_selected_versions(self, version_ids: set[str]) -> None:
        self._trigger_method(
            "set_selected_versions",
            version_ids=version_ids,
        )

    def set_selected_representations(self, repre_ids: set[str]) -> None:
        self._trigger_method(
            "set_selected_representations",
            repre_ids=repre_ids,
        )

    def get_action_items(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> list[ActionItem]:
        return self._trigger_getter(
            "get_action_items",
            project_name=project_name,
            entity_ids=entity_ids,
            entity_type=entity_type,
        )

    def trigger_action_item(
        self,
        identifier: str,
        project_name: str,
        selected_ids: set[str],
        selected_entity_type: str,
        data: dict[str, Any] | None,
        options: dict[str, Any],
        form_values: dict[str, Any],
    ) -> None:
        self._trigger_method(
            "trigger_action_item",
            project_name=project_name,
            selected_ids=selected_ids,
            selected_entity_type=selected_entity_type,
            identifier=identifier,
            data=data,
            options=options,
            form_values=form_values,
        )

    def change_products_group(
        self,
        project_name: str,
        product_ids: set[str],
        group_name: str,
    ) -> None:
        self._trigger_method(
            "change_products_group",
            project_name=project_name,
            product_ids=product_ids,
            group_name=group_name,
        )

    def fill_root_in_source(self, source: str) -> str:
        return self._trigger_getter(
            "fill_root_in_source", source=source
        )

    def get_current_context(self) -> dict[str, str | None]:
        return self._trigger_getter("get_current_context")

    def is_loaded_products_supported(self) -> bool:
        return self._trigger_getter(
            "is_loaded_products_supported"
        )

    def is_standard_projects_filter_enabled(self) -> bool:
        return self._trigger_getter(
            "is_standard_projects_filter_enabled"
        )

    def is_sitesync_enabled(
        self, project_name: str | None = None
    ) -> bool:
        return self._trigger_getter(
            "is_sitesync_enabled",
            project_name=project_name,
        )

    def get_active_site_icon_def(self, project_name: str) -> str:
        return self._trigger_getter(
            "get_active_site_icon_def",
            project_name=project_name,
        )

    def get_remote_site_icon_def(self, project_name: str):
        return self._trigger_getter(
            "get_remote_site_icon_def",
            project_name=project_name,
        )

    def get_active_site(self, project_name: str) -> str | None:
        return self._trigger_getter(
            "get_active_site",
            project_name=project_name,
        )

    def get_remote_site(self, project_name: str) -> str | None:
        return self._trigger_getter(
            "get_remote_site",
            project_name=project_name,
        )

    def get_version_sync_availability(
        self,
        project_name: str,
        version_ids: list[str] | set[str],
    ) -> dict[str, tuple[int, int]]:
        return self._trigger_getter(
            "get_version_sync_availability",
            project_name=project_name,
            version_ids=version_ids,
        )

    def get_representations_sync_status(
        self, project_name: str, representation_ids: set[str]
    ) -> dict[str, tuple[float, float]]:
        return self._trigger_getter(
            "get_representations_sync_status",
            project_name=project_name,
            representation_ids=representation_ids,
        )

    def get_product_types_filter(self) -> ProductTypesFilter:
        return self._trigger_getter("get_product_types_filter")

    def _trigger_getter(
        self,
        method_name: str,
        **kwargs,
    ):
        """Trigger a getter method on backend and wait for result.

        Args:
            method_name (str): Name of method to trigger.
            **kwargs: Parameters for the method.

        Returns:
            Any: Result of the triggered method.

        """
        return self._trigger(method_name, kwargs, True)

    def _trigger_method(
        self,
        method_name: str,
        **kwargs,
    ):
        """Trigger a method on backend without waiting for response.

        Args:
            method_name (str): Name of method to trigger.
            **kwargs: Parameters for the method.

        Returns:
            Any: Result of the triggered method.

        """
        self._trigger(method_name, kwargs, False)

    def _trigger(
        self,
        method_name: str,
        params: dict[str, Any],
        wait: bool,
    ) -> Any | None:
        """Trigger a method on backend.

        Args:
            method_name (str): Name of method to trigger.
            params (dict): Parameters for the method.
            wait (bool): Whether to wait for a response.

        Returns:
            Any: Result of the triggered method.

        """
        response_callback = WaitCallback()
        task = WorkerTask(
            self._com_info.send_request,
            self.channel_name,
            method_name,
            params,
            callback=response_callback
        )
        self._thread_pool.start(task)
        if not wait:
            return None

        app = QtCore.QCoreApplication.instance()
        while not response_callback.is_done():
            if not self._com_info.is_parent_process_alive():
                raise RuntimeError(
                    "Parent process has exited"
                    f" while waiting for '{method_name}'"
                )

            # Keep UI/queued callbacks responsive while waiting.
            app.processEvents(QtCore.QEventLoop.AllEvents, 5)
            response_callback.wait(0.01)

        response = response_callback.response
        if response is None:
            raise RuntimeError(f"No response payload for '{method_name}'")

        if not response.ok:
            raise RuntimeError(
                response.error or f"Request '{method_name}' failed"
            )
        return response.result
