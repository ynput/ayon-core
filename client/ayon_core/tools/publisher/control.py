import os
import logging
import tempfile
import shutil
from abc import abstractmethod
import re

import ayon_api

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.lib.profiles_filtering import filter_profiles
from ayon_core.lib.attribute_definitions import UIDef
from ayon_core.pipeline import (
    registered_host,
    get_process_id,
)
from ayon_core.pipeline.create import CreateContext
from ayon_core.pipeline.create.context import (
    CreatorsOperationFailed,
    ConvertorsOperationFailed,
)
from ayon_core.tools.common_models import ProjectsModel, HierarchyModel

from .models import (
    CreatorItem,
    PublishModel,
)
from .abstract import AbstractPublisherController, CardMessageTypes


class BasePublisherController(AbstractPublisherController):
    """Implement common logic for controllers.

    Implement event system, logger and common attributes. Attributes are
    triggering value changes so anyone can listen to their topics.

    Prepare implementation for creator items. Controller must implement just
    their filling by '_collect_creator_items'.

    All prepared implementation is based on calling super '__init__'.
    """

    def __init__(self):
        self._log = None
        self._event_system_obj = None

        self._publish_model = PublishModel(self)

        # Controller must '_collect_creator_items' to fill the value
        self._creator_items = None

    @property
    def log(self):
        """Controller's logger object.

        Returns:
            logging.Logger: Logger object that can be used for logging.
        """

        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    # Events system
    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self._event_system.add_callback(topic, callback)

    def is_host_valid(self) -> bool:
        return self._create_context.host_is_valid

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

    def get_publish_error_msg(self):
        return self._publish_model.get_error_msg()

    def get_creator_items(self):
        """Creators that can be shown in create dialog."""
        if self._creator_items is None:
            self._creator_items = self._collect_creator_items()
        return self._creator_items

    def get_creator_item_by_id(self, identifier):
        items = self.get_creator_items()
        return items.get(identifier)

    @abstractmethod
    def _collect_creator_items(self):
        """Receive CreatorItems to work with.

        Returns:
            Dict[str, CreatorItem]: Creator items by their identifier.
        """

        pass

    def get_creator_icon(self, identifier):
        """Function to receive icon for creator identifier.

        Args:
            str: Creator's identifier for which should be icon returned.
        """

        creator_item = self.get_creator_item_by_id(identifier)
        if creator_item is not None:
            return creator_item.icon
        return None

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

    @property
    def _event_system(self):
        """Inner event system for publisher controller.

        Is used for communication with UI. Event system is autocreated.

        Known topics:
            "show.detailed.help" - Detailed help requested (UI related).
            "show.card.message" - Show card message request (UI related).
            "instances.refresh.finished" - Instances are refreshed.
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

        Returns:
            EventSystem: Event system which can trigger callbacks for topics.
        """

        if self._event_system_obj is None:
            self._event_system_obj = QueuedEventSystem()
        return self._event_system_obj

    def _emit_event(self, topic, data=None):
        self.emit_event(topic, data, "controller")


