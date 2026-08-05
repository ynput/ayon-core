from __future__ import annotations

from abc import ABC, abstractmethod
import collections
from dataclasses import dataclass, asdict, field
from typing import (
    Any,
    Callable,
    Iterable,
    TYPE_CHECKING,
)
import uuid

from ayon_core.pipeline.publish import PublishError, KnownPublishError

if TYPE_CHECKING:
    from ayon_core.lib import AbstractAttrDef
    from ayon_core.host import AbstractHost
    from ayon_core.pipeline.create import (
        CreateContext,
        ConvertorItem,
    )
    from ayon_core.pipeline.publish import PublishReport, PublishLogic
    from ayon_core.pipeline.publish.logic import ActionType, PublishErrorInfo

    from ayon_core.tools.common_models import (
        FolderItem,
        TaskItem,
        FolderTypeItem,
        TaskTypeItem,
    )

    from .models import CreatorItem, InstanceItem


@dataclass
class CommentDef:
    """Comment attribute definition."""
    minimum_chars_required: int

    def to_data(self):
        return asdict(self)

    @classmethod
    def from_data(cls, data):
        return cls(**data)


class CardMessageTypes:
    standard = None
    info = "info"
    error = "error"


@dataclass
class PublishAttrDefsInfo:
    plugin_name: str
    attr_defs: list[AbstractAttrDef]
    values: dict[str, list[tuple[str, Any, Any]]]
    instance_ids: list[str | None]


