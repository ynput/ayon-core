"""Workfile build mechanism using workfile templates.

Build templates are manually prepared using plugin definitions which create
placeholders inside the template which are populated on import.

This approach is very explicit to achieve very specific build logic that can be
targeted by task types and names.

Placeholders are created using placeholder plugins which should care about
logic and data of placeholder items. 'PlaceholderItem' is used to keep track
about its progress.
"""

import os
import re
import collections
import copy
from abc import ABC, abstractmethod

import ayon_api
from ayon_api import (
    get_folders,
    get_folder_by_path,
    get_folder_links,
    get_task_by_name,
    get_products,
    get_last_versions,
    get_representations,
)

from ayon_core.settings import get_project_settings
from ayon_core.host import IWorkfileHost, HostBase
from ayon_core.lib import (
    Logger,
    StringTemplate,
    filter_profiles,
    attribute_definitions,
)
from ayon_core.lib.events import EventSystem, EventCallback, Event
from ayon_core.lib.attribute_definitions import get_attributes_keys
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.load import (
    get_loaders_by_name,
    get_representation_contexts,
    load_with_repre_context,
)
from ayon_core.pipeline.plugin_discover import (
    discover,
    register_plugin,
    register_plugin_path,
    deregister_plugin,
    deregister_plugin_path
)

from ayon_core.pipeline.create import (
    discover_legacy_creator_plugins,
    CreateContext,
    HiddenCreator,
)

_NOT_SET = object()


class EntityResolutionError(Exception):
    """Exception raised when entity URI resolution fails."""


def resolve_entity_uri(entity_uri: str) -> str:
    """Resolve AYON entity URI to a filesystem path for local system."""
    response = ayon_api.post(
        "resolve",
        resolveRoots=True,
        uris=[entity_uri]
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Unable to resolve AYON entity URI filepath for "
            f"'{entity_uri}': {response.text}"
        )

    entities = response.data[0]["entities"]
    if len(entities) != 1:
        raise EntityResolutionError(
            f"Unable to resolve AYON entity URI '{entity_uri}' to a "
            f"single filepath. Received data: {response.data}"
        )
    return entities[0]["filePath"]


class TemplateNotFound(Exception):
    """Exception raised when template does not exist."""
    pass


class TemplateProfileNotFound(Exception):
    """Exception raised when current profile
    doesn't match any template profile"""
    pass


class TemplateAlreadyImported(Exception):
    """Error raised when Template was already imported by host for
    this session"""
    pass


class TemplateLoadFailed(Exception):
    """Error raised whend Template loader was unable to load the template"""
    pass


