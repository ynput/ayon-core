from __future__ import annotations

import typing
from typing import Any, Optional
from dataclasses import dataclass

if typing.TYPE_CHECKING:
    from .plugins import LoadPlugin


class RepresentationContext:
    project: dict[str, Any]
    folder: dict[str, Any]
    product: dict[str, Any]
    version: dict[str, Any]
    representation: dict[str, Any]


@dataclass
class ContainerItem:
    id: str
    project_name: str
    representation_id: str
    load_plugin: str
    # How to visually display containers in scene inventory?
    # namespace: str
    # label: str


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
        return self._plugins.get(identifier)

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

    def _collect_plugins(self) -> None:
        # TODO implement
        self._plugins = {}

    def _collect_containers(self) -> None:
        for plugin in sorted(
            self.get_plugins().values(), key=lambda p: p.order
        ):
            plugin.collect_containers()
