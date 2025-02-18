import os
import logging
import tempfile
import shutil

import ayon_api

from ayon_core.lib.events import QueuedEventSystem

from ayon_core.pipeline import (
    registered_host,
    get_process_id,
)
from ayon_core.tools.common_models import ProjectsModel, HierarchyModel

from .models import (
    PublishModel,
    CreateModel,
)
from .abstract import (
    AbstractPublisherBackend,
    AbstractPublisherFrontend,
    CardMessageTypes
)


class PublisherController(
    AbstractPublisherBackend,
    AbstractPublisherFrontend,
):
    """Middleware between UI, CreateContext and publish Context.

    Handle both creation and publishing parts.

    Known topics:
        "show.detailed.help" - Detailed help requested (UI related).
        "show.card.message" - Show card message request (UI related).
        # --- Create model ---
        "create.model.reset" - Reset of create model.
        "instances.create.failed" - Creation failed.
        "convertors.convert.failed" - Convertor failed.
        "instances.save.failed" - Save failed.
        "instance.thumbnail.changed" - Thumbnail changed.
        "instances.collection.failed" - Collection of instances failed.
        "convertors.find.failed" - Convertor find failed.
        "instances.create.failed" - Create instances failed.
        "instances.remove.failed" - Remove instances failed.
        "create.context.added.instance" - Create instance added to context.
        "create.context.value.changed" - Create instance or context value
            changed.
        "create.context.pre.create.attrs.changed" - Pre create attributes
            changed.
        "create.context.create.attrs.changed" - Create attributes changed.
        "create.context.publish.attrs.changed" - Publish attributes changed.
        "create.context.removed.instance" - Instance removed from context.
        "create.model.instances.context.changed" - Instances changed context.
            like folder, task or variant.
        # --- Publish model ---
        "plugins.refresh.finished" - Plugins refreshed.
        "publish.reset.finished" - Reset finished.
        "controller.reset.started" - Controller reset started.
        "controller.reset.finished" - Controller reset finished.
        "publish.process.started" - Publishing started. Can be started from
            paused state.
        "publish.process.stopped" - Publishing stopped/paused process.
        "publish.process.plugin.changed" - Plugin state has changed.
        "publish.process.instance.changed" - Instance state has changed.
        "publish.has_validated.changed" - Attr 'publish_has_validated'
            changed.
        "publish.is_running.changed" - Attr 'publish_is_running' changed.
        "publish.has_crashed.changed" - Attr 'publish_has_crashed' changed.
        "publish.publish_error.changed" - Attr 'publish_error'
        "publish.has_validation_errors.changed" - Attr
            'has_validation_errors' changed.
        "publish.max_progress.changed" - Attr 'publish_max_progress'
            changed.
        "publish.progress.changed" - Attr 'publish_progress' changed.
        "publish.finished.changed" - Attr 'publish_has_finished' changed.

    Args:
        headless (bool): Headless publishing. ATM not implemented or used.

    """
    _log = None

    def __init__(self, headless=False):
        super().__init__()

        self._log = None
        self._event_system = self._create_event_system()

        self._host = registered_host()
        self._headless = headless

        self._create_model = CreateModel(self)
        self._publish_model = PublishModel(self)

        # Cacher of avalon documents
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)

    @property
    def log(self):
        """Controller's logger object.

        Returns:
            logging.Logger: Logger object that can be used for logging.
        """

        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    def is_headless(self):
        return self._headless

    def get_host(self):
        return self._host

    def get_create_context(self):
        return self._create_model.get_create_context()

    def is_host_valid(self) -> bool:
        return self._create_model.is_host_valid()

    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def emit_card_message(
        self, message, message_type=CardMessageTypes.standard
    ):
        self._emit_event(
            "show.card.message",
            {
                "message": message,
                "message_type": message_type
            }
        )

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def get_current_project_name(self):
        """Current project context defined by host.

        Returns:
            str: Project name.

        """
        return self._create_model.get_current_project_name()

    def get_current_folder_path(self):
        """Current context folder path defined by host.

        Returns:
            Union[str, None]: Folder path or None if folder is not set.
        """

        return self._create_model.get_current_folder_path()

    def get_current_task_name(self):
        """Current context task name defined by host.

        Returns:
            Union[str, None]: Task name or None if task is not set.
        """

        return self._create_model.get_current_task_name()

    def host_context_has_changed(self):
        return self._create_model.host_context_has_changed()

    def get_creator_items(self):
        """Creators that can be shown in create dialog."""
        return self._create_model.get_creator_items()

    def get_creator_item_by_id(self, identifier):
        return self._create_model.get_creator_item_by_id(identifier)

    def get_creator_icon(self, identifier):
        """Function to receive icon for creator identifier.

        Args:
            identifier (str): Creator's identifier for which should
                be icon returned.

        """
        return self._create_model.get_creator_icon(identifier)

    def get_instance_items(self):
        """Current instances in create context."""
        return self._create_model.get_instance_items()

    # --- Legacy for TrayPublisher ---
    @property
    def instances(self):
        return self.get_instance_items()

    def get_instances(self):
        return self.get_instance_items()

    def get_instances_by_id(self, *args, **kwargs):
        return self.get_instance_items_by_id(*args, **kwargs)

    # ---

    def get_instance_items_by_id(self, instance_ids=None):
        return self._create_model.get_instance_items_by_id(instance_ids)

    def get_instances_context_info(self, instance_ids=None):
        return self._create_model.get_instances_context_info(instance_ids)

    def set_instances_context_info(self, changes_by_instance_id):
        return self._create_model.set_instances_context_info(
            changes_by_instance_id
        )

    def set_instances_active_state(self, active_state_by_id):
        self._create_model.set_instances_active_state(active_state_by_id)

    def get_convertor_items(self):
        return self._create_model.get_convertor_items()

    def get_project_entity(self, project_name):
        return self._projects_model.get_project_entity(project_name)

    def get_folder_type_items(self, project_name, sender=None):
        return self._projects_model.get_folder_type_items(
            project_name, sender
        )

    def get_task_type_items(self, project_name, sender=None):
        return self._projects_model.get_task_type_items(
            project_name, sender
        )

    # Hierarchy model
    def get_folder_items(self, project_name, sender=None):
        return self._hierarchy_model.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_id, sender=None):
        return self._hierarchy_model.get_task_items(
            project_name, folder_id, sender
        )

    def get_folder_entity(self, project_name, folder_id):
        return self._hierarchy_model.get_folder_entity(
            project_name, folder_id
        )

    def get_task_entity(self, project_name, task_id):
        return self._hierarchy_model.get_task_entity(project_name, task_id)

    def get_folder_item_by_path(self, project_name, folder_path):
        return self._hierarchy_model.get_folder_item_by_path(
            project_name, folder_path
        )

    def get_task_item_by_name(
        self, project_name, folder_id, task_name, sender=None
    ):
        return self._hierarchy_model.get_task_item_by_name(
            project_name, folder_id, task_name, sender
        )

    # Publisher custom method
    def get_folder_id_from_path(self, folder_path):
        if not folder_path:
            return None
        folder_item = self.get_folder_item_by_path(
            self.get_current_project_name(), folder_path
        )
        if folder_item:
            return folder_item.entity_id
        return None

    def get_task_items_by_folder_paths(self, folder_paths):
        if not folder_paths:
            return {}

        folder_items = self._hierarchy_model.get_folder_items_by_paths(
            self.get_current_project_name(), folder_paths
        )

        output = {
            folder_path: []
            for folder_path in folder_paths
        }
        project_name = self.get_current_project_name()
        for folder_path, folder_item in folder_items.items():
            task_items = []
            if folder_item is not None:
                task_items = self._hierarchy_model.get_task_items(
                    project_name, folder_item.entity_id, None
                )
            output[folder_path] = task_items

        return output

    def are_folder_paths_valid(self, folder_paths):
        if not folder_paths:
            return True
        folder_paths = set(folder_paths)
        folder_items = self._hierarchy_model.get_folder_items_by_paths(
            self.get_current_project_name(), folder_paths
        )
        for folder_item in folder_items.values():
            if folder_item is None:
                return False
        return True

    # --- Publish specific callbacks ---
    def get_context_title(self):
        """Get context title for artist shown at the top of main window."""

        context_title = None
        if hasattr(self._host, "get_context_title"):
            context_title = self._host.get_context_title()

        if context_title is None:
            context_title = os.environ.get("AYON_APP_NAME")
            if context_title is None:
                context_title = os.environ.get("AYON_HOST_NAME")

        return context_title

    def get_existing_product_names(self, folder_path):
        if not folder_path:
            return None
        project_name = self.get_current_project_name()
        folder_item = self._hierarchy_model.get_folder_item_by_path(
            project_name, folder_path
        )
        if not folder_item:
            return None

        product_entities = ayon_api.get_products(
            project_name,
            folder_ids={folder_item.entity_id},
            fields={"name"}
        )
        return {
            product_entity["name"]
            for product_entity in product_entities
        }

    def reset(self):
        """Reset everything related to creation and publishing."""
        self.stop_publish()

        self._emit_event("controller.reset.started")

        self._hierarchy_model.reset()

        # Publish part must be reset after plugins
        self._create_model.reset()
        self._publish_model.reset()

        self._emit_event("controller.reset.finished")

        self.emit_card_message("Refreshed..")

    def get_thumbnail_paths_for_instances(self, instance_ids):
        return self._create_model.get_thumbnail_paths_for_instances(
            instance_ids
        )

    def set_thumbnail_paths_for_instances(self, thumbnail_path_mapping):
        self._create_model.set_thumbnail_paths_for_instances(
            thumbnail_path_mapping
        )

    def get_thumbnail_temp_dir_path(self):
        """Return path to directory where thumbnails can be temporary stored.

        Returns:
            str: Path to a directory.
        """

        return os.path.join(
            tempfile.gettempdir(),
            "publisher_thumbnails",
            get_process_id()
        )

    def clear_thumbnail_temp_dir_path(self):
        """Remove content of thumbnail temp directory."""

        dirpath = self.get_thumbnail_temp_dir_path()
        if os.path.exists(dirpath):
            shutil.rmtree(dirpath)

    def get_creator_attribute_definitions(self, instance_ids):
        """Collect creator attribute definitions for multuple instances.

        Args:
            instance_ids (List[str]): List of created instances for
                which should be attribute definitions returned.

        """
        return self._create_model.get_creator_attribute_definitions(
            instance_ids
        )

    def set_instances_create_attr_values(self, instance_ids, key, value):
        return self._create_model.set_instances_create_attr_values(
            instance_ids, key, value
        )

    def revert_instances_create_attr_values(self, instance_ids, key):
        self._create_model.revert_instances_create_attr_values(
            instance_ids, key
        )

    def get_publish_attribute_definitions(self, instance_ids, include_context):
        """Collect publish attribute definitions for passed instances.

        Args:
            instance_ids (List[str]): List of created instances for
                which should be attribute definitions returned.
            include_context (bool): Add context specific attribute definitions.

        """
        return self._create_model.get_publish_attribute_definitions(
            instance_ids, include_context
        )

    def set_instances_publish_attr_values(
        self, instance_ids, plugin_name, key, value
    ):
        return self._create_model.set_instances_publish_attr_values(
            instance_ids, plugin_name, key, value
        )

    def revert_instances_publish_attr_values(
        self, instance_ids, plugin_name, key
    ):
        return self._create_model.revert_instances_publish_attr_values(
            instance_ids, plugin_name, key
        )

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

        return self._create_model.get_product_name(
            creator_identifier,
            variant,
            task_name,
            folder_path,
            instance_id=None
        )

    def trigger_convertor_items(self, convertor_identifiers):
        """Trigger legacy item convertors.

        This functionality requires to save and reset CreateContext. The reset
        is needed so Creators can collect converted items.

        Args:
            convertor_identifiers (list[str]): Identifiers of convertor
                plugins.
        """

        self._create_model.trigger_convertor_items(convertor_identifiers)

        self.reset()

    def create(
        self, creator_identifier, product_name, instance_data, options
    ):
        """Trigger creation and refresh of instances in UI."""

        return self._create_model.create(
            creator_identifier, product_name, instance_data, options
        )

    def save_changes(self, show_message=True):
        """Save changes happened during creation.

        Trigger save of changes using host api. This functionality does not
        validate anything. It is required to do checks before this method is
        called to be able to give user actionable response e.g. check of
        context using 'host_context_has_changed'.

        Args:
            show_message (bool): Show message that changes were
                saved successfully.

        Returns:
            bool: Save of changes was successful.

        """
        return self._create_model.save_changes(show_message)

    def remove_instances(self, instance_ids):
        """Remove instances based on instance ids.

        Args:
            instance_ids (List[str]): List of instance ids to remove.

        """
        self._create_model.remove_instances(instance_ids)

    def publish_has_started(self):
        return self._publish_model.has_started()

    def publish_has_finished(self):
        return self._publish_model.has_finished()

    def publish_is_running(self):
        return self._publish_model.is_running()

    def publish_has_validated(self):
        return self._publish_model.has_validated()

    def publish_has_crashed(self):
        return self._publish_model.is_crashed()

    def publish_has_validation_errors(self):
        return self._publish_model.has_validation_errors()

    def publish_can_continue(self):
        return self._publish_model.publish_can_continue()

    def get_publish_max_progress(self):
        return self._publish_model.get_max_progress()

    def get_publish_progress(self):
        return self._publish_model.get_progress()

    def get_publish_error_info(self):
        return self._publish_model.get_error_info()

    def get_publish_report(self):
        return self._publish_model.get_publish_report()

    def get_publish_errors_report(self):
        return self._publish_model.get_publish_errors_report()

    def set_comment(self, comment):
        """Set comment from ui to pyblish context.

        This should be called always before publishing is started but should
        happen only once on first publish start thus variable
        '_publish_comment_is_set' is used to keep track about the information.
        """

        self._publish_model.set_comment(comment)

    def publish(self):
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        self._start_publish(False)

    def validate(self):
        """Run publishing and stop after Validation.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        self._start_publish(True)

    def stop_publish(self):
        """Stop publishing process (any reason)."""
        self._publish_model.stop_publish()

    def run_action(self, plugin_id, action_id):
        self._publish_model.run_action(plugin_id, action_id)

    def _create_event_system(self):
        return QueuedEventSystem()

    def _emit_event(self, topic, data=None):
        self.emit_event(topic, data, "controller")

    def _start_publish(self, up_validation):
        self._publish_model.set_publish_up_validation(up_validation)
        self._publish_model.start_publish(wait=True)