class AbstractTemplateBuilder(ABC):
    """Abstraction of Template Builder.

    Builder cares about context, shared data, cache, discovery of plugins
    and trigger logic. Provides public api for host workfile build system.

    Rest of logic is based on plugins that care about collection and creation
    of placeholder items.

    Population of placeholders happens in loops. Each loop will collect all
    available placeholders, skip already populated, and populate the rest.

    Builder item has 2 types of shared data. Refresh lifetime which are cleared
    on refresh and populate lifetime which are cleared after loop of
    placeholder population.

    Args:
        host (Union[HostBase, ModuleType]): Implementation of host.
    """

    _log = None
    use_legacy_creators = False

    def __init__(self, host):
        # Get host name
        if isinstance(host, HostBase):
            host_name = host.name
        else:
            host_name = os.environ.get("AYON_HOST_NAME")

        self._host = host
        self._host_name = host_name

        # Shared data across placeholder plugins
        self._shared_data = {}
        self._shared_populate_data = {}

        # Where created objects of placeholder plugins will be stored
        self._placeholder_plugins = None
        self._loaders_by_name = None
        self._creators_by_name = None
        self._create_context = None

        self._project_settings = None

        self._current_folder_entity = _NOT_SET
        self._current_task_entity = _NOT_SET
        self._linked_folder_entities = _NOT_SET

        self._event_system = EventSystem()

    @property
    def project_name(self):
        if isinstance(self._host, HostBase):
            return self._host.get_current_project_name()
        return os.getenv("AYON_PROJECT_NAME")

    @property
    def current_folder_path(self):
        if isinstance(self._host, HostBase):
            return self._host.get_current_folder_path()
        return os.getenv("AYON_FOLDER_PATH")

    @property
    def current_task_name(self):
        if isinstance(self._host, HostBase):
            return self._host.get_current_task_name()
        return os.getenv("AYON_TASK_NAME")

    def get_current_context(self):
        if isinstance(self._host, HostBase):
            return self._host.get_current_context()
        return {
            "project_name": self.project_name,
            "folder_path": self.current_folder_path,
            "task_name": self.current_task_name
        }

    @property
    def project_settings(self):
        if self._project_settings is None:
            self._project_settings = get_project_settings(self.project_name)
        return self._project_settings

    @property
    def current_folder_entity(self):
        if self._current_folder_entity is _NOT_SET:
            self._current_folder_entity = get_folder_by_path(
                self.project_name, self.current_folder_path
            )
        return self._current_folder_entity

    @property
    def linked_folder_entities(self):
        if self._linked_folder_entities is _NOT_SET:
            self._linked_folder_entities = self._get_linked_folder_entities()
        return self._linked_folder_entities

    @property
    def current_task_entity(self):
        if self._current_task_entity is _NOT_SET:
            task_entity = None
            folder_entity = self.current_folder_entity
            if folder_entity:
                task_entity = get_task_by_name(
                    self.project_name,
                    folder_entity["id"],
                    self.current_task_name
                )
            self._current_task_entity = task_entity
        return self._current_task_entity

    @property
    def current_task_type(self):
        task_entity = self.current_task_entity
        if task_entity:
            return task_entity["taskType"]
        return None

    @property
    def create_context(self):
        if self._create_context is None:
            self._create_context = CreateContext(
                self.host,
                discover_publish_plugins=False,
                headless=True
            )
        return self._create_context

    def get_placeholder_plugin_classes(self):
        """Get placeholder plugin classes that can be used to build template.

        Default implementation looks for method
            'get_workfile_build_placeholder_plugins' on host.

        Returns:
            List[PlaceholderPlugin]: Plugin classes available for host.
        """
        plugins = []

        # Backwards compatibility
        if hasattr(self._host, "get_workfile_build_placeholder_plugins"):
            return self._host.get_workfile_build_placeholder_plugins()

        plugins.extend(discover(PlaceholderPlugin))
        return plugins

    @property
    def host(self):
        """Access to host implementation.

        Returns:
            Union[HostBase, ModuleType]: Implementation of host.
        """

        return self._host

    @property
    def host_name(self):
        """Name of 'host' implementation.

        Returns:
            str: Host's name.
        """

        return self._host_name

    @property
    def log(self):
        """Dynamically created logger for the plugin."""

        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    def refresh(self):
        """Reset cached data."""

        self._placeholder_plugins = None
        self._loaders_by_name = None
        self._creators_by_name = None

        self._current_folder_entity = _NOT_SET
        self._current_task_entity = _NOT_SET
        self._linked_folder_entities = _NOT_SET

        self._project_settings = None

        self._event_system = EventSystem()

        self.clear_shared_data()
        self.clear_shared_populate_data()

    def get_loaders_by_name(self):
        if self._loaders_by_name is None:
            self._loaders_by_name = get_loaders_by_name()
        return self._loaders_by_name

    def _get_linked_folder_entities(self):
        project_name = self.project_name
        folder_entity = self.current_folder_entity
        if not folder_entity:
            return []
        links = get_folder_links(
            project_name, folder_entity["id"], link_direction="in"
        )
        linked_folder_ids = {
            link["entityId"]
            for link in links
            if link["entityType"] == "folder"
        }

        return list(get_folders(project_name, folder_ids=linked_folder_ids))

    def _collect_legacy_creators(self):
        creators_by_name = {}
        for creator in discover_legacy_creator_plugins():
            if not creator.enabled:
                continue
            creator_name = creator.__name__
            if creator_name in creators_by_name:
                raise KeyError(
                    "Duplicated creator name {} !".format(creator_name)
                )
            creators_by_name[creator_name] = creator
        self._creators_by_name = creators_by_name

    def _collect_creators(self):
        self._creators_by_name = {
            identifier: creator
            for identifier, creator
            in self.create_context.manual_creators.items()
            # Do not list HiddenCreator even though it is a 'manual creator'
            if not isinstance(creator, HiddenCreator)
        }

    def get_creators_by_name(self):
        if self._creators_by_name is None:
            if self.use_legacy_creators:
                self._collect_legacy_creators()
            else:
                self._collect_creators()

        return self._creators_by_name

    def get_shared_data(self, key):
        """Receive shared data across plugins and placeholders.

        This can be used to scroll scene only once to look for placeholder
        items if the storing is unified but each placeholder plugin would have
        to call it again.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        return self._shared_data.get(key)

    def set_shared_data(self, key, value):
        """Store share data across plugins and placeholders.

        Store data that can be afterwards accessed from any future call. It
        is good practice to check if the same value is not already stored under
        different key or if the key is not already used for something else.

        Key should be self-explanatory to content.
        - wrong: 'folder'
        - good: 'folder_name'

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        self._shared_data[key] = value

    def clear_shared_data(self):
        """Clear shared data.

        Method only clear shared data to default state.
        """

        self._shared_data = {}

    def clear_shared_populate_data(self):
        """Receive shared data across plugins and placeholders.

        These data are cleared after each loop of populating of template.

        This can be used to scroll scene only once to look for placeholder
        items if the storing is unified but each placeholder plugin would have
        to call it again.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        self._shared_populate_data = {}

    def get_shared_populate_data(self, key):
        """Store share populate data across plugins and placeholders.

        These data are cleared after each loop of populating of template.

        Store data that can be afterwards accessed from any future call. It
        is good practice to check if the same value is not already stored under
        different key or if the key is not already used for something else.

        Key should be self-explanatory to content.
        - wrong: 'folder'
        - good: 'folder_path'

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        return self._shared_populate_data.get(key)

    def set_shared_populate_data(self, key, value):
        """Store share populate data across plugins and placeholders.

        These data are cleared after each loop of populating of template.

        Store data that can be afterwards accessed from any future call. It
        is good practice to check if the same value is not already stored under
        different key or if the key is not already used for something else.

        Key should be self-explanatory to content.
        - wrong: 'folder'
        - good: 'folder_path'

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        self._shared_populate_data[key] = value

    @property
    def placeholder_plugins(self):
        """Access to initialized placeholder plugins.

        Returns:
            List[PlaceholderPlugin]: Initialized plugins available for host.
        """

        if self._placeholder_plugins is None:
            placeholder_plugins = {}
            for cls in self.get_placeholder_plugin_classes():
                try:
                    plugin = cls(self)
                    placeholder_plugins[plugin.identifier] = plugin

                except Exception:
                    self.log.warning(
                        "Failed to initialize placeholder plugin {}".format(
                            cls.__name__
                        ),
                        exc_info=True
                    )

            self._placeholder_plugins = placeholder_plugins
        return self._placeholder_plugins

    def create_placeholder(self, plugin_identifier, placeholder_data):
        """Create new placeholder using plugin identifier and data.

        Args:
            plugin_identifier (str): Identifier of plugin. That's how builder
                know which plugin should be used.
            placeholder_data (Dict[str, Any]): Placeholder item data. They
                should match options required by the plugin.

        Returns:
            PlaceholderItem: Created placeholder item.
        """

        plugin = self.placeholder_plugins[plugin_identifier]
        return plugin.create_placeholder(placeholder_data)

    def get_placeholders(self):
        """Collect placeholder items from scene.

        Each placeholder plugin can collect it's placeholders and return them.
        This method does not use cached values but always go through the scene.

        Returns:
            List[PlaceholderItem]: Sorted placeholder items.
        """

        placeholders = []
        for placeholder_plugin in self.placeholder_plugins.values():
            result = placeholder_plugin.collect_placeholders()
            if result:
                placeholders.extend(result)

        return list(sorted(
            placeholders,
            key=lambda placeholder: placeholder.order
        ))

    def build_template(
        self,
        template_path=None,
        level_limit=None,
        keep_placeholders=None,
        create_first_version=None,
        workfile_creation_enabled=False
    ):
        """Main callback for building workfile from template path.

        Todo:
            Handle report of populated placeholders from
                'populate_scene_placeholders' to be shown to a user.

        Args:
            template_path (str): Path to a template file with placeholders.
                Template from settings 'get_template_preset' used when not
                passed.
            level_limit (int): Limit of populate loops. Related to
                'populate_scene_placeholders' method.
            keep_placeholders (bool): Add flag to placeholder data for
                hosts to decide if they want to remove
                placeholder after it is used.
            create_first_version (bool): Create first version of a workfile.
                 When set to True, this option initiates the saving of the
                 workfile for an initial version. It will skip saving if
                 a version already exists.
            workfile_creation_enabled (bool): Whether the call is part of
                creating a new workfile.
                When True, we only build if the current file is not
                an existing saved workfile but a "new" file. Basically when
                enabled we assume the user tries to load it only into a
                "New File" (unsaved empty workfile).
                When False, the default value, we assume we explicitly want to
                build the template in our current scene regardless of current
                scene state.

        """
        # More accurate variable name
        # - logic related to workfile creation should be moved out in future
        explicit_build_requested = not workfile_creation_enabled

        # Get default values if not provided
        if (
            template_path is None
            or keep_placeholders is None
            or create_first_version is None
        ):
            preset = self.get_template_preset()
            template_path: str = template_path or preset["path"]
            if keep_placeholders is None:
                keep_placeholders: bool = preset["keep_placeholder"]
            if create_first_version is None:
                create_first_version: bool = preset["create_first_version"]

        # Build the template if we are explicitly requesting it or if it's
        # an unsaved "new file".
        is_new_file = not self.host.get_current_workfile()
        if is_new_file or explicit_build_requested:
            self.log.info(f"Building the workfile template: {template_path}")
            self.import_template(template_path)
            self.populate_scene_placeholders(
                level_limit, keep_placeholders)

        # Do not consider saving a first workfile version, if this is not set
        # to be a "workfile creation" or `create_first_version` is disabled.
        if explicit_build_requested or not create_first_version:
            return

        # If there is no existing workfile, save the first version
        workfile_path = self.get_workfile_path()
        if not os.path.exists(workfile_path):
            self.log.info("Saving first workfile: %s", workfile_path)
            self.save_workfile(workfile_path)
        else:
            self.log.info(
                "A workfile already exists. Skipping save of workfile as "
                "initial version.")

    def rebuild_template(self):
        """Go through existing placeholders in scene and update them.

        This could not make sense for all plugin types so this is optional
        logic for plugins.

        Note:
            Logic is not importing the template again but using placeholders
                that were already available. We should maybe change the method
                name.

        Question:
            Should this also handle subloops as it is possible that another
                template is loaded during processing?
        """

        if not self.placeholder_plugins:
            self.log.info("There are no placeholder plugins available.")
            return

        placeholders = self.get_placeholders()
        if not placeholders:
            self.log.info("No placeholders were found.")
            return

        for placeholder in placeholders:
            plugin = placeholder.plugin
            plugin.repopulate_placeholder(placeholder)

        self.clear_shared_populate_data()

    def open_template(self):
        """Open template file with registered host."""
        template_preset = self.get_template_preset()
        template_path = template_preset["path"]
        self.host.open_file(template_path)

    @abstractmethod
    def import_template(self, template_path):
        """
        Import template in current host.

        Should load the content of template into scene so
        'populate_scene_placeholders' can be started.

        Args:
            template_path (str): Fullpath for current task and
                host's template file.
        """

        pass

    def get_workfile_path(self):
        """Return last known workfile path or the first workfile path create.

        Return:
            str: Last workfile path, or first version to create if none exist.
        """
        # AYON_LAST_WORKFILE will be set to the last existing workfile OR
        # if none exist it will be set to the first version.
        last_workfile_path = os.environ.get("AYON_LAST_WORKFILE")
        self.log.info("__ last_workfile_path: {}".format(last_workfile_path))
        return last_workfile_path

    def save_workfile(self, workfile_path):
        """Save workfile in current host."""
        # Save current scene, continue to open file
        if isinstance(self.host, IWorkfileHost):
            self.host.save_workfile(workfile_path)
        else:
            self.host.save_file(workfile_path)

    def _prepare_placeholders(self, placeholders):
        """Run preparation part for placeholders on plugins.

        Args:
            placeholders (List[PlaceholderItem]): Placeholder items that will
                be processed.
        """

        # Prepare placeholder items by plugin
        plugins_by_identifier = {}
        placeholders_by_plugin_id = collections.defaultdict(list)
        for placeholder in placeholders:
            plugin = placeholder.plugin
            identifier = plugin.identifier
            plugins_by_identifier[identifier] = plugin
            placeholders_by_plugin_id[identifier].append(placeholder)

        # Plugin should prepare data for passed placeholders
        for identifier, placeholders in placeholders_by_plugin_id.items():
            plugin = plugins_by_identifier[identifier]
            plugin.prepare_placeholders(placeholders)

    def populate_scene_placeholders(
        self, level_limit=None, keep_placeholders=None
    ):
        """Find placeholders in scene using plugins and process them.

        This should happen after 'import_template'.

        Collect available placeholders from scene. All of them are processed
        after that shared data are cleared. Placeholder items are collected
        again and if there are any new the loop happens again. This is possible
        to change with defying 'level_limit'.

        Placeholders are marked as processed so they're not re-processed. To
        identify which placeholders were already processed is used
        placeholder's 'scene_identifier'.

        Args:
            level_limit (int): Level of loops that can happen. Default is 1000.
            keep_placeholders (bool): Add flag to placeholder data for
                hosts to decide if they want to remove
                placeholder after it is used.
        """

        if not self.placeholder_plugins:
            self.log.warning("There are no placeholder plugins available.")
            return

        placeholders = self.get_placeholders()
        if not placeholders:
            self.log.warning("No placeholders were found.")
            return

        # Avoid infinite loop
        # - 1000 iterations of placeholders processing must be enough
        if not level_limit:
            level_limit = 1000

        placeholder_by_scene_id = {
            placeholder.scene_identifier: placeholder
            for placeholder in placeholders
        }
        all_processed = len(placeholders) == 0
        # Counter is checked at the end of a loop so the loop happens at least
        #   once.
        iter_counter = 0
        while not all_processed:
            filtered_placeholders = []
            for placeholder in placeholders:
                if placeholder.finished:
                    continue

                if placeholder.in_progress:
                    self.log.warning((
                        "Placeholder that should be processed"
                        " is already in progress."
                    ))
                    continue

                # add flag for keeping placeholders in scene
                # after they are processed
                placeholder.data["keep_placeholder"] = keep_placeholders

                filtered_placeholders.append(placeholder)

            self._prepare_placeholders(filtered_placeholders)

            for placeholder in filtered_placeholders:
                placeholder.set_in_progress()
                placeholder_plugin = placeholder.plugin
                try:
                    placeholder_plugin.populate_placeholder(placeholder)

                except Exception as exc:
                    self.log.warning(
                        (
                            "Failed to process placeholder {} with plugin {}"
                        ).format(
                            placeholder.scene_identifier,
                            placeholder_plugin.__class__.__name__
                        ),
                        exc_info=True
                    )
                    placeholder.set_failed(exc)

                placeholder.set_finished()

            # Trigger on_depth_processed event
            self.emit_event(
                topic="template.depth_processed",
                data={
                    "depth": iter_counter,
                    "placeholders_by_scene_id": placeholder_by_scene_id
                },
                source="builder"
            )

            # Clear shared data before getting new placeholders
            self.clear_shared_populate_data()

            iter_counter += 1
            if iter_counter >= level_limit:
                break

            all_processed = True
            collected_placeholders = self.get_placeholders()
            for placeholder in collected_placeholders:
                identifier = placeholder.scene_identifier
                if identifier in placeholder_by_scene_id:
                    continue

                all_processed = False
                placeholder_by_scene_id[identifier] = placeholder
                placeholders.append(placeholder)

        # Trigger on_finished event
        self.emit_event(
            topic="template.finished",
            data={
                "depth": iter_counter,
                "placeholders_by_scene_id": placeholder_by_scene_id,
            },
            source="builder"
        )

        self.refresh()

    def _get_build_profiles(self):
        """Get build profiles for workfile build template path.

        Returns:
            List[Dict[str, Any]]: Profiles for template path resolving.
        """

        return (
            self.project_settings
            [self.host_name]
            ["templated_workfile_build"]
            ["profiles"]
        )

    def get_template_preset(self):
        """Unified way how template preset is received using settings.

        Method is dependent on '_get_build_profiles' which should return filter
        profiles to resolve path to a template. Default implementation looks
        into host settings:
        - 'project_settings/{host name}/templated_workfile_build/profiles'

        Returns:
            dict: Dictionary with `path`, `keep_placeholder` and
                `create_first_version` settings from the template preset
                for current context.

        Raises:
            TemplateProfileNotFound: When profiles are not filled.
            TemplateLoadFailed: Profile was found but path is not set.
            TemplateNotFound: Path was set but file does not exist.
        """

        host_name = self.host_name
        task_name = self.current_task_name
        task_type = self.current_task_type

        build_profiles = self._get_build_profiles()
        profile = filter_profiles(
            build_profiles,
            {
                "task_types": task_type,
                "task_names": task_name
            }
        )
        if not profile:
            raise TemplateProfileNotFound((
                "No matching profile found for task '{}' of type '{}' "
                "with host '{}'"
            ).format(task_name, task_type, host_name))

        path = profile["path"]
        if not path:
            raise TemplateLoadFailed((
                "Template path is not set.\n"
                "Path need to be set in {}\\Template Workfile Build "
                "Settings\\Profiles"
            ).format(host_name.title()))

        resolved_path = self.resolve_template_path(path)
        if not resolved_path or not os.path.exists(resolved_path):
            raise TemplateNotFound(
                "Template file found in AYON settings for task '{}' with host "
                "'{}' does not exists. (Not found : {})".format(
                    task_name, host_name, resolved_path)
            )

        self.log.info(f"Found template at: '{resolved_path}'")

        # switch to remove placeholders after they are used
        keep_placeholder = profile.get("keep_placeholder")
        create_first_version = profile.get("create_first_version")

        # backward compatibility, since default is True
        if keep_placeholder is None:
            keep_placeholder = True

        return {
            "path": resolved_path,
            "keep_placeholder": keep_placeholder,
            "create_first_version": create_first_version
        }

    def resolve_template_path(self, path, fill_data=None) -> str:
        """Resolve the template path.

        By default, this:
          - Resolves AYON entity URI to a filesystem path
          - Returns path directly if it exists on disk.
          - Resolves template keys through anatomy and environment variables.

        This can be overridden in host integrations to perform additional
        resolving over the template. Like, `hou.text.expandString` in Houdini.
        It's recommended to still call the super().resolve_template_path()
        to ensure the basic resolving is done across all integrations.

        Arguments:
            path (str): The input path.
            fill_data (dict[str, str]): Deprecated. This is computed inside
                the method using the current environment and project settings.
                Used to be the data to use for template formatting.

        Returns:
            str: The resolved path.

        """

        # If the path is an AYON entity URI, then resolve the filepath
        # through the backend
        if path.startswith("ayon+entity://") or path.startswith("ayon://"):
            # This is a special case where the path is an AYON entity URI
            # We need to resolve it to a filesystem path
            resolved_path = resolve_entity_uri(path)
            return resolved_path

        # If the path is set and it's found on disk, return it directly
        if path and os.path.exists(path):
            return path

        # We may have path for another platform, like C:/path/to/file
        # or a path with template keys, like {project[code]} or both.
        # Try to fill path with environments and anatomy roots
        project_name = self.project_name
        anatomy = Anatomy(project_name)

        # Simple check whether the path contains any template keys
        if "{" in path:
            fill_data = {
                key: value
                for key, value in os.environ.items()
            }
            fill_data["root"] = anatomy.roots
            fill_data["project"] = {
                "name": project_name,
                "code": anatomy.project_code,
            }

            # Format the template using local fill data
            result = StringTemplate.format_template(path, fill_data)
            if not result.solved:
                return path

            path = result.normalized()
            if os.path.exists(path):
                return path

        # If the path were set in settings using a Windows path and we
        # are now on a Linux system, we try to convert the solved path to
        # the current platform.
        while True:
            try:
                solved_path = anatomy.path_remapper(path)
            except KeyError as missing_key:
                raise KeyError(
                    f"Could not solve key '{missing_key}'"
                    f" in template path '{path}'"
                )

            if solved_path is None:
                solved_path = path
            if solved_path == path:
                break
            path = solved_path

        solved_path = os.path.normpath(solved_path)
        return solved_path

    def emit_event(self, topic, data=None, source=None) -> Event:
        return self._event_system.emit(topic, data, source)

    def add_event_callback(self, topic, callback, order=None):
        return self._event_system.add_callback(topic, callback, order=order)

    def add_on_finished_callback(
        self, callback, order=None
    ) -> EventCallback:
        return self.add_event_callback(
            topic="template.finished",
            callback=callback,
            order=order
        )

    def add_on_depth_processed_callback(
        self, callback, order=None
    ) -> EventCallback:
        return self.add_event_callback(
            topic="template.depth_processed",
            callback=callback,
            order=order
        )


class PlaceholderPlugin(ABC):
    """Plugin which care about handling of placeholder items logic.

    Plugin create and update placeholders in scene and populate them on
    template import. Populating means that based on placeholder data happens
    a logic in the scene. Most common logic is to load representation using
    loaders or to create instances in scene.
    """

    label = None
    _log = None

    def __init__(self, builder):
        self._builder = builder

    @property
    def builder(self):
        """Access to builder which initialized the plugin.

        Returns:
            AbstractTemplateBuilder: Loader of template build.
        """

        return self._builder

    @property
    def project_name(self):
        return self._builder.project_name

    @property
    def log(self):
        """Dynamically created logger for the plugin."""

        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    @property
    def identifier(self):
        """Identifier which will be stored to placeholder.

        Default implementation uses class name.

        Returns:
            str: Unique identifier of placeholder plugin.
        """

        return self.__class__.__name__

    @abstractmethod
    def create_placeholder(self, placeholder_data):
        """Create new placeholder in scene and get it's item.

        It matters on the plugin implementation if placeholder will use
        selection in scene or create new node.

        Args:
            placeholder_data (Dict[str, Any]): Data that were created
                based on attribute definitions from 'get_placeholder_options'.

        Returns:
            PlaceholderItem: Created placeholder item.
        """

        pass

    @abstractmethod
    def update_placeholder(self, placeholder_item, placeholder_data):
        """Update placeholder item with new data.

        New data should be propagated to object of placeholder item itself
        and also into the scene.

        Reason:
            Some placeholder plugins may require some special way how the
            updates should be propagated to object.

        Args:
            placeholder_item (PlaceholderItem): Object of placeholder that
                should be updated.
            placeholder_data (Dict[str, Any]): Data related to placeholder.
                Should match plugin options.
        """

        pass

    @abstractmethod
    def collect_placeholders(self):
        """Collect placeholders from scene.

        Returns:
            List[PlaceholderItem]: Placeholder objects.
        """

        pass

    def get_placeholder_options(self, options=None):
        """Placeholder options for data showed.

        Returns:
            List[AbstractAttrDef]: Attribute definitions of
                placeholder options.
        """

        return []

    def get_placeholder_keys(self):
        """Get placeholder keys that are stored in scene.

        Returns:
            Set[str]: Key of placeholder keys that are stored in scene.
        """

        option_keys = get_attributes_keys(self.get_placeholder_options())
        option_keys.add("plugin_identifier")
        return option_keys

    def prepare_placeholders(self, placeholders):
        """Preparation part of placeholders.

        Args:
            placeholders (List[PlaceholderItem]): List of placeholders that
                will be processed.
        """

        pass

    @abstractmethod
    def populate_placeholder(self, placeholder):
        """Process single placeholder item.

        Processing of placeholders is defined by their order thus can't be
        processed in batch.

        Args:
            placeholder (PlaceholderItem): Placeholder that should be
                processed.
        """

        pass

    def repopulate_placeholder(self, placeholder):
        """Update scene with current context for passed placeholder.

        Can be used to re-run placeholder logic (if it make sense).
        """

        pass

    def get_plugin_shared_data(self, key):
        """Receive shared data across plugin and placeholders.

        Using shared data from builder but stored under plugin identifier.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        plugin_data = self.builder.get_shared_data(self.identifier)
        if plugin_data is None:
            return None
        return plugin_data.get(key)

    def set_plugin_shared_data(self, key, value):
        """Store share data across plugin and placeholders.

        Using shared data from builder but stored under plugin identifier.

        Key should be self-explanatory to content.
        - wrong: 'folder'
        - good: 'folder_path'

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        plugin_data = self.builder.get_shared_data(self.identifier)
        if plugin_data is None:
            plugin_data = {}
        plugin_data[key] = value
        self.builder.set_shared_data(self.identifier, plugin_data)

    def get_plugin_shared_populate_data(self, key):
        """Receive shared data across plugin and placeholders.

        Using shared populate data from builder but stored under plugin
        identifier.

        Shared populate data are cleaned up during populate while loop.

        Args:
            key (str): Key under which are shared data stored.

        Returns:
            Union[None, Any]: None if key was not set.
        """

        plugin_data = self.builder.get_shared_populate_data(self.identifier)
        if plugin_data is None:
            return None
        return plugin_data.get(key)

    def set_plugin_shared_populate_data(self, key, value):
        """Store share data across plugin and placeholders.

        Using shared data from builder but stored under plugin identifier.

        Key should be self-explanatory to content.
        - wrong: 'folder'
        - good: 'folder_path'

        Shared populate data are cleaned up during populate while loop.

        Args:
            key (str): Key under which is key stored.
            value (Any): Value that should be stored under the key.
        """

        plugin_data = self.builder.get_shared_populate_data(self.identifier)
        if plugin_data is None:
            plugin_data = {}
        plugin_data[key] = value
        self.builder.set_shared_populate_data(self.identifier, plugin_data)


class PlaceholderItem(object):
    """Item representing single item in scene that is a placeholder to process.

    Items are always created and updated by their plugins. Each plugin can use
    modified class of 'PlaceholderItem' but only to add more options instead of
    new other.

    Scene identifier is used to avoid processing of the placeholder item
    multiple times so must be unique across whole workfile builder.

    Args:
        scene_identifier (str): Unique scene identifier. If placeholder is
            created from the same "node" it must have same identifier.
        data (Dict[str, Any]): Data related to placeholder. They're defined
            by plugin.
        plugin (PlaceholderPlugin): Plugin which created the placeholder item.
    """

    default_order = 100

    def __init__(self, scene_identifier, data, plugin):
        self._log = None
        self._scene_identifier = scene_identifier
        self._data = data
        self._plugin = plugin

        # Keep track about state of Placeholder process
        self._state = 0

        # Error messages to be shown in UI
        # - all other messages should be logged
        self._errors = []  # -> List[str]

    @property
    def plugin(self):
        """Access to plugin which created placeholder.

        Returns:
            PlaceholderPlugin: Plugin object.
        """

        return self._plugin

    @property
    def builder(self):
        """Access to builder.

        Returns:
            AbstractTemplateBuilder: Builder which is the top part of
                placeholder.
        """

        return self.plugin.builder

    @property
    def data(self):
        """Placeholder data which can modify how placeholder is processed.

        Possible general keys
        - order: Can define the order in which is placeholder processed.
                    Lower == earlier.

        Other keys are defined by placeholder and should validate them on item
        creation.

        Returns:
            Dict[str, Any]: Placeholder item data.
        """

        return self._data

    def to_dict(self):
        """Create copy of item's data.

        Returns:
            Dict[str, Any]: Placeholder data.
        """

        return copy.deepcopy(self.data)

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(repr(self))
        return self._log

    def __repr__(self):
        return "< {} {} >".format(
            self.__class__.__name__,
            self._scene_identifier
        )

    @property
    def order(self):
        """Order of item processing."""

        order = self._data.get("order")
        if order is None:
            return self.default_order
        return order

    @property
    def scene_identifier(self):
        return self._scene_identifier

    @property
    def finished(self):
        """Item was already processed."""

        return self._state == 2

    @property
    def in_progress(self):
        """Processing is in progress."""

        return self._state == 1

    def set_in_progress(self):
        """Change to in progress state."""

        self._state = 1

    def set_finished(self):
        """Change to finished state."""

        self._state = 2

    def set_failed(self, exception):
        self.add_error(str(exception))

    def add_error(self, error):
        """Set placeholder item as failed and mark it as finished."""

        self._errors.append(error)

    def get_errors(self):
        """Exception with which the placeholder process failed.

        Gives ability to access the exception.
        """

        return self._errors


class PlaceholderLoadMixin(object):
    """Mixin prepared for loading placeholder plugins.

    Implementation prepares options for placeholders with
    'get_load_plugin_options'.

    For placeholder population is implemented 'populate_load_placeholder'.

    PlaceholderItem can have implemented methods:
    - 'load_failed' - called when loading of one representation failed
    - 'load_succeed' - called when loading of one representation succeeded
    """

    def get_load_plugin_options(self, options=None):
        """Unified attribute definitions for load placeholder.

        Common function for placeholder plugins used for loading of
        representations. Use it in 'get_placeholder_options'.

        Args:
            options (Dict[str, Any]): Already available options which are used
                as defaults for attributes.

        Returns:
            List[AbstractAttrDef]: Attribute definitions common for load
                plugins.
        """

        loaders_by_name = self.builder.get_loaders_by_name()
        loader_items = [
            {"value": loader_name, "label": loader.label or loader_name}
            for loader_name, loader in loaders_by_name.items()
        ]

        loader_items = list(sorted(loader_items, key=lambda i: i["label"]))
        options = options or {}

        # Get product types from all loaders excluding "*"
        product_types = set()
        for loader in loaders_by_name.values():
            product_types.update(loader.product_types)
        product_types.discard("*")

        # Sort for readability
        product_types = list(sorted(product_types))

        builder_type_enum_items = [
            {"label": "Current folder", "value": "context_folder"},
            # TODO implement linked folders
            # {"label": "Linked folders", "value": "linked_folders"},
            {"label": "All folders", "value": "all_folders"},
        ]
        build_type_label = "Folder Builder Type"
        build_type_help = (
            "Folder Builder Type\n"
            "\nBuilder type describe what template loader will look"
            " for."
            "\nCurrent Folder: Template loader will look for products"
            " of current context folder (Folder /assets/bob will"
            " find asset)"
            "\nAll folders: All folders matching the regex will be"
            " used."
        )

        product_type = options.get("product_type")
        if product_type is None:
            product_type = options.get("family")

        return [
            attribute_definitions.UISeparatorDef(),
            attribute_definitions.UILabelDef("Main attributes"),
            attribute_definitions.UISeparatorDef(),

            attribute_definitions.EnumDef(
                "builder_type",
                label=build_type_label,
                default=options.get("builder_type"),
                items=builder_type_enum_items,
                tooltip=build_type_help
            ),
            attribute_definitions.EnumDef(
                "product_type",
                label="Product type",
                default=product_type,
                items=product_types
            ),
            attribute_definitions.TextDef(
                "representation",
                label="Representation name",
                default=options.get("representation"),
                placeholder="ma, abc, ..."
            ),
            attribute_definitions.EnumDef(
                "loader",
                label="Loader",
                default=options.get("loader"),
                items=loader_items,
                tooltip=(
                    "Loader"
                    "\nDefines what AYON loader will be used to"
                    " load assets."
                    "\nUseable loader depends on current host's loader list."
                    "\nField is case sensitive."
                )
            ),
            attribute_definitions.TextDef(
                "loader_args",
                label="Loader Arguments",
                default=options.get("loader_args"),
                placeholder='{"camera":"persp", "lights":True}',
                tooltip=(
                    "Loader"
                    "\nDefines a dictionary of arguments used to load assets."
                    "\nUseable arguments depend on current placeholder Loader."
                    "\nField should be a valid python dict."
                    " Anything else will be ignored."
                )
            ),
            attribute_definitions.NumberDef(
                "order",
                label="Order",
                default=options.get("order") or 0,
                decimals=0,
                minimum=0,
                maximum=999,
                tooltip=(
                    "Order"
                    "\nOrder defines asset loading priority (0 to 999)"
                    "\nPriority rule is : \"lowest is first to load\"."
                )
            ),
            attribute_definitions.UISeparatorDef(),
            attribute_definitions.UILabelDef("Optional attributes"),
            attribute_definitions.UISeparatorDef(),
            attribute_definitions.TextDef(
                "folder_path",
                label="Folder filter",
                default=options.get("folder_path"),
                placeholder="regex filtering by folder path",
                tooltip=(
                    "Filtering assets by matching"
                    " field regex to folder path"
                )
            ),
            attribute_definitions.TextDef(
                "product_name",
                label="Product filter",
                default=options.get("product_name"),
                placeholder="regex filtering by product name",
                tooltip=(
                    "Filtering assets by matching"
                    " field regex to product name"
                )
            ),
        ]

    def parse_loader_args(self, loader_args):
        """Helper function to parse string of loader arguments.

        Empty dictionary is returned if conversion fails.

        Args:
            loader_args (str): Loader args filled by user.

        Returns:
            Dict[str, Any]: Parsed arguments used as dictionary.
        """

        if not loader_args:
            return {}

        try:
            parsed_args = eval(loader_args)
            if isinstance(parsed_args, dict):
                return parsed_args

        except Exception as err:
            print(
                "Error while parsing loader arguments '{}'.\n{}: {}\n\n"
                "Continuing with default arguments. . .".format(
                    loader_args, err.__class__.__name__, err))

        return {}

    def _get_representations(self, placeholder):
        """Prepared query of representations based on load options.

        This function is directly connected to options defined in
        'get_load_plugin_options'.

        Note:
            This returns all representation documents from all versions of
                matching product. To filter for last version use
                '_reduce_last_version_repre_entities'.

        Args:
            placeholder (PlaceholderItem): Item which should be populated.

        Returns:
            List[Dict[str, Any]]: Representation documents matching filters
                from placeholder data.
        """

        # An OpenPype placeholder loaded in AYON
        if "asset" in placeholder.data:
            return []

        representation_names = None
        representation_name: str = placeholder.data["representation"]
        if representation_name:
            representation_names = [representation_name]

        project_name = self.builder.project_name
        current_folder_entity = self.builder.current_folder_entity

        folder_path_regex = placeholder.data["folder_path"]
        product_name_regex_value = placeholder.data["product_name"]
        product_name_regex = None
        if product_name_regex_value:
            product_name_regex = re.compile(product_name_regex_value)
        product_type = placeholder.data.get("product_type")
        if product_type is None:
            product_type = placeholder.data["family"]

        builder_type = placeholder.data["builder_type"]
        folder_ids = []
        if builder_type == "context_folder":
            folder_ids = [current_folder_entity["id"]]

        elif builder_type == "all_folders":
            folder_ids = {
                folder_entity["id"]
                for folder_entity in get_folders(
                    project_name,
                    folder_path_regex=folder_path_regex,
                    fields={"id"}
                )
            }

        if not folder_ids:
            return []

        products = list(get_products(
            project_name,
            folder_ids=folder_ids,
            product_types=[product_type],
            fields={"id", "name"}
        ))
        filtered_product_ids = set()
        for product in products:
            if (
                product_name_regex is None
                or product_name_regex.match(product["name"])
            ):
                filtered_product_ids.add(product["id"])

        if not filtered_product_ids:
            return []

        version_ids = set(
            version["id"]
            for version in get_last_versions(
                project_name, filtered_product_ids, fields={"id"}
            ).values()
        )
        return list(get_representations(
            project_name,
            representation_names=representation_names,
            version_ids=version_ids
        ))

    def _before_placeholder_load(self, placeholder):
        """Can be overridden. It's called before placeholder representations
        are loaded.
        """

        pass

    def _before_repre_load(self, placeholder, representation):
        """Can be overridden. It's called before representation is loaded."""

        pass

    def _reduce_last_version_repre_entities(self, repre_contexts):
        """Reduce representations to last version."""

        version_mapping_by_product_id = {}
        for repre_context in repre_contexts:
            product_id = repre_context["product"]["id"]
            version = repre_context["version"]["version"]
            version_mapping = version_mapping_by_product_id.setdefault(
                product_id, {}
            )
            version_mapping.setdefault(version, []).append(repre_context)

        output = []
        for version_mapping in version_mapping_by_product_id.values():
            last_version = max(version_mapping.keys())
            output.extend(version_mapping[last_version])
        return output

    def populate_load_placeholder(self, placeholder, ignore_repre_ids=None):
        """Load placeholder is going to load matching representations.

        Note:
            Ignore repre ids is to avoid loading the same representation again
            on load. But the representation can be loaded with different loader
            and there could be published new version of matching product for
            the representation. We should maybe expect containers.

            Also import loaders don't have containers at all...

        Args:
            placeholder (PlaceholderItem): Placeholder item with information
                about requested representations.
            ignore_repre_ids (Iterable[Union[str, ObjectId]]): Representation
                ids that should be skipped.
        """

        if ignore_repre_ids is None:
            ignore_repre_ids = set()

        # TODO check loader existence
        loader_name = placeholder.data["loader"]
        loader_args = self.parse_loader_args(placeholder.data["loader_args"])

        placeholder_representations = [
            repre_entity
            for repre_entity in self._get_representations(placeholder)
            if repre_entity["id"] not in ignore_repre_ids
        ]

        repre_load_contexts = get_representation_contexts(
            self.project_name, placeholder_representations
        )
        filtered_repre_contexts = self._reduce_last_version_repre_entities(
            repre_load_contexts.values()
        )
        if not filtered_repre_contexts:
            self.log.info((
                "There's no representation for this placeholder: {}"
            ).format(placeholder.scene_identifier))
            if not placeholder.data.get("keep_placeholder", True):
                self.delete_placeholder(placeholder)
            return

        loaders_by_name = self.builder.get_loaders_by_name()
        self._before_placeholder_load(
            placeholder
        )

        failed = False
        for repre_load_context in filtered_repre_contexts:
            folder_path = repre_load_context["folder"]["path"]
            product_name = repre_load_context["product"]["name"]
            representation = repre_load_context["representation"]
            self._before_repre_load(
                placeholder, representation
            )
            self.log.info(
                "Loading {} from {} with loader {}\n"
                "Loader arguments used : {}".format(
                    product_name,
                    folder_path,
                    loader_name,
                    placeholder.data["loader_args"],
                )
            )
            try:
                container = load_with_repre_context(
                    loaders_by_name[loader_name],
                    repre_load_context,
                    options=loader_args
                )

            except Exception:
                self.load_failed(placeholder, representation)
                failed = True
            else:
                self.load_succeed(placeholder, container)

        # Run post placeholder process after load of all representations
        self.post_placeholder_process(placeholder, failed)

        if failed:
            self.log.debug(
                "Placeholder cleanup skipped due to failed placeholder "
                "population."
            )
            return
        if not placeholder.data.get("keep_placeholder", True):
            self.delete_placeholder(placeholder)

    def load_failed(self, placeholder, representation):
        if hasattr(placeholder, "load_failed"):
            placeholder.load_failed(representation)

    def load_succeed(self, placeholder, container):
        if hasattr(placeholder, "load_succeed"):
            placeholder.load_succeed(container)

    def post_placeholder_process(self, placeholder, failed):
        """Cleanup placeholder after load of its corresponding representations.

        Args:
            placeholder (PlaceholderItem): Item which was just used to load
                representation.
            failed (bool): Loading of representation failed.
        """

        pass

    def delete_placeholder(self, placeholder):
        """Called when all item population is done."""
        self.log.debug("Clean up of placeholder is not implemented.")


