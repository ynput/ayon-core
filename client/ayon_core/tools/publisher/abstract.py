from abc import ABC, abstractmethod


class CardMessageTypes:
    standard = None
    info = "info"
    error = "error"


class AbstractPublisherController(ABC):
    """Publisher tool controller.

    Define what must be implemented to be able use Publisher functionality.

    Goal is to have "data driven" controller that can be used to control UI
    running in different process. That lead to some disadvantages like UI can't
    access objects directly but by using wrappers that can be serialized.
    """

    @property
    @abstractmethod
    def log(self):
        """Controller's logger object.

        Returns:
            logging.Logger: Logger object that can be used for logging.
        """

        pass

    @abstractmethod
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        pass

    @abstractmethod
    def register_event_callback(self, topic, callback):
        pass

    @abstractmethod
    def get_current_project_name(self):
        """Current context project name.

        Returns:
            str: Name of project.
        """

        pass

    @abstractmethod
    def get_current_folder_path(self):
        """Current context folder path.

        Returns:
            Union[str, None]: Folder path.

        """
        pass

    @abstractmethod
    def get_current_task_name(self):
        """Current context task name.

        Returns:
            Union[str, None]: Name of task.
        """

        pass

    @abstractmethod
    def host_context_has_changed(self):
        """Host context changed after last reset.

        'CreateContext' has this option available using 'context_has_changed'.

        Returns:
            bool: Context has changed.
        """

        pass

    @abstractmethod
    def is_host_valid(self):
        """Host is valid for creation part.

        Host must have implemented certain functionality to be able create
        in Publisher tool.

        Returns:
            bool: Host can handle creation of instances.
        """

        pass

    @abstractmethod
    def get_instances(self):
        """Collected/created instances.

        Returns:
            List[CreatedInstance]: List of created instances.

        """
        pass

    @abstractmethod
    def get_instance_by_id(self, instance_id):
        pass

    @abstractmethod
    def get_instances_by_id(self, instance_ids=None):
        pass

    @abstractmethod
    def get_context_title(self):
        """Get context title for artist shown at the top of main window.

        Returns:
            Union[str, None]: Context title for window or None. In case of None
                a warning is displayed (not nice for artists).
        """

        pass

    @abstractmethod
    def get_existing_product_names(self, folder_path):
        pass

    @abstractmethod
    def reset(self):
        """Reset whole controller.

        This should reset create context, publish context and all variables
        that are related to it.
        """

        pass

    @abstractmethod
    def get_creator_attribute_definitions(self, instances):
        pass

    @abstractmethod
    def get_publish_attribute_definitions(self, instances, include_context):
        pass

    @abstractmethod
    def get_creator_icon(self, identifier):
        """Receive creator's icon by identifier.

        Args:
            identifier (str): Creator's identifier.

        Returns:
            Union[str, None]: Creator's icon string.
        """

        pass

    @abstractmethod
    def get_product_name(
        self,
        creator_identifier,
        variant,
        task_name,
        folder_path,
        instance_id=None
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
        self, creator_identifier, product_name, instance_data, options
    ):
        """Trigger creation by creator identifier.

        Should also trigger refresh of instanes.

        Args:
            creator_identifier (str): Identifier of Creator plugin.
            product_name (str): Calculated product name.
            instance_data (Dict[str, Any]): Base instance data with variant,
                folder path and task name.
            options (Dict[str, Any]): Data from pre-create attributes.
        """

        pass

    @abstractmethod
    def save_changes(self):
        """Save changes in create context.

        Save can crash because of unexpected errors.

        Returns:
            bool: Save was successful.
        """

        pass

    @abstractmethod
    def remove_instances(self, instance_ids):
        """Remove list of instances from create context."""
        # TODO expect instance ids

        pass

    @abstractmethod
    def publish_has_started(self):
        """Has publishing finished.

        Returns:
            bool: If publishing finished and all plugins were iterated.
        """

        pass

    @abstractmethod
    def publish_has_finished(self):
        """Has publishing finished.

        Returns:
            bool: If publishing finished and all plugins were iterated.
        """

        pass

    @abstractmethod
    def publish_is_running(self):
        """Publishing is running right now.

        Returns:
            bool: If publishing is in progress.
        """

        pass

    @property
    @abstractmethod
    def publish_has_validated(self):
        """Publish validation passed.

        Returns:
            bool: If publishing passed last possible validation order.
        """

        pass

    @property
    @abstractmethod
    def publish_has_crashed(self):
        """Publishing crashed for any reason.

        Returns:
            bool: Publishing crashed.
        """

        pass

    @property
    @abstractmethod
    def publish_has_validation_errors(self):
        """During validation happened at least one validation error.

        Returns:
            bool: Validation error was raised during validation.
        """

        pass

    @abstractmethod
    def get_publish_max_progress(self):
        """Get maximum possible progress number.

        Returns:
            int: Number that can be used as 100% of publish progress bar.
        """

        pass

    @abstractmethod
    def get_publish_progress(self):
        """Current progress number.

        Returns:
            int: Current progress value from 0 to 'publish_max_progress'.
        """

        pass

    @abstractmethod
    def get_publish_error_msg(self):
        """Current error message which cause fail of publishing.

        Returns:
            Union[str, None]: Message which will be showed to artist or
                None.
        """

        pass

    @abstractmethod
    def get_publish_report(self):
        pass

    @abstractmethod
    def get_validation_errors(self):
        pass

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
    def run_action(self, plugin_id, action_id):
        """Trigger pyblish action on a plugin.

        Args:
            plugin_id (str): Id of publish plugin.
            action_id (str): Id of publish action.
        """

        pass

    @abstractmethod
    def get_convertor_items(self):
        pass

    @abstractmethod
    def trigger_convertor_items(self, convertor_identifiers):
        pass

    @abstractmethod
    def get_thumbnail_paths_for_instances(self, instance_ids):
        pass

    @abstractmethod
    def set_thumbnail_paths_for_instances(self, thumbnail_path_mapping):
        pass

    @abstractmethod
    def set_comment(self, comment):
        """Set comment on pyblish context.

        Set "comment" key on current pyblish.api.Context data.

        Args:
            comment (str): Artist's comment.
        """

        pass

    @abstractmethod
    def emit_card_message(
        self, message, message_type=CardMessageTypes.standard
    ):
        """Emit a card message which can have a lifetime.

        This is for UI purposes. Method can be extended to more arguments
        in future e.g. different message timeout or type (color).

        Args:
            message (str): Message that will be showed.
        """

        pass

    @abstractmethod
    def get_thumbnail_temp_dir_path(self):
        """Return path to directory where thumbnails can be temporary stored.

        Returns:
            str: Path to a directory.
        """

        pass

    @abstractmethod
    def clear_thumbnail_temp_dir_path(self):
        """Remove content of thumbnail temp directory."""

        pass
