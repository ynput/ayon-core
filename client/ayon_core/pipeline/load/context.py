from __future__ import annotations

import copy
import typing
from typing import Any, Optional, Iterable

from ayon_core.lib import TrackDictChangesItem, Logger

if typing.TYPE_CHECKING:
    from .plugins import LoadPlugin


class RepresentationContext:
    """Representation context used for loading.

    Attributes:
        project_entity (dict[str, Any]): Project entity.
        folder_entity (dict[str, Any]): Folder entity.
        product_entity (dict[str, Any]): Product entity.
        version_entity (dict[str, Any]): Version entity.
        representation_entity (dict[str, Any]): Representation entity.

    """
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    product_entity: dict[str, Any]
    version_entity: dict[str, Any]
    representation_entity: dict[str, Any]


class ContainerItem:
    """Container item of loaded content.

    Args:
        scene_identifier (str): Unique container id.
        project_name (str): Project name.
        representation_id (str): Representation id.
        label (str): Label of container for UI purposes.
        namespace (str): Group label of container for UI purposes.
        version_locked (bool): Version is locked to ignore
            the last version checks.
        parent_scene_identifier (Optional[str]): Parent container id. For visual
            purposes.
        scene_data (Optional[dict[str, Any]]): Additional data stored to the
            scene.
        transient_data (Optional[dict[str, Any]]): Internal load plugin data
            related to the container. Could be any object e.g. node.

    """
    def __init__(
        self,
        scene_identifier: str,
        project_name: str,
        representation_id: str,
        label: str,
        namespace: str,
        load_plugin: LoadPlugin,
        *,
        version_locked: bool = False,
        is_dirty: bool = False,
        parent_scene_identifier: Optional[str] = None,
        scene_data: Optional[dict[str, Any]] = None,
        transient_data: Optional[dict[str, Any]] = None,
    ) -> None:
        self._scene_identifier = scene_identifier
        self._project_name = project_name
        self._representation_id = representation_id
        self._label = label
        self._namespace = namespace
        self._load_plugin_identifier = load_plugin.identifier
        self._version_locked = version_locked
        self._is_dirty = is_dirty
        self._parent_scene_identifier = parent_scene_identifier

        if transient_data is None:
            transient_data = {}

        if scene_data is None:
            scene_data = {}

        self._orig_generic_data = {
            "scene_identifier": self._scene_identifier,
            "project_name": self._project_name,
            "representation_id": self._representation_id,
            "label": self._label,
            "namespace": self._namespace,
            "load_plugin_identifier": self._load_plugin_identifier,
            "version_locked": self._version_locked,
            "is_dirty": self._is_dirty,
            "parent_scene_identifier": self._parent_scene_identifier,
        }
        self._scene_data = scene_data
        self._origin_scene_data = copy.deepcopy(scene_data)
        self._transient_data = transient_data
        self._load_plugin = load_plugin

    # --- Dictionary like methods ---
    def __getitem__(self, key: str) -> Any:
        return self._scene_data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._scene_data

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._scene_data and self._scene_data[key] == value:
            return

        self._scene_data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._scene_data.get(key, default)

    def pop(self, key: str, *args, **kwargs) -> Any:
        return self._scene_data.pop(key, *args, **kwargs)

    def keys(self) -> Iterable[str]:
        return self._scene_data.keys()

    def values(self) -> Iterable[Any]:
        return self._scene_data.values()

    def items(self) -> Iterable[tuple[str, Any]]:
        return self._scene_data.items()
    # ------

    def get_scene_identifier(self) -> str:
        return self._scene_identifier

    def get_project_name(self) -> str:
        return self._project_name

    def get_representation_id(self) -> str:
        return self._representation_id

    def get_is_dirty(self) -> bool:
        return self._is_dirty

    def set_is_dirty(self, dirty: bool) -> None:
        if dirty is self._is_dirty:
            return
        self._is_dirty = dirty
        # TODO trigger event

    def get_version_locked(self) -> bool:
        return self._version_locked

    def set_version_locked(self, version_locked: bool) -> None:
        if self._version_locked == version_locked:
            return
        self._version_locked = version_locked
        # TODO trigger event

    def get_load_plugin_identifier(self) -> str:
        return self._load_plugin_identifier

    def get_scene_data(self) -> dict[str, Any]:
        return copy.deepcopy(self._scene_data)

    def get_origin_scene_data(self) -> dict[str, Any]:
        return copy.deepcopy(self._origin_scene_data)

    def get_transient_data(self) -> dict[str, Any]:
        """Transient data are manager by load plugin.

        Should be used for any arbitrary data needed for a container
            management.

        """
        return self._transient_data

    def get_changes(self) -> TrackDictChangesItem:
        """Calculate and return changes.

        Returns:
            TrackDictChangesItem: Calculated changes on container.

        """
        new_data = {
            "scene_identifier": self._scene_identifier,
            "project_name": self._project_name,
            "representation_id": self._representation_id,
            "label": self._label,
            "namespace": self._namespace,
            "load_plugin_identifier": self._load_plugin_identifier,
            "version_locked": self._version_locked,
            "is_dirty": self._is_dirty,
            "parent_scene_identifier": self._parent_scene_identifier,
            "scene_data": self.get_scene_data(),
        }
        orig_data = copy.deepcopy(self._orig_generic_data)
        orig_data["scene_data"] = self.get_origin_scene_data()
        return TrackDictChangesItem(orig_data, new_data)

    id: str = property(get_scene_identifier)
    scene_identifier: str = property(get_scene_identifier)
    project_name: str = property(get_project_name)
    load_plugin_identifier: str = property(get_load_plugin_identifier)
    representation_id: str = property(get_representation_id)
    scene_data: dict[str, Any] = property(get_scene_data)
    origin_scene_data: dict[str, Any] = property(get_origin_scene_data)
    transient_data: dict[str, Any] = property(get_transient_data)
    changes: TrackDictChangesItem = property(get_changes)