class PlaceholderCreateMixin(object):
    """Mixin prepared for creating placeholder plugins.

    Implementation prepares options for placeholders with
    'get_create_plugin_options'.

    For placeholder population is implemented 'populate_create_placeholder'.

    PlaceholderItem can have implemented methods:
    - 'create_failed' - called when creating of an instance failed
    - 'create_succeed' - called when creating of an instance succeeded
    """

    def get_create_plugin_options(self, options=None):
        """Unified attribute definitions for create placeholder.

        Common function for placeholder plugins used for creating of
        publishable instances. Use it with 'get_placeholder_options'.

        Args:
            options (Dict[str, Any]): Already available options which are used
                as defaults for attributes.

        Returns:
            List[AbstractAttrDef]: Attribute definitions common for create
                plugins.
        """

        creators_by_name = self.builder.get_creators_by_name()

        creator_items = [
            (creator_name, creator.label or creator_name)
            for creator_name, creator in creators_by_name.items()
        ]

        creator_items.sort(key=lambda i: i[1])
        options = options or {}
        return [
            attribute_definitions.UISeparatorDef(),
            attribute_definitions.UILabelDef("Main attributes"),
            attribute_definitions.UISeparatorDef(),

            attribute_definitions.EnumDef(
                "creator",
                label="Creator",
                default=options.get("creator"),
                items=creator_items,
                tooltip=(
                    "Creator"
                    "\nDefines what AYON creator will be used to"
                    " create publishable instance."
                    "\nUseable creator depends on current host's creator list."
                    "\nField is case sensitive."
                )
            ),
            attribute_definitions.TextDef(
                "create_variant",
                label="Variant",
                default=options.get("create_variant"),
                placeholder='Main',
                tooltip=(
                    "Creator"
                    "\nDefines variant name which will be use for "
                    "\ncompiling of product name."
                )
            ),
            attribute_definitions.BoolDef(
                "active",
                label="Active",
                default=options.get("active", True),
                tooltip=(
                    "Active"
                    "\nDefines whether the created instance will default to "
                    "active or not."
                )
            ),
            attribute_definitions.UISeparatorDef(),
            attribute_definitions.NumberDef(
                "order",
                label="Order",
                default=options.get("order") or 0,
                decimals=0,
                minimum=0,
                maximum=999,
                tooltip=(
                    "Order"
                    "\nOrder defines creating instance priority (0 to 999)"
                    "\nPriority rule is : \"lowest is first to load\"."
                )
            )
        ]

    def populate_create_placeholder(self, placeholder, pre_create_data=None):
        """Create placeholder is going to create matching publishabe instance.

        Args:
            placeholder (PlaceholderItem): Placeholder item with information
                about requested publishable instance.
            pre_create_data (dict): dictionary of configuration from Creator
                configuration in UI
        """

        legacy_create = self.builder.use_legacy_creators
        creator_name = placeholder.data["creator"]
        create_variant = placeholder.data["create_variant"]
        active = placeholder.data.get("active")

        creator_plugin = self.builder.get_creators_by_name()[creator_name]

        # create product name
        context = self._builder.get_current_context()
        project_name = context["project_name"]
        folder_path = context["folder_path"]
        task_name = context["task_name"]
        host_name = self.builder.host_name

        folder_entity = get_folder_by_path(project_name, folder_path)
        if not folder_entity:
            raise ValueError("Current context does not have set folder")
        task_entity = get_task_by_name(
            project_name, folder_entity["id"], task_name
        )

        product_name = creator_plugin.get_product_name(
            project_name,
            folder_entity,
            task_entity,
            create_variant,
            host_name
        )

        creator_data = {
            "creator_name": creator_name,
            "create_variant": create_variant,
            "product_name": product_name,
            "creator_plugin": creator_plugin
        }

        self._before_instance_create(placeholder)

        # compile product name from variant
        try:
            if legacy_create:
                creator_instance = creator_plugin(
                    product_name,
                    folder_path
                ).process()
            else:
                creator_instance = self.builder.create_context.create(
                    creator_plugin.identifier,
                    create_variant,
                    folder_entity,
                    task_entity,
                    pre_create_data=pre_create_data,
                    active=active
                )

        except:  # noqa: E722
            failed = True
            self.create_failed(placeholder, creator_data)

        else:
            failed = False
            self.create_succeed(placeholder, creator_instance)

        self.post_placeholder_process(placeholder, failed)

        if failed:
            self.log.debug(
                "Placeholder cleanup skipped due to failed placeholder "
                "population."
            )
            return

        if not placeholder.data.get("keep_placeholder", True):
            self.delete_placeholder(placeholder)

    def create_failed(self, placeholder, creator_data):
        if hasattr(placeholder, "create_failed"):
            placeholder.create_failed(creator_data)

    def create_succeed(self, placeholder, creator_instance):
        if hasattr(placeholder, "create_succeed"):
            placeholder.create_succeed(creator_instance)

    def post_placeholder_process(self, placeholder, failed):
        """Cleanup placeholder after load of its corresponding representations.

        Args:
            placeholder (PlaceholderItem): Item which was just used to load
                representation.
            failed (bool): Loading of representation failed.
        """
        pass

    def delete_placeholder(self, placeholder):
        """Called when all item population is done."""
        self.log.debug("Clean up of placeholder is not implemented.")

    def _before_instance_create(self, placeholder):
        """Can be overridden. Is called before instance is created."""

        pass