@dataclass
class UIFailInfo:
    message: str
    is_unknown_error: bool

    @classmethod
    def from_exception(cls, exc) -> "UIFailInfo":
        if isinstance(exc, PublishError):
            return cls(exc.message, False)

        if isinstance(exc, KnownPublishError):
            msg = str(exc)
        else:
            msg = (
                "Something went wrong. Send report"
                " to your supervisor or Ynput team."
            )
        return cls(msg, True)

    def to_data(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "is_unknown_error": self.is_unknown_error,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "UIFailInfo":
        return cls(data["message"], data["is_unknown_error"])


@dataclass
class UIPublishPluginActionItem:
    """Representation of publish plugin action.

    Data driven object which is used as proxy for controller and UI.

    Attributes:
        action_id (str): Action id.
        plugin_id (str): Plugin id.
        active (bool): Action is active.
        on_filter (Literal["all", "notProcessed", "processed", "failed",
            "warning", "failedOrWarning", "succeeded"]): Actions have 'on'
            attribute which define  when can be action triggered
            (e.g. 'all', 'failed', ...).
        label (str): Action's label.
        icon (str | None) Action's icon.

    """
    action_id: str
    plugin_id: str
    active: bool
    on_filter: str
    label: str
    icon: str | None

    @classmethod
    def from_action(
        cls, action: ActionType, plugin_id: str
    ) -> "UIPublishPluginActionItem":
        label = action.label or action.__name__
        icon = getattr(action, "icon", None)
        return cls(
            action_id=action.id,
            plugin_id=plugin_id,
            active=action.active,
            on_filter="all",
            label=label,
            icon=icon,
        )

    @classmethod
    def from_data(
        cls, data: dict[str, str | bool | None]
    ) -> "UIPublishPluginActionItem":
        """Create object from data.

        Args:
            data (dict[str, str | bool | None]): Data used to recreate
                object.

        Returns:
            UIPublishPluginActionItem: Object created using data.

        """
        return cls(**data)

    def to_data(self) -> dict[str, str | bool | None]:
        """Serialize object to dictionary.

        Returns:
            dict[str, str | bool | None]: Serialized object.

        """
        return {
            "action_id": self.action_id,
            "plugin_id": self.plugin_id,
            "active": self.active,
            "on_filter": self.on_filter,
            "label": self.label,
            "icon": self.icon
        }


@dataclass
class UIPublishErrorItem:
    """Data driven publish error item.

    Prepared data container with information about publish error and its
    source plugin.

    Can be converted to raw data and recreated should be used for controller
    and UI connection.

    Args:
        instance_id (str | None): Pyblish instance id to which is
            publish error connected.
        instance_label (str | None): Prepared instance label.
        plugin_id (str): Pyblish plugin id which triggered the publish
            error. Id is generated using 'PublishPluginsProxy'.
        is_context_plugin (bool): Error happened on context.
        is_validation_error (bool): Error is a validation error.
        title (str | None): Error title.
        description (str | None): Error description.
        detail (str): Error detail.

    """
    instance_id: str | None
    instance_label: str | None
    plugin_id: str
    is_context_plugin: bool
    is_validation_error: bool
    title: str | None
    description: str | None
    detail: str | None

    @classmethod
    def from_error_item(
        cls, error_info: PublishErrorInfo
    ) -> "UIPublishErrorItem":
        """Create new object based on resukt from controller.

        Returns:
            PublishErrorItem: New object with filled data.
        """
        return cls(
            instance_id=error_info.instance_id,
            instance_label=error_info.instance_label,
            plugin_id=error_info.plugin_id,
            is_context_plugin=error_info.is_context_plugin,
            is_validation_error=error_info.is_validation_error,
            title=error_info.title,
            description=error_info.description,
            detail=error_info.detail,
        )

    def to_data(self) -> dict[str, str | bool | None]:
        """Serialize object to dictionary.

        Returns:
            dict[str, str | bool | None]: Serialized object data.

        """
        return {
            "instance_id": self.instance_id,
            "instance_label": self.instance_label,
            "plugin_id": self.plugin_id,
            "is_context_plugin": self.is_context_plugin,
            "is_validation_error": self.is_validation_error,
            "title": self.title,
            "description": self.description,
            "detail": self.detail,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)


@dataclass
class UIPublishErrorReport:
    plugin_id: str
    title: str
    error_items: list[UIPublishErrorItem]
    plugin_action_items: list[UIPublishPluginActionItem]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    @classmethod
    def get_items_grouped_by_title(
        cls, logic: PublishLogic
    ) -> list[UIPublishErrorReport]:
        """Group errors by plugin and their titles.

        Items are grouped by plugin and title -> same title from different
        plugin is different item. Items are ordered by plugin order.

        Returns:
            list[dict[str, Any]]: List where each item title, instance
                information related to title and possible plugin actions.
        """
        ordered_plugin_ids = []
        error_items_by_plugin_id = collections.defaultdict(list)
        for error_item in logic.iter_all_error_info():
            plugin_id = error_item.plugin_id
            if plugin_id not in ordered_plugin_ids:
                ordered_plugin_ids.append(plugin_id)
            ui_error_item = UIPublishErrorItem.from_error_item(error_item)
            error_items_by_plugin_id[plugin_id].append(ui_error_item)

        grouped_error_items = []
        for plugin_id in ordered_plugin_ids:
            plugin = logic.get_publish_plugin_by_id(plugin_id)
            plugin_action_items = [
                UIPublishPluginActionItem.from_action(
                    action, plugin_id
                )
                for action in logic.get_publish_plugin_actions(plugin)
            ]
            error_items = error_items_by_plugin_id[plugin_id]

            titles = []
            error_items_by_title = collections.defaultdict(list)
            for error_item in error_items:
                title = error_item.title
                if title not in titles:
                    titles.append(error_item.title)
                error_items_by_title[title].append(error_item)

            for title in titles:
                item = UIPublishErrorReport(
                    plugin_id=plugin_id,
                    title=title,
                    error_items=error_items_by_title[title],
                    plugin_action_items=plugin_action_items,
                )
                grouped_error_items.append(item)
        return grouped_error_items

    def to_data(self) -> dict[str, Any]:
        """Serialize object to json supported dictionary."""
        return {
            "id": self.id,
            "plugin_id": self.plugin_id,
            "title": self.title,
            "error_items": [ei.to_data() for ei in self.error_items],
            "plugin_action_items": [
                ai.to_data() for ai in self.plugin_action_items
            ],
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]):
        """Recreate object from data serialized using 'to_data'."""

        return cls(
            id=data["id"],
            plugin_id=data["plugin_id"],
            title=data["title"],
            error_items=[
                UIPublishErrorItem.from_data(ei)
                for ei in data["error_items"]
            ],
            plugin_action_items=[
                UIPublishPluginActionItem.from_data(ai)
                for ai in data["plugin_action_items"]
            ],
        )


