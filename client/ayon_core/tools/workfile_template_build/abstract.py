"""Abstraction of workfile template builder tool backend.

The tool is split to a controller (backend) and a UI (frontend). The
controller does all communication with the host and the AYON server, the UI
only shows data that the controller provides. All objects passed between the
two are plain data or serializable objects, so the UI can potentially live in
a different process than the host.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)

# Event topics emitted by the controller
PLACEHOLDERS_REFRESHED_TOPIC = "placeholders.refreshed"
PLACEHOLDER_CREATED_TOPIC = "placeholder.created"
PLACEHOLDER_UPDATED_TOPIC = "placeholder.updated"
PLACEHOLDER_DELETED_TOPIC = "placeholder.deleted"


@dataclass
class PlaceholderPluginItem:
    """Placeholder plugin available in the current host.

    Attributes:
        identifier (str): Unique identifier of the plugin.
        label (str): Label shown in UI.
        icon (Optional[dict[str, Any]]): Icon definition of the plugin.
        delete_supported (bool): Plugin can remove its placeholders from
            the scene.
        select_supported (bool): Plugin can select its placeholders in the
            host.

    """
    identifier: str
    label: str
    icon: Optional[dict[str, Any]] = None
    delete_supported: bool = False
    select_supported: bool = False

    def to_data(self) -> dict[str, Any]:
        return {
            "identifier": self.identifier,
            "label": self.label,
            "icon": self.icon,
            "delete_supported": self.delete_supported,
            "select_supported": self.select_supported,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PlaceholderPluginItem":
        return cls(**data)


@dataclass
class PlaceholderItemInfo:
    """Placeholder that exists in the current scene.

    Attributes:
        scene_identifier (str): Unique identifier of the placeholder in the
            scene.
        plugin_identifier (str): Identifier of plugin that created it.
        plugin_label (str): Label of plugin that created it.
        label (str): Label of the placeholder itself.
        order (int): Order in which the placeholder is populated.
        icon (Optional[dict[str, Any]]): Icon definition of the plugin.
        data (dict[str, Any]): Placeholder options stored in the scene.

    """
    scene_identifier: str
    plugin_identifier: str
    plugin_label: str
    label: str
    order: int = 0
    icon: Optional[dict[str, Any]] = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_data(self) -> dict[str, Any]:
        return {
            "scene_identifier": self.scene_identifier,
            "plugin_identifier": self.plugin_identifier,
            "plugin_label": self.plugin_label,
            "label": self.label,
            "order": self.order,
            "icon": self.icon,
            "data": self.data,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "PlaceholderItemInfo":
        return cls(**data)


@dataclass
class ActionResult:
    """Result of an action that changes the scene.

    Attributes:
        success (bool): Action finished successfully.
        scene_identifier (Optional[str]): Placeholder the action was about.
        error_title (Optional[str]): Short description of the failure.
        error_detail (Optional[str]): Formatted traceback of the failure.

    """
    success: bool
    scene_identifier: Optional[str] = None
    error_title: Optional[str] = None
    error_detail: Optional[str] = None

    def to_data(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "scene_identifier": self.scene_identifier,
            "error_title": self.error_title,
            "error_detail": self.error_detail,
        }

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> "ActionResult":
        return cls(**data)


class AbstractTemplateBuilderController(ABC):
    """Backend of workfile template builder tool."""

    @abstractmethod
    def register_event_callback(
        self, topic: str, callback: Callable
    ) -> None:
        """Register callback to a topic.

        Args:
            topic (str): Name of the topic.
            callback (Callable): Callback triggered on event.

        """
        pass

    @abstractmethod
    def emit_event(
        self,
        topic: str,
        data: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> None:
        """Emit event to registered callbacks.

        Args:
            topic (str): Name of the topic.
            data (Optional[dict[str, Any]]): Event data.
            source (Optional[str]): Source of the event.

        """
        pass

    @abstractmethod
    def get_host_name(self) -> str:
        """Name of the host the tool runs in.

        Returns:
            str: Host name.

        """
        pass

    @abstractmethod
    def is_builder_available(self) -> bool:
        """Host has implemented template build logic.

        Returns:
            bool: Template builder is available.

        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """Refresh all cached data of the controller."""
        pass

    @abstractmethod
    def get_placeholder_plugin_items(self) -> list[PlaceholderPluginItem]:
        """Placeholder plugins available in the host.

        Returns:
            list[PlaceholderPluginItem]: Available plugins.

        """
        pass

    @abstractmethod
    def get_placeholder_items(self) -> list[PlaceholderItemInfo]:
        """Placeholders that are in the current scene.

        Returns:
            list[PlaceholderItemInfo]: Collected placeholders.

        """
        pass

    @abstractmethod
    def get_placeholder_options(
        self,
        plugin_identifier: str,
        placeholder_data: Optional[dict[str, Any]] = None,
    ) -> list[AbstractAttrDef]:
        """Attribute definitions of placeholder options.

        Args:
            plugin_identifier (str): Identifier of placeholder plugin.
            placeholder_data (Optional[dict[str, Any]]): Values used as
                defaults of the attribute definitions.

        Returns:
            list[AbstractAttrDef]: Attribute definitions.

        """
        pass

    @abstractmethod
    def get_placeholder_preview(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> Optional[PlaceholderPreview]:
        """Preview of what the placeholder would do when populated.

        Args:
            plugin_identifier (str): Identifier of placeholder plugin.
            placeholder_data (dict[str, Any]): Currently filled options.

        Returns:
            Optional[PlaceholderPreview]: Preview of the outcome. None when
                the plugin does not support previews.

        """
        pass

    @abstractmethod
    def get_placeholder_completions(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> dict[str, list[str]]:
        """Completion suggestions for text options of the placeholder.

        Args:
            plugin_identifier (str): Identifier of placeholder plugin.
            placeholder_data (dict[str, Any]): Currently filled options.

        Returns:
            dict[str, list[str]]: Suggestions by option key.

        """
        pass

    @abstractmethod
    def create_placeholder(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> ActionResult:
        """Create new placeholder in the scene.

        Args:
            plugin_identifier (str): Identifier of placeholder plugin.
            placeholder_data (dict[str, Any]): Placeholder options.

        Returns:
            ActionResult: Result with scene identifier of created
                placeholder.

        """
        pass

    @abstractmethod
    def update_placeholder(
        self, scene_identifier: str, placeholder_data: dict[str, Any]
    ) -> ActionResult:
        """Store new options to an existing placeholder.

        Args:
            scene_identifier (str): Scene identifier of the placeholder.
            placeholder_data (dict[str, Any]): Placeholder options.

        Returns:
            ActionResult: Result of the action.

        """
        pass

    @abstractmethod
    def delete_placeholder(self, scene_identifier: str) -> ActionResult:
        """Remove placeholder from the scene.

        Args:
            scene_identifier (str): Scene identifier of the placeholder.

        Returns:
            ActionResult: Result of the action.

        """
        pass

    @abstractmethod
    def select_placeholder(self, scene_identifier: str) -> ActionResult:
        """Select placeholder in the host scene.

        Args:
            scene_identifier (str): Scene identifier of the placeholder.

        Returns:
            ActionResult: Result of the action.

        """
        pass


__all__ = (
    "PLACEHOLDERS_REFRESHED_TOPIC",
    "PLACEHOLDER_CREATED_TOPIC",
    "PLACEHOLDER_UPDATED_TOPIC",
    "PLACEHOLDER_DELETED_TOPIC",

    "PlaceholderPluginItem",
    "PlaceholderItemInfo",
    "ActionResult",

    "AbstractTemplateBuilderController",
)
