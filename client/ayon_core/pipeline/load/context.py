from __future__ import annotations

import copy
import typing
from typing import Any, Optional

from ayon_core.lib import TrackDictChangesItem

from .exceptions import ImmutableKeyError

if typing.TYPE_CHECKING:
    from .plugins import LoadPlugin


class RepresentationContext:
    project_entity: dict[str, Any]
    folder_entity: dict[str, Any]
    product_entity: dict[str, Any]
    version_entity: dict[str, Any]
    representation_entity: dict[str, Any]


class ContainerItem:
    __immutable_keys = (
        "container_id",
        "project_name",
        "representation_id",
        "load_plugin_identifier",
        "version_locked",
    )

    def __init__(
        self,
        container_id: str,
        project_name: str,
        representation_id: str,
        load_plugin: LoadPlugin,
        version_locked: bool = False,
        # UI specific data
        # TODO we should look at these with "fresh eye"
        # - What is their meaning and usage? Does it actually fit?
        # - Should we allow to define "hierarchy" of the items?
        # namespace: str,
        # label: str,
        data: Optional[dict[str, Any]] = None,
        transient_data: Optional[dict[str, Any]] = None,
    ):
        if data is None:
            data = {}
        origin_data = copy.deepcopy(data)
        data.update({
            "container_id": container_id,
            "project_name": project_name,
            "representation_id": representation_id,
            "load_plugin_identifier": load_plugin.identifier,
            "version_locked": version_locked,
        })

        if transient_data is None:
            transient_data = {}

        self._data = data
        self._origin_data = origin_data
        self._transient_data = transient_data
        self._load_plugin = load_plugin

    # --- Dictionary like methods ---
    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def __setitem__(self, key, value):
        # Validate immutable keys
        if key in self.__immutable_keys:
            if value == self._data.get(key):
                return
            # Raise exception if key is immutable and value has changed
            raise ImmutableKeyError(key)

        if key in self._data and self._data[key] == value:
            return

        self._data[key] = value

    def get(self, key, default=None):
        return self._data.get(key, default)

    def pop(self, key, *args, **kwargs):
        # Raise exception if is trying to pop key which is immutable
        if key in self.__immutable_keys:
            raise ImmutableKeyError(key)

        return self._data.pop(key, *args, **kwargs)

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def items(self):
        return self._data.items()
    # ------

    def get_container_id(self) -> str:
        return self._data["container_id"]

    def get_project_name(self) -> str:
        return self._data["project_name"]

    def get_representation_id(self) -> str:
        return self._data["representation_id"]

    def get_load_plugin_identifier(self) -> str:
        return self._data["load_plugin_identifier"]

    def get_version_locked(self) -> bool:
        return self._data["version_locked"]

    def get_data(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    def get_origin_data(self) -> dict[str, Any]:
        return copy.deepcopy(self._origin_data)

    def get_transient_data(self) -> dict[str, Any]:
        return self._transient_data

    def get_changes(self) -> TrackDictChangesItem:
        """Calculate and return changes."""
        return TrackDictChangesItem(self.origin_data, self.get_data())

    id: str = property(get_container_id)
    container_id: str = property(get_container_id)
    project_name: str = property(get_project_name)
    load_plugin_identifier: str = property(get_load_plugin_identifier)
    representation_id: str = property(get_representation_id)
    data: dict[str, Any] = property(get_data)
    origin_data: dict[str, Any] = property(get_origin_data)
    transient_data: dict[str, Any] = property(get_transient_data)
    changes: TrackDictChangesItem = property(get_changes)


class LoadContext:
    def __init__(self) -> None:
        self._shared_data = {}
        self._plugins = None
        self._containers = []
        self._collect_containers()

    def reset(self) -> None:
        self._shared_data = {}
        self._plugins = {}
        self._containers = []
        self._collect_plugins()
        self._collect_containers()

    def get_plugins(self) -> dict[str, LoadPlugin]:
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
        self._containers.extend(containers)

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
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.load_representations(representation_contexts)

    def change_representations(
        self,
        identifier: str,
        items: list[tuple[ContainerItem, RepresentationContext]],
    ) -> None:
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.change_representations(items)

    def remove_containers(
        self,
        identifier: str,
        containers: list[ContainerItem],
    ) -> None:
        plugin = self._get_plugin_by_identifier(identifier, validate=True)
        return plugin.remove_containers(containers)

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
