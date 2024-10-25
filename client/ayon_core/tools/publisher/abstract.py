from abc import ABC, abstractmethod
from typing import (
    Optional,
    Dict,
    List,
    Tuple,
    Any,
    Callable,
    Union,
    Iterable,
    TYPE_CHECKING,
)

from ayon_core.lib import AbstractAttrDef
from ayon_core.host import HostBase
from ayon_core.pipeline.create import (
    CreateContext,
    ConvertorItem,
)
from ayon_core.tools.common_models import (
    FolderItem,
    TaskItem,
    FolderTypeItem,
    TaskTypeItem,
)

if TYPE_CHECKING:
    from .models import CreatorItem, PublishErrorInfo, InstanceItem


class CardMessageTypes:
    standard = None
    info = "info"
    error = "error"


class AbstractPublisherCommon(ABC):
    @abstractmethod
    def register_event_callback(self, topic, callback):
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
        data: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None
    ):
        """Emit event.

        Args:
            topic (str): Event topic used for callbacks filtering.
            data (Optional[dict[str, Any]]): Event data.
            source (Optional[str]): Event source.

        """
        pass

    @abstractmethod
    def emit_card_message(
        self,
        message: str,
        message_type: Optional[str] = CardMessageTypes.standard
    ):
        """Emit a card message which can have a lifetime.

        This is for UI purposes. Method can be extended to more arguments
        in future e.g. different message timeout or type (color).

        Args:
            message (str): Message that will be shown.
            message_type (Optional[str]): Message type.
        """

        pass

    @abstractmethod
    def get_current_project_name(self) -> Union[str, None]:
        """Current context project name.

        Returns:
            str: Name of project.
        """

        pass

    @abstractmethod
    def get_current_folder_path(self) -> Union[str, None]:
        """Current context folder path.

        Returns:
            Union[str, None]: Folder path.

        """
        pass

    @abstractmethod
    def get_current_task_name(self) -> Union[str, None]:
        """Current context task name.

        Returns:
            Union[str, None]: Name of task.
        """

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
    def reset(self):
        """Reset whole controller.

        This should reset create context, publish context and all variables
        that are related to it.
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
    def get_host(self) -> HostBase:
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
        sender: Optional[str] = None
    ) -> Union[TaskItem, None]:
        pass

    @abstractmethod
    def get_project_entity(
        self, project_name: str
    ) -> Union[Dict[str, Any], None]:
        pass

    @abstractmethod
    def get_folder_entity(
        self, project_name: str, folder_id: str
    ) -> Union[Dict[str, Any], None]:
        pass

    @abstractmethod
    def get_folder_item_by_path(
        self, project_name: str, folder_path: str
    ) -> Union[FolderItem, None]:
        pass

    @abstractmethod
    def get_task_entity(
        self, project_name: str, task_id: str
    ) -> Union[Dict[str, Any], None]:
        pass


class AbstractPublisherFrontend(AbstractPublisherCommon):
    @abstractmethod
    def register_event_callback(self, topic: str, callback: Callable):
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
    def get_context_title(self) -> Union[str, None]:
        """Get context title for artist shown at the top of main window.

        Returns:
            Union[str, None]: Context title for window or None. In case of None
                a warning is displayed (not nice for artists).
        """

        pass

    @abstractmethod
    def get_task_items_by_folder_paths(
        self, folder_paths: Iterable[str]
    ) -> Dict[str, List[TaskItem]]:
        pass

    @abstractmethod
    def get_folder_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> List[FolderItem]:
        pass

    @abstractmethod
    def get_task_items(
        self, project_name: str, folder_id: str, sender: Optional[str] = None
    ) -> List[TaskItem]:
        pass

    @abstractmethod
    def get_folder_type_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> List[FolderTypeItem]:
        pass

    @abstractmethod
    def get_task_type_items(
        self, project_name: str, sender: Optional[str] = None
    ) -> List[TaskTypeItem]:
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
    def get_folder_id_from_path(self, folder_path: str) -> Optional[str]:
        """Get folder id from folder path."""
        pass

    # --- Create ---
    @abstractmethod
    def get_creator_items(self) -> Dict[str, "CreatorItem"]:
        """Creator items by identifier.

        Returns:
            Dict[str, CreatorItem]: Creator items that will be shown to user.

        """
        pass

    @abstractmethod
    def get_creator_item_by_id(
        self, identifier: str
    ) -> Optional["CreatorItem"]:
        """Get creator item by identifier.

        Args:
            identifier (str): Create plugin identifier.

        Returns:
            Optional[CreatorItem]: Creator item or None.

        """
        pass

    @abstractmethod
    def get_creator_icon(
        self, identifier: str
    ) -> Union[str, Dict[str, Any], None]:
        """Receive creator's icon by identifier.

        Todos:
            Icon should be part of 'CreatorItem'.

        Args:
            identifier (str): Creator's identifier.

        Returns:
            Union[str, None]: Creator's icon string.
        """

        pass

    @abstractmethod
    def get_convertor_items(self) -> Dict[str, ConvertorItem]:
        """Convertor items by identifier.

        Returns:
            Dict[str, ConvertorItem]: Convertor items that can be triggered
                by user.

        """
        pass

    @abstractmethod
    def get_instance_items(self) -> List["InstanceItem"]:
        """Collected/created instances.

        Returns:
            List[InstanceItem]: List of created instances.

        """
        pass

    @abstractmethod
    def get_instance_items_by_id(
        self, instance_ids: Optional[Iterable[str]] = None
    ) -> Dict[str, Union["InstanceItem", None]]:
        pass

    @abstractmethod
    def get_instances_context_info(
        self, instance_ids: Optional[Iterable[str]] = None
    ):
        pass

    @abstractmethod
    def set_instances_context_info(
        self, changes_by_instance_id: Dict[str, Dict[str, Any]]
    ):
        pass

    @abstractmethod
    def set_instances_active_state(
        self, active_state_by_id: Dict[str, bool]
    ):
        pass

    @abstractmethod
    def get_existing_product_names(self, folder_path: str) -> List[str]:
        pass

    @abstractmethod
    def get_creator_attribute_definitions(
        self, instance_ids: Iterable[str]
    ) -> List[Tuple[AbstractAttrDef, List[str], List[Any]]]:
        pass

    @abstractmethod
    def set_instances_create_attr_values(
        self, instance_ids: Iterable[str], key: str, value: Any
    ):
        pass

    @abstractmethod
    def get_publish_attribute_definitions(
        self,
        instance_ids: Iterable[str],
        include_context: bool
    ) -> List[Tuple[
        str,
        List[AbstractAttrDef],
        Dict[str, List[Tuple[str, Any]]]
    ]]:
        pass

    @abstractmethod
    def set_instances_publish_attr_values(
        self,
        instance_ids: Iterable[str],
        plugin_name: str,
        key: str,
        value: Any
    ):
        pass

    @abstractmethod
    def get_product_name(
        self,
        creator_identifier: str,
        variant: str,
        task_name: Union[str, None],
        folder_path: Union[str, None],
        instance_id: Optional[str] = None
    ):
        """Get product name based on passed data.

        Args:
            creator_identifier (str): Identifier of creator which should be
                responsible for product name creation.
            variant (str): Variant value from user's input.
            task_name (str): Name of task for which is instance created.
            folder_path (str): Folder path for which is instance created.
            instance_id (Union[str, None]): Existing instance id when product
                name is updated.
        """

        pass

    @abstractmethod
    def create(
        self,
        creator_identifier: str,
        product_name: str,
        instance_data: Dict[str, Any],
        options: Dict[str, Any],
    ):
        """Trigger creation by creator identifier.

        Should also trigger refresh of instances.

        Args:
            creator_identifier (str): Identifier of Creator plugin.
            product_name (str): Calculated product name.
            instance_data (Dict[str, Any]): Base instance data with variant,
                folder path and task name.
            options (Dict[str, Any]): Data from pre-create attributes.
        """

        pass

    @abstractmethod
    def trigger_convertor_items(self, convertor_identifiers: List[str]):
        pass

    @abstractmethod
    def remove_instances(self, instance_ids: Iterable[str]):
        """Remove list of instances from create context."""
        # TODO expect instance ids

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
    def publish(self):
        """Trigger publishing without any order limitations."""

        pass

    @abstractmethod
    def validate(self):
        """Trigger publishing which will stop after validation order."""

        pass

    @abstractmethod
    def stop_publish(self):
        """Stop publishing can be also used to pause publishing.

        Pause of publishing is possible only if all plugins successfully
        finished.
        """

        pass

    @abstractmethod
    def run_action(self, plugin_id: str, action_id: str):
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
    def publish_can_continue(self):
        """Publish has still plugins to process and did not crash yet.

        Returns:
            bool: Publishing can continue in processing.

        """
        pass

    @abstractmethod
    def publish_has_crashed(self) -> bool:
        """Publishing crashed for any reason.

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
    def get_publish_error_info(self) -> Optional["PublishErrorInfo"]:
        """Current error message which cause fail of publishing.

        Returns:
            Optional[PublishErrorInfo]: Error info or None.

        """
        pass

    @abstractmethod
    def get_publish_report(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_publish_errors_report(self):
        pass

    @abstractmethod
    def set_comment(self, comment: str):
        """Set comment on pyblish context.

        Set "comment" key on current pyblish.api.Context data.

        Args:
            comment (str): Artist's comment.
        """

        pass

    @abstractmethod
    def get_thumbnail_paths_for_instances(
        self, instance_ids: List[str]
    ) -> Dict[str, Union[str, None]]:
        pass

    @abstractmethod
    def set_thumbnail_paths_for_instances(
        self, thumbnail_path_mapping: Dict[str, Optional[str]]
    ):
        pass

    @abstractmethod
    def get_thumbnail_temp_dir_path(self) -> str:
        """Path to directory where thumbnails can be temporarily stored.

        Returns:
            str: Path to a directory.
        """

        pass

    @abstractmethod
    def clear_thumbnail_temp_dir_path(self):
        """Remove content of thumbnail temp directory."""

        pass
