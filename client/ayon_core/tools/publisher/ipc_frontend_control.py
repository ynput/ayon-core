from __future__ import annotations

import typing
from typing import Any, Callable

from qtpy import QtCore

from ayon_core.lib.events import QueuedEventSystem

from ayon_core.ipc_communication import WaitCallback

from ayon_core.tools.ipc_utils.utils import execute_in_main_thread

from .abstract import AbstractPublisherFrontend
from .window import PublisherWindow
from .abstract import CardMessageTypes

if typing.TYPE_CHECKING:
    from ayon_core.lib import IconBase
    from ayon_core.tools.ipc_utils.utils import CommunicationInfo
    from ayon_core.ipc_communication import RequestMessage
    from ayon_core.pipeline.create import InstanceContextInfo, ConvertorItem
    from ayon_core.pipeline.publish import PublishReport
    from ayon_core.tools.common_models import (
        FolderItem,
        TaskItem,
        FolderTypeItem,
        TaskTypeItem,
    )
    from .abstract import (
        CommentDef,
        PublishAttrDefsInfo,
    )
    from .models.create import (
        InstanceItem,
        CreatorItem,
        AbstractAttrDef,
    )
    from .models.publish import PublishErrorInfo


class WorkerTask(QtCore.QObject, QtCore.QRunnable):
    def __init__(self, func, *args, **kwargs):
        QtCore.QObject.__init__(self)
        QtCore.QRunnable.__init__(self)
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        self.func(*self.args, **self.kwargs)