class AbstractPublisherCommon(ABC):
    @abstractmethod
    def register_event_callback(self, topic: str, callback: Callable) -> None:
        """Register event callback.

        Listen for events with given topic.

        Args:
            topic (str): Name of topic.
            callback (Callable): Callback that will be called when event
                is triggered.

        """
        pass

    @abstractmethod
    def emit_event(
        self, topic: str,
        data: dict[str, Any] | None = None,
        source: str | None = None
    ) -> None:
        """Emit event.

        Args:
            topic (str): Event topic used for callbacks filtering.
            data (dict[str, Any] | None): Event data.
            source (str | None): Event source.

        """
        pass

    @abstractmethod
    def emit_card_message(
        self,
        message: str,
        message_type: str | None = CardMessageTypes.standard
    ) -> None:
        """Emit a card message which can have a lifetime.

        This is for UI purposes. Method can be extended to more arguments
        in future e.g. different message timeout or type (color).

        Args:
            message (str): Message that will be shown.
            message_type (Optional[str]): Message type.

        """
        pass

    @abstractmethod
    def get_current_project_name(self) -> str | None:
        """Current context project name.

        Returns:
            str: Name of project.

        """
        pass

    @abstractmethod
    def get_current_folder_path(self) -> str | None:
        """Current context folder path.

        Returns:
            str | None: Folder path.

        """
        pass

    @abstractmethod
    def get_current_task_name(self) -> str | None:
        """Current context task name.

        Returns:
            str | None: Name of task.

        """
        pass

    @abstractmethod
    def get_project_settings(self, project_name: str | None) -> dict:
        pass

    @abstractmethod
    def host_context_has_changed(self) -> bool:
        """Host context changed after last reset.

        'CreateContext' has this option available using 'context_has_changed'.

        Returns:
            bool: Context has changed.

        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset whole controller.

        This should reset create context, publish context and all variables
        that are related to it.

        """
        pass

    @abstractmethod
    def get_comment_def(self) -> CommentDef:
        """Get comment attribute definition.

        This can define how the Comment field should behave, like having
        a minimum amount of required characters before being allowed to
        publish.

        """
        pass


class AbstractPublisherBackend(AbstractPublisherCommon):
    @abstractmethod
    def is_headless(self) -> bool:
        """Controller is in headless mode.

        Notes:
            Not sure if this method is relevant in UI tool?

        Returns:
            bool: Headless mode.

        """
        pass

    @abstractmethod
    def get_host(self) -> AbstractHost:
        pass

    @abstractmethod
    def get_create_context(self) -> CreateContext:
        pass

    @abstractmethod
    def get_task_item_by_name(
        self,
        project_name: str,
        folder_id: str,
        task_name: str,
        sender: str | None = None
    ) -> TaskItem | None:
        pass

    @abstractmethod
    def get_project_entity(
        self, project_name: str
    ) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def get_folder_entity(
        self, project_name: str, folder_id: str
    ) -> dict[str, Any] | None:
        pass

    @abstractmethod
    def get_folder_item_by_path(
        self, project_name: str, folder_path: str
    ) -> FolderItem | None:
        pass

    @abstractmethod
    def get_task_entity(
        self, project_name: str, task_id: str
    ) -> dict[str, Any] | None:
        pass