class PublisherController(BasePublisherController):
    """Middleware between UI, CreateContext and publish Context.

    Handle both creation and publishing parts.

    Args:
        headless (bool): Headless publishing. ATM not implemented or used.
    """

    _log = None

    def __init__(self, headless=False):
        super().__init__()

        self._host = registered_host()
        self._headless = headless

        self._create_context = CreateContext(
            self._host, headless=headless, reset=False
        )

        # State flags to prevent executing method which is already in progress
        self._resetting_plugins = False
        self._resetting_instances = False

        # Cacher of avalon documents
        self._projects_model = ProjectsModel(self)
        self._hierarchy_model = HierarchyModel(self)

    def get_current_project_name(self):
        """Current project context defined by host.

        Returns:
            str: Project name.

        """
        return self._create_context.get_current_project_name()

    def get_current_folder_path(self):
        """Current context folder path defined by host.

        Returns:
            Union[str, None]: Folder path or None if folder is not set.
        """

        return self._create_context.get_current_folder_path()

    def get_current_task_name(self):
        """Current context task name defined by host.

        Returns:
            Union[str, None]: Task name or None if task is not set.
        """

        return self._create_context.get_current_task_name()

    def host_context_has_changed(self):
        return self._create_context.context_has_changed

    @property
    def instances(self):
        """Current instances in create context.

        Deprecated:
            Use 'get_instances' instead. Kept for backwards compatibility with
                traypublisher.

        """
        return self.get_instances()

    def get_instances(self):
        """Current instances in create context."""
        return list(self._create_context.instances_by_id.values())

    def get_instance_by_id(self, instance_id):
        return self._create_context.instances_by_id.get(instance_id)

    def get_instances_by_id(self, instance_ids=None):
        if instance_ids is None:
            instance_ids = self._create_context.instances_by_id.keys()
        return {
            instance_id: self.get_instance_by_id(instance_id)
            for instance_id in instance_ids
        }

    def get_convertor_items(self):
        return self._create_context.convertor_items_by_id

    @property
    def _creators(self):
        """All creators loaded in create context."""

        return self._create_context.creators

    def _get_current_project_settings(self):
        """Current project settings.

        Returns:
            dict
        """

        return self._create_context.get_current_project_settings()

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

    # Publisher custom method
    def get_folder_id_from_path(self, folder_path):
        if not folder_path:
            return None
        folder_item = self._hierarchy_model.get_folder_item_by_path(
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
        for folder_item in folder_items.values():
            task_items = self._hierarchy_model.get_task_items(
                project_name, folder_item.entity_id, None
            )
            output[folder_item.path] = task_items

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

        self._create_context.reset_preparation()

        # Reset current context
        self._create_context.reset_current_context()

        self._hierarchy_model.reset()

        self._reset_plugins()
        # Publish part must be reset after plugins
        self._publish_model.reset(self._create_context)
        self._reset_instances()

        self._create_context.reset_finalization()

        self._emit_event("controller.reset.finished")

        self.emit_card_message("Refreshed..")

    def _reset_plugins(self):
        """Reset to initial state."""
        if self._resetting_plugins:
            return

        self._resetting_plugins = True

        self._create_context.reset_plugins()
        # Reset creator items
        self._creator_items = None

        self._resetting_plugins = False

        self._emit_event("plugins.refresh.finished")

    def _collect_creator_items(self):
        # TODO add crashed initialization of create plugins to report
        output = {}
        allowed_creator_pattern = self._get_allowed_creators_pattern()
        for identifier, creator in self._create_context.creators.items():
            try:
                if self._is_label_allowed(
                    creator.label, allowed_creator_pattern
                ):
                    output[identifier] = CreatorItem.from_creator(creator)
                    continue
                self.log.debug(f"{creator.label} not allowed for context")
            except Exception:
                self.log.error(
                    "Failed to create creator item for '%s'",
                    identifier,
                    exc_info=True
                )

        return output

    def _get_allowed_creators_pattern(self):
        """Provide regex pattern for configured creator labels in this context

        If no profile matches current context, it shows all creators.
        Support usage of regular expressions for configured values.
        Returns:
            (re.Pattern)[optional]: None or regex compiled patterns
                into single one ('Render|Image.*')
        """

        task_type = self._create_context.get_current_task_type()
        project_settings = self._get_current_project_settings()

        filter_creator_profiles = (
            project_settings
            ["core"]
            ["tools"]
            ["creator"]
            ["filter_creator_profiles"]
        )
        filtering_criteria = {
            "task_names": self.get_current_task_name(),
            "task_types": task_type,
            "host_names": self._create_context.host_name
        }
        profile = filter_profiles(
            filter_creator_profiles,
            filtering_criteria,
            logger=self.log
        )

        allowed_creator_pattern = None
        if profile:
            allowed_creator_labels = {
                label
                for label in profile["creator_labels"]
                if label
            }
            self.log.debug(f"Only allowed `{allowed_creator_labels}` creators")
            allowed_creator_pattern = (
                re.compile("|".join(allowed_creator_labels)))
        return allowed_creator_pattern

    def _is_label_allowed(self, label, allowed_labels_regex):
        """Implement regex support for allowed labels.

        Args:
            label (str): Label of creator - shown in Publisher
            allowed_labels_regex (re.Pattern): compiled regular expression
        """
        if not allowed_labels_regex:
            return True
        return bool(allowed_labels_regex.match(label))

    def _reset_instances(self):
        """Reset create instances."""
        if self._resetting_instances:
            return

        self._resetting_instances = True

        self._create_context.reset_context_data()
        with self._create_context.bulk_instances_collection():
            try:
                self._create_context.reset_instances()
            except CreatorsOperationFailed as exc:
                self._emit_event(
                    "instances.collection.failed",
                    {
                        "title": "Instance collection failed",
                        "failed_info": exc.failed_info
                    }
                )

            try:
                self._create_context.find_convertor_items()
            except ConvertorsOperationFailed as exc:
                self._emit_event(
                    "convertors.find.failed",
                    {
                        "title": "Collection of unsupported product failed",
                        "failed_info": exc.failed_info
                    }
                )

            try:
                self._create_context.execute_autocreators()

            except CreatorsOperationFailed as exc:
                self._emit_event(
                    "instances.create.failed",
                    {
                        "title": "AutoCreation failed",
                        "failed_info": exc.failed_info
                    }
                )

        self._resetting_instances = False

        self._on_create_instance_change()

    def get_thumbnail_paths_for_instances(self, instance_ids):
        thumbnail_paths_by_instance_id = (
            self._create_context.thumbnail_paths_by_instance_id
        )
        return {
            instance_id: thumbnail_paths_by_instance_id.get(instance_id)
            for instance_id in instance_ids
        }

    def set_thumbnail_paths_for_instances(self, thumbnail_path_mapping):
        thumbnail_paths_by_instance_id = (
            self._create_context.thumbnail_paths_by_instance_id
        )
        for instance_id, thumbnail_path in thumbnail_path_mapping.items():
            thumbnail_paths_by_instance_id[instance_id] = thumbnail_path

        self._emit_event(
            "instance.thumbnail.changed",
            {
                "mapping": thumbnail_path_mapping
            }
        )

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

    def get_creator_attribute_definitions(self, instances):
        """Collect creator attribute definitions for multuple instances.

        Args:
            instances(List[CreatedInstance]): List of created instances for
                which should be attribute definitions returned.
        """

        # NOTE it would be great if attrdefs would have hash method implemented
        #   so they could be used as keys in dictionary
        output = []
        _attr_defs = {}
        for instance in instances:
            for attr_def in instance.creator_attribute_defs:
                found_idx = None
                for idx, _attr_def in _attr_defs.items():
                    if attr_def == _attr_def:
                        found_idx = idx
                        break

                value = None
                if attr_def.is_value_def:
                    value = instance.creator_attributes[attr_def.key]
                if found_idx is None:
                    idx = len(output)
                    output.append((attr_def, [instance], [value]))
                    _attr_defs[idx] = attr_def
                else:
                    item = output[found_idx]
                    item[1].append(instance)
                    item[2].append(value)
        return output

    def get_publish_attribute_definitions(self, instances, include_context):
        """Collect publish attribute definitions for passed instances.

        Args:
            instances(list<CreatedInstance>): List of created instances for
                which should be attribute definitions returned.
            include_context(bool): Add context specific attribute definitions.
        """

        _tmp_items = []
        if include_context:
            _tmp_items.append(self._create_context)

        for instance in instances:
            _tmp_items.append(instance)

        all_defs_by_plugin_name = {}
        all_plugin_values = {}
        for item in _tmp_items:
            for plugin_name, attr_val in item.publish_attributes.items():
                attr_defs = attr_val.attr_defs
                if not attr_defs:
                    continue

                if plugin_name not in all_defs_by_plugin_name:
                    all_defs_by_plugin_name[plugin_name] = attr_val.attr_defs

                if plugin_name not in all_plugin_values:
                    all_plugin_values[plugin_name] = {}

                plugin_values = all_plugin_values[plugin_name]

                for attr_def in attr_defs:
                    if isinstance(attr_def, UIDef):
                        continue
                    if attr_def.key not in plugin_values:
                        plugin_values[attr_def.key] = []
                    attr_values = plugin_values[attr_def.key]

                    value = attr_val[attr_def.key]
                    attr_values.append((item, value))

        output = []
        for plugin in self._create_context.plugins_with_defs:
            plugin_name = plugin.__name__
            if plugin_name not in all_defs_by_plugin_name:
                continue
            output.append((
                plugin_name,
                all_defs_by_plugin_name[plugin_name],
                all_plugin_values
            ))
        return output

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

        creator = self._creators[creator_identifier]

        instance = None
        if instance_id:
            instance = self.get_instance_by_id(instance_id)

        project_name = self.get_current_project_name()
        folder_item = self._hierarchy_model.get_folder_item_by_path(
            project_name, folder_path
        )
        folder_entity = None
        task_item = None
        task_entity = None
        if folder_item is not None:
            folder_entity = self._hierarchy_model.get_folder_entity(
                project_name, folder_item.entity_id
            )
            task_item = self._hierarchy_model.get_task_item_by_name(
                project_name, folder_item.entity_id, task_name, "controller"
            )

        if task_item is not None:
            task_entity = self._hierarchy_model.get_task_entity(
                project_name, task_item.task_id
            )

        return creator.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            variant,
            instance=instance
        )

    def trigger_convertor_items(self, convertor_identifiers):
        """Trigger legacy item convertors.

        This functionality requires to save and reset CreateContext. The reset
        is needed so Creators can collect converted items.

        Args:
            convertor_identifiers (list[str]): Identifiers of convertor
                plugins.
        """

        success = True
        try:
            self._create_context.run_convertors(convertor_identifiers)

        except ConvertorsOperationFailed as exc:
            success = False
            self._emit_event(
                "convertors.convert.failed",
                {
                    "title": "Conversion failed",
                    "failed_info": exc.failed_info
                }
            )

        if success:
            self.emit_card_message("Conversion finished")
        else:
            self.emit_card_message("Conversion failed", CardMessageTypes.error)

        self.reset()

    def create(
        self, creator_identifier, product_name, instance_data, options
    ):
        """Trigger creation and refresh of instances in UI."""

        success = True
        try:
            self._create_context.create_with_unified_error(
                creator_identifier, product_name, instance_data, options
            )

        except CreatorsOperationFailed as exc:
            success = False
            self._emit_event(
                "instances.create.failed",
                {
                    "title": "Creation failed",
                    "failed_info": exc.failed_info
                }
            )

        self._on_create_instance_change()
        return success

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

        if not self._create_context.host_is_valid:
            # TODO remove
            # Fake success save when host is not valid for CreateContext
            #   this is for testing as experimental feature
            return True

        try:
            self._create_context.save_changes()
            if show_message:
                self.emit_card_message("Saved changes..")
            return True

        except CreatorsOperationFailed as exc:
            self._emit_event(
                "instances.save.failed",
                {
                    "title": "Instances save failed",
                    "failed_info": exc.failed_info
                }
            )

        return False

    def remove_instances(self, instance_ids):
        """Remove instances based on instance ids.

        Args:
            instance_ids (List[str]): List of instance ids to remove.
        """

        # QUESTION Expect that instances are really removed? In that case reset
        #    is not required.
        self._remove_instances_from_context(instance_ids)

        self._on_create_instance_change()

    def _remove_instances_from_context(self, instance_ids):
        instances_by_id = self._create_context.instances_by_id
        instances = [
            instances_by_id[instance_id]
            for instance_id in instance_ids
        ]
        try:
            self._create_context.remove_instances(instances)
        except CreatorsOperationFailed as exc:
            self._emit_event(
                "instances.remove.failed",
                {
                    "title": "Instance removement failed",
                    "failed_info": exc.failed_info
                }
            )

    def _on_create_instance_change(self):
        self._emit_event("instances.refresh.finished")

    def get_publish_report(self):
        return self._publish_model.get_publish_report()

    def get_validation_errors(self):
        return self._publish_model.get_validation_errors()

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

    def _start_publish(self, up_validation):
        self._publish_model.set_publish_up_validation(up_validation)
        self._publish_model.start_publish(wait=True)