class IPCPublisherFrontend(AbstractPublisherFrontend):
    channel_name = "publisher"

    def __init__(self, com_info: CommunicationInfo) -> None:
        com_info.register_channel_handler(
            self.channel_name, self._handle_request
        )
        self._window = None
        self._event_system = QueuedEventSystem()
        self._com_info: CommunicationInfo = com_info
        self._thread_pool = QtCore.QThreadPool()
        self._thread_pool.setMaxThreadCount(1)

    def emit_card_message(
        self,
        message: str,
        message_type: str = CardMessageTypes.standard
    ):
        self.emit_event(
            "show.card.message",
            {
                "message": message,
                "message_type": message_type
            }
        )

    def emit_event(
        self,
        topic: str,
        data: dict[str, Any] | None = None,
        source: str | None = None,
    ) -> None:
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic: str, callback: Callable) -> None:
        self._event_system.add_callback(topic, callback)

    def get_window_subtitle(self) -> str | None:
        return self._trigger_getter("get_window_subtitle")

    def get_project_settings(
        self, project_name: str | None
    ) -> dict[str, Any]:
        return self._trigger_getter(
            "get_project_settings",
            project_name=project_name,
        )

    def get_current_project_name(self) -> str | None:
        return self._trigger_getter("get_current_project_name")

    def get_current_folder_path(self) -> str | None:
        return self._trigger_getter("get_current_folder_path")

    def get_current_task_name(self) -> str | None:
        return self._trigger_getter("get_current_task_name")

    def host_context_has_changed(self) -> bool:
        return self._trigger_getter("host_context_has_changed")

    def get_comment_def(self) -> CommentDef:
        return self._trigger_getter("get_comment_def")

    def reset(self) -> None:
        self._trigger_method("reset")

    def is_host_valid(self) -> bool:
        return self._trigger_getter("is_host_valid")

    def get_context_title(self) -> str | None:
        return self._trigger_getter("get_context_title")

    def get_task_items_by_folder_paths(
        self, folder_paths: list[str]
    ) -> dict[str, list[TaskItem]]:
        return self._trigger_getter(
            "get_task_items_by_folder_paths",
            folder_paths=folder_paths,
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
        folder_id: str,
        sender: str | None = None,
    ) -> list[TaskItem]:
        return self._trigger_getter(
            "get_task_items",
            project_name=project_name,
            folder_id=folder_id,
            sender=sender,
        )

    def get_folder_type_items(
        self, project_name: str, sender: str | None = None
    ) -> list[FolderTypeItem]:
        return self._trigger_getter(
            "get_folder_type_items",
            project_name=project_name,
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

    def are_folder_paths_valid(self, folder_paths: list[str]) -> bool:
        return self._trigger_getter(
            "are_folder_paths_valid",
            folder_paths=folder_paths,
        )

    def get_folder_id_from_path(self, folder_path: str) -> str | None:
        return self._trigger_getter(
            "get_folder_id_from_path",
            folder_path=folder_path,
        )

    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        return self._trigger_getter(
            "get_my_tasks_entity_ids",
            project_name=project_name,
        )

    def get_creator_items(self) -> dict[str, CreatorItem]:
        return self._trigger_getter("get_creator_items")

    def get_creator_item_by_id(
        self, identifier: str
    ) -> CreatorItem | None:
        return self._trigger_getter(
            "get_creator_item_by_id", identifier=identifier
        )

    def get_creator_icon(
        self, identifier: str
    ) -> str | dict[str, Any] | None | IconBase:
        return self._trigger_getter(
            "get_creator_icon", identifier=identifier
        )

    def get_convertor_items(self) -> dict[str, ConvertorItem]:
        return self._trigger_getter("get_convertor_items")

    def get_instance_items(self) -> list[InstanceItem]:
        return self._trigger_getter("get_instance_items")

    def get_instance_items_by_id(
        self, instance_ids: list[str] | None = None
    ) -> dict[str, InstanceItem | None]:
        if instance_ids is not None:
            instance_ids = set(instance_ids)
        return self._trigger_getter(
            "get_instance_items_by_id",
            instance_ids=instance_ids,
        )

    def get_instances_context_info(
        self, instance_ids: list[str] | None = None
    ) -> dict[str, InstanceContextInfo]:
        if instance_ids is not None:
            instance_ids = set(instance_ids)
        return self._trigger_getter(
            "get_instances_context_info",
            instance_ids=instance_ids,
        )

    def set_instances_context_info(
        self, changes_by_instance_id: dict[str, dict[str, Any]]
    ) -> None:
        self._trigger_method(
            "set_instances_context_info",
            changes_by_instance_id=changes_by_instance_id,
        )

    def set_instances_active_state(
        self, active_state_by_id: dict[str, bool]
    ) -> None:
        self._trigger_method(
            "set_instances_active_state",
            active_state_by_id=active_state_by_id,
        )

    def get_existing_product_names(self, folder_path: str) -> list[str]:
        return self._trigger_getter(
            "get_existing_product_names",
            folder_path=folder_path,
        )

    def get_creator_attribute_definitions(
        self, instance_ids: list[str]
    ) -> list[tuple[AbstractAttrDef, dict[str, dict[str, Any]]]]:
        return self._trigger_getter(
            "get_creator_attribute_definitions",
            instance_ids=instance_ids,
        )

    def set_instances_create_attr_values(
        self, instance_ids: list[str], key: str, value: Any
    ) -> None:
        self._trigger_method(
            "revert_instances_create_attr_values",
            instance_ids=instance_ids,
            key=key,
            value=value,
        )

    def revert_instances_create_attr_values(
        self,
        instance_ids: list[str | None],
        key: str,
    ) -> None:
        self._trigger_method(
            "revert_instances_create_attr_values",
            instance_ids=instance_ids,
            key=key,
        )

    def get_publish_attribute_definitions(
        self,
        instance_ids: list[str],
        include_context: bool
    ) -> list[PublishAttrDefsInfo]:
        return self._trigger_getter(
            "get_publish_attribute_definitions",
            instance_ids=instance_ids,
            include_context=include_context,
        )

    def set_instances_publish_attr_values(
        self,
        instance_ids: list[str],
        plugin_name: str,
        key: str,
        value: Any
    ) -> None:
        self._trigger_method(
            "set_instances_publish_attr_values",
            instance_ids=instance_ids,
            plugin_name=plugin_name,
            key=key,
            value=value,
        )

    def revert_instances_publish_attr_values(
        self,
        instance_ids: list[str | None],
        plugin_name: str,
        key: str,
    ) -> None:
        self._trigger_method(
            "revert_instances_publish_attr_values",
            instance_ids=instance_ids,
            plugin_name=plugin_name,
            key=key,
        )

    def trigger_pre_create_button_callback(
        self, identifier: str, button_name: str
    ) -> None:
        self._trigger_method(
            "trigger_pre_create_button_callback",
            identifier=identifier,
            button_name=button_name,
        )

    def trigger_create_button_callback(
        self,
        button_name: str,
        instance_ids: list[str],
    ) -> None:
        self._trigger_method(
            "trigger_create_button_callback",
            button_name=button_name,
            instance_ids=instance_ids,
        )

    def trigger_publish_button_callback(
        self,
        plugin_name: str,
        button_name: str,
        instance_ids: list[str | None],
    ) -> None:
        self._trigger_method(
            "trigger_publish_button_callback",
            plugin_name=plugin_name,
            button_name=button_name,
            instance_ids=instance_ids,
        )

    def get_product_name(
        self,
        creator_identifier: str,
        product_type: str,
        variant: str,
        folder_path: str | None,
        task_name: str | None,
        instance_id: str | None = None
    ) -> str:
        return self._trigger_getter(
            "get_product_name",
            creator_identifier=creator_identifier,
            product_type=product_type,
            variant=variant,
            folder_path=folder_path,
            task_name=task_name,
            instance_id=instance_id,
        )

    def create(
        self,
        creator_identifier: str,
        product_name: str,
        instance_data: dict[str, Any],
        options: dict[str, Any],
    ) -> bool:
        return self._trigger_getter(
            "create",
            creator_identifier=creator_identifier,
            product_name=product_name,
            instance_data=instance_data,
            options=options,
        )

    def trigger_convertor_items(
        self, convertor_identifiers: list[str]
    ) -> None:
        self._trigger_method(
            "trigger_convertor_items",
            convertor_identifiers=convertor_identifiers,
        )

    def remove_instances(self, instance_ids: list[str]) -> None:
        self._trigger_method(
            "remove_instances",
            instance_ids=instance_ids,
        )

    def save_changes(self) -> bool:
        return self._trigger_getter("save_changes")

    def publish(self) -> None:
        self._trigger_method("publish")

    def validate(self) -> None:
        self._trigger_method("validate")

    def stop_publish(self) -> None:
        self._trigger_method("stop_publish")

    def run_action(self, plugin_id: str, action_id: str) -> None:
        self._trigger_method("run_action", plugin_id, action_id)

    def publish_has_started(self) -> bool:
        return self._trigger_getter("publish_has_started")

    def publish_has_finished(self) -> bool:
        return self._trigger_getter("publish_has_finished")

    def publish_is_running(self) -> bool:
        return self._trigger_getter("publish_is_running")

    def publish_has_validated(self) -> bool:
        return self._trigger_getter("publish_has_validated")

    def publish_can_continue(self):
        return self._trigger_getter("publish_can_continue")

    def publish_has_crashed(self) -> bool:
        return self._trigger_getter("publish_has_crashed")

    def publish_has_validation_errors(self) -> bool:
        return self._trigger_getter("publish_has_validation_errors")

    def get_publish_progress(self) -> int:
        return self._trigger_getter("get_publish_progress")

    def get_publish_max_progress(self) -> int:
        return self._trigger_getter("get_publish_max_progress")

    def get_publish_error_info(self) -> PublishErrorInfo | None:
        return self._trigger_getter("get_publish_error_info")

    def get_publish_report(self) -> PublishReport:
        return self._trigger_getter("get_publish_report")

    def get_publish_report_data(self) -> dict[str, Any]:
        return self._trigger_getter("get_publish_report_data")

    def get_publish_errors_report(self):
        return self._trigger_getter("get_publish_errors_report")

    def store_publish_report(self, filepath: str) -> None:
        self._trigger_method("store_publish_report", filepath=filepath)

    def set_comment(self, comment: str):
        self._trigger_method("set_comment", comment=comment)

    def get_thumbnail_paths_for_instances(
        self, instance_ids: list[str]
    ) -> dict[str, str | None]:
        return self._trigger_getter(
            "get_thumbnail_paths_for_instances",
            instance_ids=instance_ids,
        )

    def set_thumbnail_paths_for_instances(
        self, thumbnail_path_mapping: dict[str, str | None]
    ):
        self._trigger_method(
            "set_thumbnail_paths_for_instances",
            thumbnail_path_mapping=thumbnail_path_mapping,
        )

    def get_thumbnail_temp_dir_path(self) -> str:
        """Path to directory where thumbnails can be temporarily stored.

        Returns:
            str: Path to a directory.
        """
        return self._trigger_getter("get_thumbnail_temp_dir_path")

    def clear_thumbnail_temp_dir_path(self):
        """Remove content of thumbnail temp directory."""
        self._trigger_method("clear_thumbnail_temp_dir_path")

    def _show_window(self, tab: str | None = None):
        if self._window is None:
            self._window = PublisherWindow(controller=self)
            self._window.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)

        if tab is not None:
            self._window.set_current_tab(tab)

        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _handle_request(self, req: RequestMessage) -> None:
        if req.method == "show":
            execute_in_main_thread(self._show_window, **req.params)

        elif req.method == "emit_event":
            execute_in_main_thread(self.emit_event, **req.params)

    def _trigger(
        self,
        method_name: str,
        params: dict[str, Any] | None = None,
        wait: bool = False,
    ) -> Any | None:
        """Trigger method on backend.

        Args:
            method_name (str): Name of method to trigger.
            params (dict | None): Parameters for the method.
            wait (bool): Whether to wait for a response.

        Returns:
            Any: Result of the triggered method.

        """
        response_callback = WaitCallback()
        task = WorkerTask(
            self._com_info.send_request,
            self.channel_name,
            method_name,
            params or {},
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

    def _trigger_method(self, method_name: str, **params) -> Any | None:
        return self._trigger(method_name, params, False)

    def _trigger_getter(self, method_name: str, **params):
        return self._trigger(method_name, params, True)
