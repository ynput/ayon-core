import os
import sys
import copy
import logging
import traceback
import collections
import inspect
from contextlib import contextmanager
from typing import Optional

import pyblish.logic
import pyblish.api
import ayon_api

from ayon_core.settings import get_project_settings
from ayon_core.lib import is_func_signature_supported
from ayon_core.lib.attribute_definitions import get_default_values
from ayon_core.host import IPublishHost, IWorkfileHost
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.plugin_discover import DiscoverResult

from .exceptions import (
    CreatorError,
    CreatorsCreateFailed,
    CreatorsCollectionFailed,
    CreatorsSaveFailed,
    CreatorsRemoveFailed,
    ConvertorsFindFailed,
    ConvertorsConversionFailed,
    UnavailableSharedData,
    HostMissRequiredMethod,
)
from .changes import TrackChangesItem
from .structures import PublishAttributes, ConvertorItem
from .creator_plugins import (
    Creator,
    AutoCreator,
    discover_creator_plugins,
    discover_convertor_plugins,
)

# Import of functions and classes that were moved to different file
# TODO Should be removed in future release - Added 24/08/28, 0.4.3-dev.1
from .exceptions import (
    ImmutableKeyError,  # noqa: F401
    CreatorsOperationFailed,  # noqa: F401
    ConvertorsOperationFailed,  # noqa: F401
)
from .structures import (
    AttributeValues,  # noqa: F401
    CreatorAttributeValues,  # noqa: F401
    PublishAttributeValues,  # noqa: F401
)

# Changes of instances and context are send as tuple of 2 information
UpdateData = collections.namedtuple("UpdateData", ["instance", "changes"])
_NOT_SET = object()


def prepare_failed_convertor_operation_info(identifier, exc_info):
    exc_type, exc_value, exc_traceback = exc_info
    formatted_traceback = "".join(traceback.format_exception(
        exc_type, exc_value, exc_traceback
    ))

    return {
        "convertor_identifier": identifier,
        "message": str(exc_value),
        "traceback": formatted_traceback
    }


def prepare_failed_creator_operation_info(
    identifier, label, exc_info, add_traceback=True
):
    formatted_traceback = None
    exc_type, exc_value, exc_traceback = exc_info
    if add_traceback:
        formatted_traceback = "".join(traceback.format_exception(
            exc_type, exc_value, exc_traceback
        ))

    return {
        "creator_identifier": identifier,
        "creator_label": label,
        "message": str(exc_value),
        "traceback": formatted_traceback
    }