class LoadPlaceholderItem(PlaceholderItem):
    """PlaceholderItem for plugin which is loading representations.

    Connected to 'PlaceholderLoadMixin'.
    """

    def __init__(self, *args, **kwargs):
        super(LoadPlaceholderItem, self).__init__(*args, **kwargs)
        self._failed_representations = []

    def get_errors(self):
        if not self._failed_representations:
            return []
        message = (
            "Failed to load {} representations using Loader {}"
        ).format(
            len(self._failed_representations),
            self.data["loader"]
        )
        return [message]

    def load_failed(self, representation):
        self._failed_representations.append(representation)


class CreatePlaceholderItem(PlaceholderItem):
    """PlaceholderItem for plugin which is creating publish instance.

    Connected to 'PlaceholderCreateMixin'.
    """

    def __init__(self, *args, **kwargs):
        super(CreatePlaceholderItem, self).__init__(*args, **kwargs)
        self._failed_created_publish_instances = []

    def get_errors(self):
        if not self._failed_created_publish_instances:
            return []
        message = (
            "Failed to create {} instance using Creator {}"
        ).format(
            len(self._failed_created_publish_instances),
            self.data["creator"]
        )
        return [message]

    def create_failed(self, creator_data):
        self._failed_created_publish_instances.append(creator_data)


def discover_workfile_build_plugins(*args, **kwargs):
    return discover(PlaceholderPlugin, *args, **kwargs)


def register_workfile_build_plugin(plugin: PlaceholderPlugin):
    register_plugin(PlaceholderPlugin, plugin)


def deregister_workfile_build_plugin(plugin: PlaceholderPlugin):
    deregister_plugin(PlaceholderPlugin, plugin)


def register_workfile_build_plugin_path(path: str):
    register_plugin_path(PlaceholderPlugin, path)


def deregister_workfile_build_plugin_path(path: str):
    deregister_plugin_path(PlaceholderPlugin, path)
