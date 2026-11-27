"""Abstraction of workfile template builder tool backend.

The tool is split to a controller (backend) and a UI (frontend). The
controller does all communication with the host and the AYON server, the UI
only shows data that the controller provides. Data objects passed between the
two are plain dataclasses used in the same process.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)

# Event topics emitted by the controller
PLACEHOLDERS_REFRESHED_TOPIC = "placeholders.refreshed"
PLACEHOLDER_CREATED_TOPIC = "placeholder.created"
PLACEHOLDER_UPDATED_TOPIC = "placeholder.updated"
PLACEHOLDER_DELETED_TOPIC = "placeholder.deleted"
BUILD_CONTEXT_CHANGED_TOPIC = "build_context.changed"


class PlaceholderOptionsError(Exception):
    """Options of a placeholder plugin could not be collected."""


class PlaceholderCompletionsError(Exception):
    """Completion suggestions of a placeholder plugin could not be
    collected."""


@dataclass
class PlaceholderDynamicData:
    """Preview and completions calculated together for one editor state."""

    completions: dict[str, list[str]] = field(default_factory=dict)
    completions_error: Optional[str] = None
    preview: Optional[PlaceholderPreview] = None


@dataclass
class BuildStep:
    """Step of a template build for a single placeholder.

    Attributes:
        scene_identifier (str): Scene identifier of the placeholder.
        label (str): Label of the placeholder.
        order (int): Order in which the placeholder was processed.
        status (str): Outcome of the step, one of 'succeeded', 'failed' or
            'skipped'.
        duration (float): Duration of the step in seconds.
        error (str): Error message when the step failed.

    """

    scene_identifier: str
    label: str
    order: int
    # succeeded | failed | skipped
    status: str
    duration: float = 0.0
    error: str = ""


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
    run_supported: bool = False


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
        delete_supported (bool): Placeholder can be removed from the scene.
        run_supported (bool): Placeholder can be re-run in the scene.

    """
    scene_identifier: str
    plugin_identifier: str
    plugin_label: str
    label: str
    order: int = 0
    icon: Optional[dict[str, Any]] = None
    data: dict[str, Any] = field(default_factory=dict)
    delete_supported: bool = False
    run_supported: bool = False


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


@dataclass
class BuildContextItem:
    """Context in which placeholders are previewed and populated.

    Attributes:
        folder_path (Optional[str]): Folder path.
        task_name (Optional[str]): Task name.
        is_override (bool): Context was chosen in the tool and is different
            from the context of the host.

    """
    folder_path: Optional[str] = None
    task_name: Optional[str] = None
    is_override: bool = False

    @property
    def label(self) -> str:
        """Label of the context shown in UI."""
        if not self.folder_path:
            return "No context"
        if not self.task_name:
            return self.folder_path
        return "{} \u00b7 {}".format(self.folder_path, self.task_name)


__all__ = (
    "PLACEHOLDERS_REFRESHED_TOPIC",
    "PLACEHOLDER_CREATED_TOPIC",
    "PLACEHOLDER_UPDATED_TOPIC",
    "PLACEHOLDER_DELETED_TOPIC",
    "BUILD_CONTEXT_CHANGED_TOPIC",

    "PlaceholderOptionsError",
    "PlaceholderCompletionsError",

    "BuildContextItem",

    "PlaceholderPluginItem",
    "PlaceholderItemInfo",
    "ActionResult",

)