class CreateContext:
    """Context of instance creation.

    Context itself also can store data related to whole creation (workfile).
    - those are mainly for Context publish plugins

    Todos:
        Don't use 'AvalonMongoDB'. It's used only to keep track about current
            context which should be handled by host.

    Args:
        host(ModuleType): Host implementation which handles implementation and
            global metadata.
        headless(bool): Context is created out of UI (Current not used).
        reset(bool): Reset context on initialization.
        discover_publish_plugins(bool): Discover publish plugins during reset
            phase.
    """

    def __init__(
        self, host, headless=False, reset=True, discover_publish_plugins=True
    ):
        self.host = host

        # Prepare attribute for logger (Created on demand in `log` property)
        self._log = None

        # Publish context plugins attributes and it's values
        self._publish_attributes = PublishAttributes(self, {})
        self._original_context_data = {}

        # Validate host implementation
        # - defines if context is capable of handling context data
        host_is_valid = True
        missing_methods = self.get_host_misssing_methods(host)
        if missing_methods:
            host_is_valid = False
            joined_methods = ", ".join(
                ['"{}"'.format(name) for name in missing_methods]
            )
            self.log.warning((
                "Host miss required methods to be able use creation."
                " Missing methods: {}"
            ).format(joined_methods))

        self._current_project_name = None
        self._current_folder_path = None
        self._current_task_name = None
        self._current_workfile_path = None
        self._current_project_settings = None

        self._current_project_entity = _NOT_SET
        self._current_folder_entity = _NOT_SET
        self._current_task_entity = _NOT_SET
        self._current_task_type = _NOT_SET

        self._current_project_anatomy = None

        self._host_is_valid = host_is_valid
        # Currently unused variable
        self.headless = headless

        # Instances by their ID
        self._instances_by_id = {}

        self.creator_discover_result = None
        self.convertor_discover_result = None
        # Discovered creators
        self.creators = {}
        # Prepare categories of creators
        self.autocreators = {}
        # Manual creators
        self.manual_creators = {}
        # Creators that are disabled
        self.disabled_creators = {}

        self.convertors_plugins = {}
        self.convertor_items_by_id = {}

        self.publish_discover_result: Optional[DiscoverResult] = None
        self.publish_plugins_mismatch_targets = []
        self.publish_plugins = []
        self.plugins_with_defs = []
        self._attr_plugins_by_product_type = {}

        # Helpers for validating context of collected instances
        #   - they can be validation for multiple instances at one time
        #       using context manager which will trigger validation
        #       after leaving of last context manager scope
        self._bulk_counter = 0
        self._bulk_instances_to_process = []

        # Shared data across creators during collection phase
        self._collection_shared_data = None

        self.thumbnail_paths_by_instance_id = {}

        # Trigger reset if was enabled
        if reset:
            self.reset(discover_publish_plugins)

    @property
    def instances(self):
        return self._instances_by_id.values()

    @property
    def instances_by_id(self):
        return self._instances_by_id

    @property
    def publish_attributes(self):
        """Access to global publish attributes."""
        return self._publish_attributes

    def get_instance_by_id(self, instance_id):
        """Receive instance by id.

        Args:
            instance_id (str): Instance id.

        Returns:
            Union[CreatedInstance, None]: Instance or None if instance with
                given id is not available.
        """

        return self._instances_by_id.get(instance_id)

    def get_sorted_creators(self, identifiers=None):
        """Sorted creators by 'order' attribute.

        Args:
            identifiers (Iterable[str]): Filter creators by identifiers. All
                creators are returned if 'None' is passed.

        Returns:
            List[BaseCreator]: Sorted creator plugins by 'order' value.
        """

        if identifiers is not None:
            identifiers = set(identifiers)
            creators = [
                creator
                for identifier, creator in self.creators.items()
                if identifier in identifiers
            ]
        else:
            creators = self.creators.values()

        return sorted(
            creators, key=lambda creator: creator.order
        )

    @property
    def sorted_creators(self):
        """Sorted creators by 'order' attribute.

        Returns:
            List[BaseCreator]: Sorted creator plugins by 'order' value.
        """

        return self.get_sorted_creators()

    @property
    def sorted_autocreators(self):
        """Sorted auto-creators by 'order' attribute.

        Returns:
            List[AutoCreator]: Sorted plugins by 'order' value.
        """

        return sorted(
            self.autocreators.values(), key=lambda creator: creator.order
        )

    @classmethod
    def get_host_misssing_methods(cls, host):
        """Collect missing methods from host.

        Args:
            host(ModuleType): Host implementaion.
        """

        missing = set(
            IPublishHost.get_missing_publish_methods(host)
        )
        return missing

    @property
    def host_is_valid(self):
        """Is host valid for creation."""
        return self._host_is_valid

    @property
    def host_name(self):
        if hasattr(self.host, "name"):
            return self.host.name
        return os.environ["AYON_HOST_NAME"]

    def get_current_project_name(self):
        """Project name which was used as current context on context reset.

        Returns:
            Union[str, None]: Project name.
        """

        return self._current_project_name

    def get_current_folder_path(self):
        """Folder path which was used as current context on context reset.

        Returns:
            Union[str, None]: Folder path.
        """

        return self._current_folder_path

    def get_current_task_name(self):
        """Task name which was used as current context on context reset.

        Returns:
            Union[str, None]: Task name.
        """

        return self._current_task_name

    def get_current_task_type(self):
        """Task type which was used as current context on context reset.

        Returns:
            Union[str, None]: Task type.

        """
        if self._current_task_type is _NOT_SET:
            task_type = None
            task_entity = self.get_current_task_entity()
            if task_entity:
                task_type = task_entity["taskType"]
            self._current_task_type = task_type
        return self._current_task_type

    def get_current_project_entity(self):
        """Project entity for current context project.

        Returns:
            Union[dict[str, Any], None]: Folder entity.

        """
        if self._current_project_entity is not _NOT_SET:
            return copy.deepcopy(self._current_project_entity)
        project_entity = None
        project_name = self.get_current_project_name()
        if project_name:
            project_entity = ayon_api.get_project(project_name)
        self._current_project_entity = project_entity
        return copy.deepcopy(self._current_project_entity)

    def get_current_folder_entity(self):
        """Folder entity for current context folder.

        Returns:
            Union[dict[str, Any], None]: Folder entity.

        """
        if self._current_folder_entity is not _NOT_SET:
            return copy.deepcopy(self._current_folder_entity)
        folder_entity = None
        folder_path = self.get_current_folder_path()
        if folder_path:
            project_name = self.get_current_project_name()
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path
            )
        self._current_folder_entity = folder_entity
        return copy.deepcopy(self._current_folder_entity)

    def get_current_task_entity(self):
        """Task entity for current context task.

        Returns:
            Union[dict[str, Any], None]: Task entity.

        """
        if self._current_task_entity is not _NOT_SET:
            return copy.deepcopy(self._current_task_entity)
        task_entity = None
        task_name = self.get_current_task_name()
        if task_name:
            folder_entity = self.get_current_folder_entity()
            if folder_entity:
                project_name = self.get_current_project_name()
                task_entity = ayon_api.get_task_by_name(
                    project_name,
                    folder_id=folder_entity["id"],
                    task_name=task_name
                )
        self._current_task_entity = task_entity
        return copy.deepcopy(self._current_task_entity)

    def get_current_workfile_path(self):
        """Workfile path which was opened on context reset.

        Returns:
            Union[str, None]: Workfile path.
        """

        return self._current_workfile_path

    def get_current_project_anatomy(self):
        """Project anatomy for current project.

        Returns:
            Anatomy: Anatomy object ready to be used.
        """

        if self._current_project_anatomy is None:
            self._current_project_anatomy = Anatomy(
                self._current_project_name)
        return self._current_project_anatomy

    def get_current_project_settings(self):
        if self._current_project_settings is None:
            self._current_project_settings = get_project_settings(
                self.get_current_project_name())
        return self._current_project_settings

    @property
    def context_has_changed(self):
        """Host context has changed.

        As context is used project, folder, task name and workfile path if
        host does support workfiles.

        Returns:
            bool: Context changed.
        """

        project_name, folder_path, task_name, workfile_path = (
            self._get_current_host_context()
        )
        return (
            self._current_project_name != project_name
            or self._current_folder_path != folder_path
            or self._current_task_name != task_name
            or self._current_workfile_path != workfile_path
        )

    project_name = property(get_current_project_name)
    project_anatomy = property(get_current_project_anatomy)

    @property
    def log(self):
        """Dynamic access to logger."""
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    def reset(self, discover_publish_plugins=True):
        """Reset context with all plugins and instances.

        All changes will be lost if were not saved explicitely.
        """

        self.reset_preparation()

        self.reset_current_context()
        self.reset_plugins(discover_publish_plugins)
        self.reset_context_data()

        with self.bulk_instances_collection():
            self.reset_instances()
            self.find_convertor_items()
            self.execute_autocreators()

        self.reset_finalization()

    def refresh_thumbnails(self):
        """Cleanup thumbnail paths.

        Remove all thumbnail filepaths that are empty or lead to files which
        does not exists or of instances that are not available anymore.
        """

        invalid = set()
        for instance_id, path in self.thumbnail_paths_by_instance_id.items():
            instance_available = True
            if instance_id is not None:
                instance_available = instance_id in self._instances_by_id

            if (
                not instance_available
                or not path
                or not os.path.exists(path)
            ):
                invalid.add(instance_id)

        for instance_id in invalid:
            self.thumbnail_paths_by_instance_id.pop(instance_id)

    def reset_preparation(self):
        """Prepare attributes that must be prepared/cleaned before reset."""

        # Give ability to store shared data for collection phase
        self._collection_shared_data = {}

    def reset_finalization(self):
        """Cleanup of attributes after reset."""

        # Stop access to collection shared data
        self._collection_shared_data = None
        self.refresh_thumbnails()

    def _get_current_host_context(self):
        project_name = folder_path = task_name = workfile_path = None
        if hasattr(self.host, "get_current_context"):
            host_context = self.host.get_current_context()
            if host_context:
                project_name = host_context.get("project_name")
                folder_path = host_context.get("folder_path")
                task_name = host_context.get("task_name")

        if isinstance(self.host, IWorkfileHost):
            workfile_path = self.host.get_current_workfile()

        return project_name, folder_path, task_name, workfile_path

    def reset_current_context(self):
        """Refresh current context.

        Reset is based on optional host implementation of `get_current_context`
        function.

        Some hosts have ability to change context file without using workfiles
        tool but that change is not propagated to 'os.environ'.

        Todos:
            UI: Current context should be also checked on save - compare
                initial values vs. current values.
            Related to UI checks: Current workfile can be also considered
                as current context information as that's where the metadata
                are stored. We should store the workfile (if is available) too.
        """

        project_name, folder_path, task_name, workfile_path = (
            self._get_current_host_context()
        )

        self._current_project_name = project_name
        self._current_folder_path = folder_path
        self._current_task_name = task_name
        self._current_workfile_path = workfile_path

        self._current_project_entity = _NOT_SET
        self._current_folder_entity = _NOT_SET
        self._current_task_entity = _NOT_SET
        self._current_task_type = _NOT_SET

        self._current_project_anatomy = None
        self._current_project_settings = None

    def reset_plugins(self, discover_publish_plugins=True):
        """Reload plugins.

        Reloads creators from preregistered paths and can load publish plugins
        if it's enabled on context.
        """

        self._reset_publish_plugins(discover_publish_plugins)
        self._reset_creator_plugins()
        self._reset_convertor_plugins()

    def _reset_publish_plugins(self, discover_publish_plugins):
        from ayon_core.pipeline import AYONPyblishPluginMixin
        from ayon_core.pipeline.publish import (
            publish_plugins_discover
        )

        # Reset publish plugins
        self._attr_plugins_by_product_type = {}

        discover_result = DiscoverResult(pyblish.api.Plugin)
        plugins_with_defs = []
        plugins_by_targets = []
        plugins_mismatch_targets = []
        if discover_publish_plugins:
            discover_result = publish_plugins_discover()
            publish_plugins = discover_result.plugins

            targets = set(pyblish.logic.registered_targets())
            targets.add("default")
            plugins_by_targets = pyblish.logic.plugins_by_targets(
                publish_plugins, list(targets)
            )

            # Collect plugins that can have attribute definitions
            for plugin in publish_plugins:
                if AYONPyblishPluginMixin in inspect.getmro(plugin):
                    plugins_with_defs.append(plugin)

            plugins_mismatch_targets = [
                plugin
                for plugin in publish_plugins
                if plugin not in plugins_by_targets
            ]

        self.publish_plugins_mismatch_targets = plugins_mismatch_targets
        self.publish_discover_result = discover_result
        self.publish_plugins = plugins_by_targets
        self.plugins_with_defs = plugins_with_defs

    def _reset_creator_plugins(self):
        # Prepare settings
        project_settings = self.get_current_project_settings()

        # Discover and prepare creators
        creators = {}
        disabled_creators = {}
        autocreators = {}
        manual_creators = {}
        report = discover_creator_plugins(return_report=True)
        self.creator_discover_result = report
        for creator_class in report.plugins:
            if inspect.isabstract(creator_class):
                self.log.debug(
                    "Skipping abstract Creator {}".format(str(creator_class))
                )
                continue

            creator_identifier = creator_class.identifier
            if creator_identifier in creators:
                self.log.warning(
                    "Duplicate Creator identifier: '%s'. Using first Creator "
                    "and skipping: %s", creator_identifier, creator_class
                )
                continue

            # Filter by host name
            if (
                creator_class.host_name
                and creator_class.host_name != self.host_name
            ):
                self.log.info((
                    "Creator's host name \"{}\""
                    " is not supported for current host \"{}\""
                ).format(creator_class.host_name, self.host_name))
                continue

            creator = creator_class(
                project_settings,
                self,
                self.headless
            )

            if not creator.enabled:
                disabled_creators[creator_identifier] = creator
                continue
            creators[creator_identifier] = creator
            if isinstance(creator, AutoCreator):
                autocreators[creator_identifier] = creator
            elif isinstance(creator, Creator):
                manual_creators[creator_identifier] = creator

        self.autocreators = autocreators
        self.manual_creators = manual_creators

        self.creators = creators
        self.disabled_creators = disabled_creators

    def _reset_convertor_plugins(self):
        convertors_plugins = {}
        report = discover_convertor_plugins(return_report=True)
        self.convertor_discover_result = report
        for convertor_class in report.plugins:
            if inspect.isabstract(convertor_class):
                self.log.info(
                    "Skipping abstract Creator {}".format(str(convertor_class))
                )
                continue

            convertor_identifier = convertor_class.identifier
            if convertor_identifier in convertors_plugins:
                self.log.warning((
                    "Duplicated Converter identifier. "
                    "Using first and skipping following"
                ))
                continue

            convertors_plugins[convertor_identifier] = convertor_class(self)

        self.convertors_plugins = convertors_plugins

    def reset_context_data(self):
        """Reload context data using host implementation.

        These data are not related to any instance but may be needed for whole
        publishing.
        """
        if not self.host_is_valid:
            self._original_context_data = {}
            self._publish_attributes = PublishAttributes(self, {})
            return

        original_data = self.host.get_context_data() or {}
        self._original_context_data = copy.deepcopy(original_data)

        publish_attributes = original_data.get("publish_attributes") or {}

        attr_plugins = self._get_publish_plugins_with_attr_for_context()
        self._publish_attributes = PublishAttributes(
            self, publish_attributes, attr_plugins
        )

    def context_data_to_store(self):
        """Data that should be stored by host function.

        The same data should be returned on loading.
        """
        return {
            "publish_attributes": self._publish_attributes.data_to_store()
        }

    def context_data_changes(self):
        """Changes of attributes."""

        return TrackChangesItem(
            self._original_context_data, self.context_data_to_store()
        )

    def creator_adds_instance(self, instance):
        """Creator adds new instance to context.

        Instances should be added only from creators.

        Args:
            instance(CreatedInstance): Instance with prepared data from
                creator.

        TODO: Rename method to more suit.
        """
        # Add instance to instances list
        if instance.id in self._instances_by_id:
            self.log.warning((
                "Instance with id {} is already added to context."
            ).format(instance.id))
            return

        self._instances_by_id[instance.id] = instance
        # Prepare publish plugin attributes and set it on instance
        attr_plugins = self._get_publish_plugins_with_attr_for_product_type(
            instance.product_type
        )
        instance.set_publish_plugins(attr_plugins)

        # Add instance to be validated inside 'bulk_instances_collection'
        #   context manager if is inside bulk
        with self.bulk_instances_collection():
            self._bulk_instances_to_process.append(instance)

    def _get_creator_in_create(self, identifier):
        """Creator by identifier with unified error.

        Helper method to get creator by identifier with same error when creator
        is not available.

        Args:
            identifier (str): Identifier of creator plugin.

        Returns:
            BaseCreator: Creator found by identifier.

        Raises:
            CreatorError: When identifier is not known.
        """

        creator = self.creators.get(identifier)
        # Fake CreatorError (Could be maybe specific exception?)
        if creator is None:
            raise CreatorError(
                "Creator {} was not found".format(identifier)
            )
        return creator

    def create(
        self,
        creator_identifier,
        variant,
        folder_entity=None,
        task_entity=None,
        pre_create_data=None,
        active=None
    ):
        """Trigger create of plugins with standartized arguments.

        Arguments 'folder_entity' and 'task_name' use current context as
        default values. If only 'task_entity' is provided it will be
        overridden by task name from current context. If 'task_name' is not
        provided when 'folder_entity' is, it is considered that task name is
        not specified, which can lead to error if product name template
        requires task name.

        Args:
            creator_identifier (str): Identifier of creator plugin.
            variant (str): Variant used for product name.
            folder_entity (Dict[str, Any]): Folder entity which define context
                of creation (possible context of created instance/s).
            task_entity (Dict[str, Any]): Task entity.
            pre_create_data (Dict[str, Any]): Pre-create attribute values.
            active (Optional[bool]): Whether the created instance defaults
                to be active or not.

        Returns:
            Any: Output of triggered creator's 'create' method.

        Raises:
            CreatorError: If creator was not found or folder is empty.
        """

        creator = self._get_creator_in_create(creator_identifier)

        project_name = self.project_name
        if folder_entity is None:
            folder_path = self.get_current_folder_path()
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path
            )
            if folder_entity is None:
                raise CreatorError(
                    "Folder '{}' was not found".format(folder_path)
                )

        if task_entity is None:
            current_task_name = self.get_current_task_name()
            if current_task_name:
                task_entity = ayon_api.get_task_by_name(
                    project_name, folder_entity["id"], current_task_name
                )

        if pre_create_data is None:
            pre_create_data = {}

        precreate_attr_defs = []
        # Hidden creators do not have or need the pre-create attributes.
        if isinstance(creator, Creator):
            precreate_attr_defs = creator.get_pre_create_attr_defs()

        # Create default values of precreate data
        _pre_create_data = get_default_values(precreate_attr_defs)
        # Update passed precreate data to default values
        # TODO validate types
        _pre_create_data.update(pre_create_data)

        project_entity = self.get_current_project_entity()
        args = (
            project_name,
            folder_entity,
            task_entity,
            variant,
            self.host_name,
        )
        kwargs = {"project_entity": project_entity}
        # Backwards compatibility for 'project_entity' argument
        # - 'get_product_name' signature changed 24/07/08
        if not is_func_signature_supported(
            creator.get_product_name, *args, **kwargs
        ):
            kwargs.pop("project_entity")
        product_name = creator.get_product_name(*args, **kwargs)

        instance_data = {
            "folderPath": folder_entity["path"],
            "task": task_entity["name"] if task_entity else None,
            "productType": creator.product_type,
            "variant": variant
        }
        if active is not None:
            if not isinstance(active, bool):
                self.log.warning(
                    "CreateContext.create 'active' argument is not a bool. "
                    f"Converting {active} {type(active)} to bool.")
                active = bool(active)
            instance_data["active"] = active

        return creator.create(
            product_name,
            instance_data,
            _pre_create_data
        )

    def _create_with_unified_error(
        self, identifier, creator, *args, **kwargs
    ):
        error_message = "Failed to run Creator with identifier \"{}\". {}"

        label = None
        add_traceback = False
        result = None
        fail_info = None
        exc_info = None
        success = False

        try:
            # Try to get creator and his label
            if creator is None:
                creator = self._get_creator_in_create(identifier)
            label = getattr(creator, "label", label)

            # Run create
            result = creator.create(*args, **kwargs)
            success = True

        except CreatorError:
            exc_info = sys.exc_info()
            self.log.warning(error_message.format(identifier, exc_info[1]))

        except:  # noqa: E722
            add_traceback = True
            exc_info = sys.exc_info()
            self.log.warning(
                error_message.format(identifier, ""),
                exc_info=True
            )

        if not success:
            fail_info = prepare_failed_creator_operation_info(
                identifier, label, exc_info, add_traceback
            )
        return result, fail_info

    def create_with_unified_error(self, identifier, *args, **kwargs):
        """Trigger create but raise only one error if anything fails.

        Added to raise unified exception. Capture any possible issues and
        reraise it with unified information.

        Args:
            identifier (str): Identifier of creator.
            *args (Tuple[Any]): Arguments for create method.
            **kwargs (Dict[Any, Any]): Keyword argument for create method.

        Raises:
            CreatorsCreateFailed: When creation fails due to any possible
                reason. If anything goes wrong this is only possible exception
                the method should raise.
        """

        result, fail_info = self._create_with_unified_error(
            identifier, None, *args, **kwargs
        )
        if fail_info is not None:
            raise CreatorsCreateFailed([fail_info])
        return result

    def _remove_instance(self, instance):
        self._instances_by_id.pop(instance.id, None)

    def creator_removed_instance(self, instance):
        """When creator removes instance context should be acknowledged.

        If creator removes instance conext should know about it to avoid
        possible issues in the session.

        Args:
            instance (CreatedInstance): Object of instance which was removed
                from scene metadata.
        """

        self._remove_instance(instance)

    def add_convertor_item(self, convertor_identifier, label):
        self.convertor_items_by_id[convertor_identifier] = ConvertorItem(
            convertor_identifier, label
        )

    def remove_convertor_item(self, convertor_identifier):
        self.convertor_items_by_id.pop(convertor_identifier, None)

    @contextmanager
    def bulk_instances_collection(self):
        """Validate context of instances in bulk.

        This can be used for single instance or for adding multiple instances
            which is helpfull on reset.

        Should not be executed from multiple threads.
        """
        self._bulk_counter += 1
        try:
            yield
        finally:
            self._bulk_counter -= 1

            # Trigger validation if there is no more context manager for bulk
            #   instance validation
            if self._bulk_counter != 0:
                return

            (
                self._bulk_instances_to_process,
                instances_to_validate
            ) = (
                [],
                self._bulk_instances_to_process
            )
            self.validate_instances_context(instances_to_validate)

    def reset_instances(self):
        """Reload instances"""
        self._instances_by_id = collections.OrderedDict()

        # Collect instances
        error_message = "Collection of instances for creator {} failed. {}"
        failed_info = []
        for creator in self.sorted_creators:
            label = creator.label
            identifier = creator.identifier
            failed = False
            add_traceback = False
            exc_info = None
            try:
                creator.collect_instances()

            except CreatorError:
                failed = True
                exc_info = sys.exc_info()
                self.log.warning(error_message.format(identifier, exc_info[1]))

            except:  # noqa: E722
                failed = True
                add_traceback = True
                exc_info = sys.exc_info()
                self.log.warning(
                    error_message.format(identifier, ""),
                    exc_info=True
                )

            if failed:
                failed_info.append(
                    prepare_failed_creator_operation_info(
                        identifier, label, exc_info, add_traceback
                    )
                )

        if failed_info:
            raise CreatorsCollectionFailed(failed_info)

    def find_convertor_items(self):
        """Go through convertor plugins to look for items to convert.

        Raises:
            ConvertorsFindFailed: When one or more convertors fails during
                finding.
        """

        self.convertor_items_by_id = {}

        failed_info = []
        for convertor in self.convertors_plugins.values():
            try:
                convertor.find_instances()

            except:  # noqa: E722
                failed_info.append(
                    prepare_failed_convertor_operation_info(
                        convertor.identifier, sys.exc_info()
                    )
                )
                self.log.warning(
                    "Failed to find instances of convertor \"{}\"".format(
                        convertor.identifier
                    ),
                    exc_info=True
                )

        if failed_info:
            raise ConvertorsFindFailed(failed_info)

    def execute_autocreators(self):
        """Execute discovered AutoCreator plugins.

        Reset instances if any autocreator executed properly.
        """

        failed_info = []
        for creator in self.sorted_autocreators:
            identifier = creator.identifier
            _, fail_info = self._create_with_unified_error(identifier, creator)
            if fail_info is not None:
                failed_info.append(fail_info)

        if failed_info:
            raise CreatorsCreateFailed(failed_info)

    def validate_instances_context(self, instances=None):
        """Validate 'folder' and 'task' instance context."""
        # Use all instances from context if 'instances' are not passed
        if instances is None:
            instances = tuple(self._instances_by_id.values())

        # Skip if instances are empty
        if not instances:
            return

        project_name = self.project_name

        task_names_by_folder_path = {}
        for instance in instances:
            folder_path = instance.get("folderPath")
            task_name = instance.get("task")
            if folder_path:
                task_names_by_folder_path[folder_path] = set()
                if task_name:
                    task_names_by_folder_path[folder_path].add(task_name)

        # Backwards compatibility for cases where folder name is set instead
        #   of folder path
        folder_names = set()
        folder_paths = set()
        for folder_path in task_names_by_folder_path.keys():
            if folder_path is None:
                pass
            elif "/" in folder_path:
                folder_paths.add(folder_path)
            else:
                folder_names.add(folder_path)

        folder_paths_by_id = {}
        if folder_paths:
            for folder_entity in ayon_api.get_folders(
                project_name,
                folder_paths=folder_paths,
                fields={"id", "path"}
            ):
                folder_id = folder_entity["id"]
                folder_paths_by_id[folder_id] = folder_entity["path"]

        folder_entities_by_name = collections.defaultdict(list)
        if folder_names:
            for folder_entity in ayon_api.get_folders(
                project_name,
                folder_names=folder_names,
                fields={"id", "name", "path"}
            ):
                folder_id = folder_entity["id"]
                folder_name = folder_entity["name"]
                folder_paths_by_id[folder_id] = folder_entity["path"]
                folder_entities_by_name[folder_name].append(folder_entity)

        tasks_entities = ayon_api.get_tasks(
            project_name,
            folder_ids=folder_paths_by_id.keys(),
            fields={"name", "folderId"}
        )

        task_names_by_folder_path = collections.defaultdict(set)
        for task_entity in tasks_entities:
            folder_id = task_entity["folderId"]
            folder_path = folder_paths_by_id[folder_id]
            task_names_by_folder_path[folder_path].add(task_entity["name"])

        for instance in instances:
            if not instance.has_valid_folder or not instance.has_valid_task:
                continue

            folder_path = instance["folderPath"]
            if folder_path and "/" not in folder_path:
                folder_entities = folder_entities_by_name.get(folder_path)
                if len(folder_entities) == 1:
                    folder_path = folder_entities[0]["path"]
                    instance["folderPath"] = folder_path

            if folder_path not in task_names_by_folder_path:
                instance.set_folder_invalid(True)
                continue

            task_name = instance["task"]
            if not task_name:
                continue

            if task_name not in task_names_by_folder_path[folder_path]:
                instance.set_task_invalid(True)

    def save_changes(self):
        """Save changes. Update all changed values."""
        if not self.host_is_valid:
            missing_methods = self.get_host_misssing_methods(self.host)
            raise HostMissRequiredMethod(self.host, missing_methods)

        self._save_context_changes()
        self._save_instance_changes()

    def _save_context_changes(self):
        """Save global context values."""
        changes = self.context_data_changes()
        if changes:
            data = self.context_data_to_store()
            self.host.update_context_data(data, changes)

    def _save_instance_changes(self):
        """Save instance specific values."""
        instances_by_identifier = collections.defaultdict(list)
        for instance in self._instances_by_id.values():
            instance_changes = instance.changes()
            if not instance_changes:
                continue

            identifier = instance.creator_identifier
            instances_by_identifier[identifier].append(
                UpdateData(instance, instance_changes)
            )

        if not instances_by_identifier:
            return

        error_message = "Instances update of creator \"{}\" failed. {}"
        failed_info = []

        for creator in self.get_sorted_creators(
            instances_by_identifier.keys()
        ):
            identifier = creator.identifier
            update_list = instances_by_identifier[identifier]
            if not update_list:
                continue

            label = creator.label
            failed = False
            add_traceback = False
            exc_info = None
            try:
                creator.update_instances(update_list)

            except CreatorError:
                failed = True
                exc_info = sys.exc_info()
                self.log.warning(error_message.format(identifier, exc_info[1]))

            except:  # noqa: E722
                failed = True
                add_traceback = True
                exc_info = sys.exc_info()
                self.log.warning(
                    error_message.format(identifier, ""), exc_info=True)

            if failed:
                failed_info.append(
                    prepare_failed_creator_operation_info(
                        identifier, label, exc_info, add_traceback
                    )
                )
            else:
                for update_data in update_list:
                    instance = update_data.instance
                    instance.mark_as_stored()

        if failed_info:
            raise CreatorsSaveFailed(failed_info)

    def remove_instances(self, instances):
        """Remove instances from context.

        All instances that don't have creator identifier leading to existing
            creator are just removed from context.

        Args:
            instances(List[CreatedInstance]): Instances that should be removed.
                Remove logic is done using creator, which may require to
                do other cleanup than just remove instance from context.
        """

        instances_by_identifier = collections.defaultdict(list)
        for instance in instances:
            identifier = instance.creator_identifier
            instances_by_identifier[identifier].append(instance)

        # Just remove instances from context if creator is not available
        missing_creators = set(instances_by_identifier) - set(self.creators)
        for identifier in missing_creators:
            for instance in instances_by_identifier[identifier]:
                self._remove_instance(instance)

        error_message = "Instances removement of creator \"{}\" failed. {}"
        failed_info = []
        # Remove instances by creator plugin order
        for creator in self.get_sorted_creators(
            instances_by_identifier.keys()
        ):
            identifier = creator.identifier
            creator_instances = instances_by_identifier[identifier]

            label = creator.label
            failed = False
            add_traceback = False
            exc_info = None
            try:
                creator.remove_instances(creator_instances)

            except CreatorError:
                failed = True
                exc_info = sys.exc_info()
                self.log.warning(
                    error_message.format(identifier, exc_info[1])
                )

            except:  # noqa: E722
                failed = True
                add_traceback = True
                exc_info = sys.exc_info()
                self.log.warning(
                    error_message.format(identifier, ""),
                    exc_info=True
                )

            if failed:
                failed_info.append(
                    prepare_failed_creator_operation_info(
                        identifier, label, exc_info, add_traceback
                    )
                )

        if failed_info:
            raise CreatorsRemoveFailed(failed_info)

    def _get_publish_plugins_with_attr_for_product_type(self, product_type):
        """Publish plugin attributes for passed product type.

        Attribute definitions for specific product type are cached.

        Args:
            product_type(str): Instance product type for which should be
                attribute definitions returned.
        """

        if product_type not in self._attr_plugins_by_product_type:
            import pyblish.logic

            filtered_plugins = pyblish.logic.plugins_by_families(
                self.plugins_with_defs, [product_type]
            )
            plugins = []
            for plugin in filtered_plugins:
                if plugin.__instanceEnabled__:
                    plugins.append(plugin)
            self._attr_plugins_by_product_type[product_type] = plugins

        return self._attr_plugins_by_product_type[product_type]

    def _get_publish_plugins_with_attr_for_context(self):
        """Publish plugins attributes for Context plugins.

        Returns:
            List[pyblish.api.Plugin]: Publish plugins that have attribute
                definitions for context.
        """

        plugins = []
        for plugin in self.plugins_with_defs:
            if not plugin.__instanceEnabled__:
                plugins.append(plugin)
        return plugins

    @property
    def collection_shared_data(self):
        """Access to shared data that can be used during creator's collection.

        Returns:
            Dict[str, Any]: Shared data.

        Raises:
            UnavailableSharedData: When called out of collection phase.
        """

        if self._collection_shared_data is None:
            raise UnavailableSharedData(
                "Accessed Collection shared data out of collection phase"
            )
        return self._collection_shared_data

    def run_convertor(self, convertor_identifier):
        """Run convertor plugin by identifier.

        Conversion is skipped if convertor is not available.

        Args:
            convertor_identifier (str): Identifier of convertor.
        """

        convertor = self.convertors_plugins.get(convertor_identifier)
        if convertor is not None:
            convertor.convert()

    def run_convertors(self, convertor_identifiers):
        """Run convertor plugins by identifiers.

        Conversion is skipped if convertor is not available. It is recommended
        to trigger reset after conversion to reload instances.

        Args:
            convertor_identifiers (Iterator[str]): Identifiers of convertors
                to run.

        Raises:
            ConvertorsConversionFailed: When one or more convertors fails.
        """

        failed_info = []
        for convertor_identifier in convertor_identifiers:
            try:
                self.run_convertor(convertor_identifier)

            except:  # noqa: E722
                failed_info.append(
                    prepare_failed_convertor_operation_info(
                        convertor_identifier, sys.exc_info()
                    )
                )
                self.log.warning(
                    "Failed to convert instances of convertor \"{}\"".format(
                        convertor_identifier
                    ),
                    exc_info=True
                )

        if failed_info:
            raise ConvertorsConversionFailed(failed_info)