class AbstractPublisherFrontend(AbstractPublisherCommon):
    @abstractmethod
    def get_window_subtitle(self) -> str | None:
        """Get window subtitle.

        Returns:
            str | None: Window subtitle.

        """

    @abstractmethod
    def register_event_callback(self, topic: str, callback: Callable) -> None:
        pass

    @abstractmethod
    def is_host_valid(self) -> bool:
        """Host is valid for creation part.

        Host must have implemented certain functionality to be able to create
            in Publisher tool.

        Returns:
            bool: Host can handle creation of instances.

        """
        pass

    @abstractmethod
    def get_context_title(self) -> str | None:
        """Get context title for artist shown at the top of main window.

        Returns:
            str | None: Context title for window or None. In case of None
                a warning is displayed (not nice for artists).

        """
        pass

    @abstractmethod
    def get_task_items_by_folder_paths(
        self, folder_paths: Iterable[str]
    ) -> dict[str, list[TaskItem]]:
        pass

    @abstractmethod
    def get_folder_items(
        self, project_name: str, sender: str | None = None
    ) -> list[FolderItem]:
        pass

    @abstractmethod
    def get_task_items(
        self, project_name: str, folder_id: str, sender: str | None = None
    ) -> list[TaskItem]:
        pass

    @abstractmethod
    def get_folder_type_items(
        self, project_name: str, sender: str | None = None
    ) -> list[FolderTypeItem]:
        pass

    @abstractmethod
    def get_task_type_items(
        self, project_name: str, sender: str | None = None
    ) -> list[TaskTypeItem]:
        pass

    @abstractmethod
    def are_folder_paths_valid(self, folder_paths: Iterable[str]) -> bool:
        """Folder paths do exist in project.

        Args:
            folder_paths (Iterable[str]): List of folder paths.

        Returns:
            bool: All folder paths exist in project.

        """
        pass

    @abstractmethod
    def get_folder_id_from_path(self, folder_path: str) -> str | None:
        """Get folder id from folder path."""
        pass

    @abstractmethod
    def get_my_tasks_entity_ids(
        self, project_name: str
    ) -> dict[str, list[str]]:
        """Get entity ids for my tasks.

        Args:
            project_name (str): Project name.

        Returns:
            dict[str, list[str]]: Folder and task ids.

        """
        pass

    # --- Create ---
    @abstractmethod
    def get_creator_items(self) -> dict[str, CreatorItem]:
        """Creator items by identifier.

        Returns:
            dict[str, CreatorItem]: Creator items that will be shown to user.

        """
        pass

    @abstractmethod
    def get_creator_item_by_id(
        self, identifier: str
    ) -> CreatorItem | None:
        """Get creator item by identifier.

        Args:
            identifier (str): Create plugin identifier.

        Returns:
            CreatorItem | None: Creator item or None.

        """
        pass

    @abstractmethod
    def get_creator_icon(
        self, identifier: str
    ) -> str | dict[str, Any] | None:
        """Receive creator's icon by identifier.

        Todos:
            Icon should be part of 'CreatorItem'.

        Args:
            identifier (str): Creator's identifier.

        Returns:
            str | dict[str, Any] | None: Creator's icon string.

        """
        pass

    @abstractmethod
    def get_convertor_items(self) -> dict[str, ConvertorItem]:
        """Convertor items by identifier.

        Returns:
            dict[str, ConvertorItem]: Convertor items that can be triggered
                by user.

        """
        pass

    @abstractmethod
    def get_instance_items(self) -> list[InstanceItem]:
        """Collected/created instances.

        Returns:
            list[InstanceItem]: List of created instances.

        """
        pass

    @abstractmethod
    def get_instance_items_by_id(
        self, instance_ids: Iterable[str] | None = None
    ) -> dict[str, InstanceItem | None]:
        pass

    @abstractmethod
    def get_instances_context_info(
        self, instance_ids: Iterable[str] | None = None
    ):
        pass

    @abstractmethod
    def set_instances_context_info(
        self, changes_by_instance_id: dict[str, dict[str, Any]]
    ) -> None:
        pass

    @abstractmethod
    def set_instances_active_state(
        self, active_state_by_id: dict[str, bool]
    ) -> None:
        pass

    @abstractmethod
    def get_existing_product_names(self, folder_path: str) -> list[str]:
        pass

    @abstractmethod
    def get_creator_attribute_definitions(
        self, instance_ids: Iterable[str]
    ) -> list[tuple[AbstractAttrDef, dict[str, dict[str, Any]]]]:
        pass

    @abstractmethod
    def set_instances_create_attr_values(
        self, instance_ids: Iterable[str], key: str, value: Any
    ) -> None:
        pass

    @abstractmethod
    def revert_instances_create_attr_values(
        self,
        instance_ids: list[str | None],
        key: str,
    ) -> None:
        pass

    @abstractmethod
    def get_publish_attribute_definitions(
        self,
        instance_ids: Iterable[str],
        include_context: bool
    ) -> list[PublishAttrDefsInfo]:
        pass

    @abstractmethod
    def set_instances_publish_attr_values(
        self,
        instance_ids: Iterable[str],
        plugin_name: str,
        key: str,
        value: Any
    ) -> None:
        pass

    @abstractmethod
    def revert_instances_publish_attr_values(
        self,
        instance_ids: list[str | None],
        plugin_name: str,
        key: str,
    ) -> None:
        pass

    @abstractmethod
    def trigger_pre_create_button_callback(
        self, identifier: str, button_name: str
    ) -> None:
        pass

    @abstractmethod
    def trigger_create_button_callback(
        self,
        button_name: str,
        instance_ids: list[str],
    ) -> None:
        pass

    @abstractmethod
    def trigger_publish_button_callback(
        self,
        plugin_name: str,
        button_name: str,
        instance_ids: list[str | None],
    ) -> None:
        pass

    @abstractmethod
    def get_product_name(
        self,
        creator_identifier: str,
        product_type: str,
        variant: str,
        folder_path: str | None,
        task_name: str | None,
        instance_id: str | None = None
    ):
        """Get product name based on passed data.

        Args:
            creator_identifier (str): Identifier of creator which should be
                responsible for product name creation.
            product_type (str): Product type.
            variant (str): Variant value from user's input.
            folder_path (str | None): Folder path for which
                is instance created.
            task_name (str | None): Name of task for which
                is instance created.
            instance_id (str | None): Existing instance id when product
                name is updated.

        """
        pass

    @abstractmethod
    def create(
        self,
        creator_identifier: str,
        product_name: str,
        instance_data: dict[str, Any],
        options: dict[str, Any],
    ) -> None:
        """Trigger creation by creator identifier.

        Should also trigger refresh of instances.

        Args:
            creator_identifier (str): Identifier of Creator plugin.
            product_name (str): Calculated product name.
            instance_data (dict[str, Any]): Base instance data with variant,
                folder path and task name.
            options (dict[str, Any]): Data from pre-create attributes.

        """
        pass

    @abstractmethod
    def trigger_convertor_items(
        self, convertor_identifiers: list[str]
    ) -> None:
        pass

    @abstractmethod
    def remove_instances(self, instance_ids: Iterable[str]) -> None:
        """Remove list of instances from create context."""
        pass

    @abstractmethod
    def save_changes(self) -> bool:
        """Save changes in create context.

        Save can crash because of unexpected errors.

        Returns:
            bool: Save was successful.

        """
        pass

    # --- Publish ---
    @abstractmethod
    def publish(self) -> None:
        """Trigger publishing without any order limitations."""
        pass

    @abstractmethod
    def validate(self) -> None:
        """Trigger publishing which will stop after validation order."""
        pass

    @abstractmethod
    def stop_publish(self) -> None:
        """Stop publishing can be also used to pause publishing.

        Pause of publishing is possible only if all plugins successfully
        finished.
        """
        pass

    @abstractmethod
    def run_action(self, plugin_id: str, action_id: str) -> None:
        """Trigger pyblish action on a plugin.

        Args:
            plugin_id (str): Publish plugin id.
            action_id (str): Publish action id.

        """
        pass

    @abstractmethod
    def publish_has_started(self) -> bool:
        """Has publishing finished.

        Returns:
            bool: If publishing finished and all plugins were iterated.

        """
        pass

    @abstractmethod
    def publish_has_finished(self) -> bool:
        """Has publishing finished.

        Returns:
            bool: If publishing finished and all plugins were iterated.

        """
        pass

    @abstractmethod
    def publish_is_running(self) -> bool:
        """Publishing is running right now.

        Returns:
            bool: If publishing is in progress.

        """
        pass

    @abstractmethod
    def publish_has_validated(self) -> bool:
        """Publish validation passed.

        Returns:
            bool: If publishing passed last possible validation order.

        """
        pass

    @abstractmethod
    def publish_can_continue(self) -> bool:
        """Publish has still plugins to process and did not crash yet.

        Returns:
            bool: Publishing can continue in processing.

        """
        pass

    @abstractmethod
    def publish_has_crashed(self) -> bool:
        """Publishing crashed with an error during process iteration.

        Returns:
            bool: Publishing crashed.

        """
        pass

    @abstractmethod
    def publish_has_validation_errors(self) -> bool:
        """During validation happened at least one validation error.

        Returns:
            bool: Validation error was raised during validation.

        """
        pass

    @abstractmethod
    def get_publish_progress(self) -> int:
        """Current progress number.

        Returns:
            int: Current progress value from 0 to 'publish_max_progress'.
        """

        pass

    @abstractmethod
    def get_publish_max_progress(self) -> int:
        """Get maximum possible progress number.

        Returns:
            int: Number that can be used as 100% of publish progress bar.

        """
        pass

    @abstractmethod
    def get_publish_fail_info(self) -> UIFailInfo | None:
        """Current error message which cause fail of publishing.

        Returns:
            UIFailInfo | None: Error info or None.

        """
        pass

    @abstractmethod
    def get_publish_report(self) -> PublishReport:
        pass

    @abstractmethod
    def get_publish_report_data(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def get_publish_errors_reports(self) -> list[UIPublishErrorReport]:
        pass

    @abstractmethod
    def store_publish_report(self, filepath: str) -> None:
        pass

    @abstractmethod
    def set_comment(self, comment: str) -> None:
        """Set comment on pyblish context.

        Set "comment" key on current pyblish.api.Context data.

        Args:
            comment (str): Artist's comment.

        """
        pass

    @abstractmethod
    def get_thumbnail_paths_for_instances(
        self, instance_ids: list[str]
    ) -> dict[str, str | None]:
        pass

    @abstractmethod
    def set_thumbnail_paths_for_instances(
        self, thumbnail_path_mapping: dict[str, str | None]
    ) -> None:
        pass

    @abstractmethod
    def get_thumbnail_temp_dir_path(self) -> str:
        """Path to directory where thumbnails can be temporarily stored.

        Returns:
            str: Path to a directory.

        """
        pass

    @abstractmethod
    def clear_thumbnail_temp_dir_path(self) -> None:
        """Remove content of thumbnail temp directory."""
        pass