class LoadContext:
    """Context of logic related to loading.

    To be able to load anything in a DCC using AYON is to have load plugins.
    Load plugin is responsible for loading representation. To maintain the
    loaded content it is usually necessary to store some metadata in workfile.

    Loaded content is refered to as a 'container' which is a helper wrapper
    to manage loaded the content, to be able to switch versions or switch to
    different representation (png -> exr), or to remove them from the scene.
    """
    def __init__(self) -> None:
        self._shared_data = {}
        self._plugins = None
        self._containers = {}
        self._collect_containers()
        self._log = Logger.get_logger(self.__class__.__name__)

    def reset(self) -> None:
        self._shared_data = {}
        self._plugins = None
        self._containers = {}

        self._collect_plugins()
        self._collect_containers()

    def get_plugins(self) -> dict[str, LoadPlugin]:
        if self._plugins is None:
            self._collect_plugins()
        return self._plugins

    def get_plugin(self, identifier: str) -> Optional[LoadPlugin]:
        """Get plugin by identifier.

        Args:
            identifier (str): Plugin identifier.

        Returns:
            Optional[LoadPlugin]: Load plugin or None if not found.

        """
        return self._get_plugin_by_identifier(identifier, validate=False)

    def add_containers(self, containers: list[ContainerItem]) -> None:
        """Called by load plugins.

        Args:
            containers (list[ContainerItem]): Containers to add.

        """
        for container in containers:
            if container.id in self._containers:
                self._log.warning()
                continue
            self._containers[container.id] = container

    def get_container_by_id(
        self, scene_identifier: str
    ) -> Optional[ContainerItem]:
        return self._containers.get(scene_identifier)

    def get_containers(self) -> dict[str, ContainerItem]:
        return self._containers

    @property
    def shared_data(self) -> dict[str, Any]:
        """Access to shared data of load plugins.

        It is common that load plugins do store data the same way for all
        containers. This helps to share data between the plugins.

        Returns:
            dict[str, Any]: Shared data.

        """
        return self._shared_data

    def load_representations(
        self,
        identifier: str,
        representation_contexts: list[RepresentationContext],
    ) -> list[ContainerItem]:
        """Load representations.

        Args:
            identifier (str): Load plugin identifier.
            representation_contexts (list[RepresentationContext]): List of
                representation contexts.

        Returns:
            list[ContainerItem]: List of loaded containers.

        """
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.load_representations(representation_contexts)

    def change_representations(
        self,
        identifier: str,
        items: list[tuple[ContainerItem, RepresentationContext]],
    ) -> None:
        """Change representations of loaded containers.

        Args:
            identifier (str): Load plugin identifier.
            items (list[tuple[ContainerItem, RepresentationContext]]): List
                of containers and their new representation contexts.

        """
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.change_representations(items)

    def remove_containers(
        self,
        identifier: str,
        containers: list[ContainerItem],
    ) -> None:
        """Remove containers content with metadata from scene.

        Args:
            identifier (str): Load plugin identifier.
            containers (list[ContainerItem]): Containers to remove.

        """
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.remove_containers(containers)

    def can_switch_container(
        self,
        identifier: str,
        container: ContainerItem,
    ) -> bool:
        """Check if container can be switched.

        Args:
            identifier: Load plugin identifier.
            container (ContainerItem): Container to check.

        Returns:
            bool: True if container can be switched, False otherwise.

        """
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.can_switch_container(container)

    def switch_containers(
        self,
        identifier: str,
        containers: list[ContainerItem],
    ) -> list[ContainerItem]:
        """Switch containers of other load plugins.

        Args:
            identifier: Load plugin identifier.
            containers (list[ContainerItem]): Containers to switch.

        Raises:
            UnsupportedSwitchError: If switching is not supported.

        Returns:
            list[ContainerItem]: New containers after switching.

        """
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        raise plugin.switch_containers(containers)

    def _collect_plugins(self) -> None:
        # TODO implement
        self._plugins = {}

    def _get_plugin_by_identifier(
        self, identifier: str, validate: bool,
    ) -> Optional[LoadPlugin]:
        if self._plugins is None:
            self._collect_plugins()
        plugin = self._plugins.get(identifier)
        if validate and plugin is None:
            # QUESTION: Use custom exception?
            raise ValueError(
                f"Plugin with identifier '{identifier}' not found."
            )
        return plugin

    def _collect_containers(self) -> None:
        for plugin in sorted(
            self.get_plugins().values(), key=lambda p: p.order
        ):
            plugin.collect_containers()
