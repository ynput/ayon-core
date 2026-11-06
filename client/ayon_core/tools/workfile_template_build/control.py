"""Controller of workfile template builder tool.

Wraps 'AbstractTemplateBuilder' of a host and converts its objects to plain
data that the UI can consume.
"""

from __future__ import annotations

import logging
import os
import traceback
from typing import Any, Callable, Optional

from ayon_core.lib import Logger
from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.lib.events import QueuedEventSystem
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderItem,
    PlaceholderPlugin,
    PlaceholderPreview,
)

from .abstract import (
    BUILD_CONTEXT_CHANGED_TOPIC,
    PLACEHOLDERS_REFRESHED_TOPIC,
    PLACEHOLDER_CREATED_TOPIC,
    PLACEHOLDER_UPDATED_TOPIC,
    PLACEHOLDER_DELETED_TOPIC,
    AbstractTemplateBuilderController,
    ActionResult,
    BuildContextItem,
    BuildStep,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)

# Maximum number of log lines kept from a single build
MAX_BUILD_LOG_LINES = 2000

# Maximum number of builds kept in the history
MAX_BUILD_HISTORY = 5


class _BuildLogHandler(logging.Handler):
    """Collect log records emitted during a template build.

    Args:
        lines (list[str]): List the formatted records are appended to.

    """

    def __init__(self, lines: list[str]):
        super().__init__()
        self._lines = lines
        self.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))

    def emit(self, record):
        try:
            message = self.format(record)
        except Exception:
            return
        self._lines.append(message)
        del self._lines[:-MAX_BUILD_LOG_LINES]


class WorkfileTemplateBuilderController(AbstractTemplateBuilderController):
    """In-process controller of workfile template builder tool.

    Args:
        builder (Optional[AbstractTemplateBuilder]): Template builder
            implementation of the host. Tool shows an explanation message
            when the host does not have one.

    """

    def __init__(self, builder: Optional[AbstractTemplateBuilder] = None):
        self._log = Logger.get_logger(self.__class__.__name__)
        self._builder = builder
        self._event_system = QueuedEventSystem()

        # Cache of collected placeholders by scene identifier. Cleared on
        #   'reset' and after any action that changes the scene.
        self._placeholders_by_id = None

        # Results of the last template build
        self._build_steps: list[BuildStep] = []
        self._build_log: list[str] = []
        self._build_history: list[list[BuildStep]] = []
        self._build_durations: dict[str, float] = {}

        if builder is not None:
            # Builder events are emitted synchronously during the build and
            #   are used to measure duration of each placeholder.
            builder.add_event_callback(
                "template.placeholder_finished",
                self._on_placeholder_finished,
            )

    # --- Events -------------------------------------------------------
    def register_event_callback(self, topic: str, callback: Callable) -> None:
        self._event_system.add_callback(topic, callback)

    def emit_event(
        self,
        topic: str,
        data: Optional[dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> None:
        if data is None:
            data = {}
        self._event_system.emit(topic, data, source)

    # --- Context ------------------------------------------------------
    def get_host_name(self) -> str:
        if self._builder is not None:
            host_name = self._builder.host_name
            if host_name:
                return host_name
        return os.getenv("AYON_HOST_NAME") or "NA"

    def is_builder_available(self) -> bool:
        return self._builder is not None

    def get_project_name(self) -> Optional[str]:
        if self._builder is not None:
            return self._builder.project_name
        return os.getenv("AYON_PROJECT_NAME")

    def get_workfile_name(self) -> Optional[str]:
        if self._builder is None:
            return None
        get_current_workfile = getattr(
            self._builder.host, "get_current_workfile", None
        )
        if get_current_workfile is None:
            return None
        try:
            filepath = get_current_workfile()
        except Exception:
            self._log.debug("Failed to get current workfile.", exc_info=True)
            return None
        if not filepath:
            return None
        return os.path.basename(filepath)

    def get_build_context(self) -> BuildContextItem:
        if self._builder is None:
            return BuildContextItem()
        return BuildContextItem(
            folder_path=self._builder.current_folder_path,
            task_name=self._builder.current_task_name,
            is_override=self._builder.get_context_override() is not None,
        )

    def set_build_context(
        self,
        folder_path: Optional[str] = None,
        task_name: Optional[str] = None,
    ) -> None:
        if self._builder is None:
            return
        self._builder.set_context_override(folder_path, task_name)
        self.emit_event(BUILD_CONTEXT_CHANGED_TOPIC)

    def reset(self) -> None:
        self._placeholders_by_id = None
        if self._builder is not None:
            self._builder.refresh()
        self.emit_event(PLACEHOLDERS_REFRESHED_TOPIC)

    # --- Data ---------------------------------------------------------
    def get_placeholder_plugin_items(self) -> list[PlaceholderPluginItem]:
        plugin_items = [
            PlaceholderPluginItem(
                identifier=identifier,
                label=plugin.label or identifier,
                icon=plugin.icon,
                delete_supported=plugin.is_delete_placeholder_supported(),
                select_supported=plugin.is_select_placeholder_supported(),
                run_supported=plugin.is_run_placeholder_supported(),
            )
            for identifier, plugin in self._get_plugins().items()
        ]
        plugin_items.sort(key=lambda item: item.label.lower())
        return plugin_items

    def get_placeholder_items(self) -> list[PlaceholderItemInfo]:
        return [
            self._create_placeholder_item_info(placeholder)
            for placeholder in self._get_placeholders().values()
        ]

    def get_placeholder_options(
        self,
        plugin_identifier: str,
        placeholder_data: Optional[dict[str, Any]] = None,
    ) -> list[AbstractAttrDef]:
        plugin = self._get_plugin(plugin_identifier)
        if plugin is None:
            return []
        try:
            return list(plugin.get_placeholder_options(placeholder_data))
        except Exception:
            self._log.warning(
                "Failed to collect options of placeholder plugin"
                f" '{plugin_identifier}'.",
                exc_info=True
            )
            return []

    def get_placeholder_preview(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> Optional[PlaceholderPreview]:
        plugin = self._get_plugin(plugin_identifier)
        if plugin is None:
            return None

        try:
            return plugin.get_placeholder_preview(placeholder_data)
        except Exception:
            self._log.warning(
                "Failed to calculate preview of placeholder plugin"
                f" '{plugin_identifier}'.",
                exc_info=True
            )
            return PlaceholderPreview(
                title="Preview failed",
                hint=traceback.format_exc(limit=0).strip(),
                is_error=True,
            )

    def get_placeholder_completions(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> dict[str, list[str]]:
        plugin = self._get_plugin(plugin_identifier)
        if plugin is None:
            return {}

        try:
            return plugin.get_placeholder_completions(placeholder_data) or {}
        except Exception:
            self._log.warning(
                "Failed to collect completions of placeholder plugin"
                f" '{plugin_identifier}'.",
                exc_info=True
            )
            return {}

    # --- Actions ------------------------------------------------------
    def create_placeholder(
        self, plugin_identifier: str, placeholder_data: dict[str, Any]
    ) -> ActionResult:
        plugin = self._get_plugin(plugin_identifier)
        if plugin is None:
            return ActionResult(
                success=False,
                error_title=(
                    f"Placeholder plugin '{plugin_identifier}' is not"
                    " available."
                ),
            )

        # Placeholder plugins are not required to return the created item,
        #   so identifiers before creation are used to find out which
        #   placeholder is the new one.
        known_identifiers = set(self._get_placeholders())

        try:
            placeholder = plugin.create_placeholder(placeholder_data)
        except Exception:
            return self._action_failed("Failed to create placeholder")

        self._invalidate_placeholders()

        scene_identifier = None
        if isinstance(placeholder, PlaceholderItem):
            scene_identifier = placeholder.scene_identifier
        else:
            new_identifiers = set(self._get_placeholders()) - known_identifiers
            if len(new_identifiers) == 1:
                scene_identifier = next(iter(new_identifiers))

        self.emit_event(
            PLACEHOLDER_CREATED_TOPIC,
            {"scene_identifier": scene_identifier},
        )
        return ActionResult(success=True, scene_identifier=scene_identifier)

    def update_placeholder(
        self, scene_identifier: str, placeholder_data: dict[str, Any]
    ) -> ActionResult:
        placeholder = self._get_placeholder(scene_identifier)
        if placeholder is None:
            return self._placeholder_not_found(scene_identifier)

        try:
            self._builder.update_placeholder(placeholder, placeholder_data)
        except Exception:
            return self._action_failed(
                "Failed to save placeholder changes", scene_identifier
            )

        self._invalidate_placeholders()
        self.emit_event(
            PLACEHOLDER_UPDATED_TOPIC,
            {"scene_identifier": scene_identifier},
        )
        return ActionResult(success=True, scene_identifier=scene_identifier)

    def delete_placeholder(self, scene_identifier: str) -> ActionResult:
        placeholder = self._get_placeholder(scene_identifier)
        if placeholder is None:
            return self._placeholder_not_found(scene_identifier)

        try:
            self._builder.delete_placeholder(placeholder)
        except Exception:
            return self._action_failed(
                "Failed to delete placeholder", scene_identifier
            )

        self._invalidate_placeholders()
        self.emit_event(
            PLACEHOLDER_DELETED_TOPIC,
            {"scene_identifier": scene_identifier},
        )
        return ActionResult(success=True, scene_identifier=scene_identifier)

    def select_placeholder(self, scene_identifier: str) -> ActionResult:
        placeholder = self._get_placeholder(scene_identifier)
        if placeholder is None:
            return self._placeholder_not_found(scene_identifier)

        try:
            self._builder.select_placeholder(placeholder)
        except Exception:
            return self._action_failed(
                "Failed to select placeholder in scene", scene_identifier
            )
        return ActionResult(success=True, scene_identifier=scene_identifier)

    def run_placeholder(self, scene_identifier: str) -> ActionResult:
        placeholder = self._get_placeholder(scene_identifier)
        if placeholder is None:
            return self._placeholder_not_found(scene_identifier)

        try:
            self._builder.repopulate_placeholder(placeholder)
        except Exception:
            return self._action_failed(
                "Failed to run placeholder", scene_identifier
            )

        # Running a placeholder can change or remove it from the scene.
        self._invalidate_placeholders()
        return ActionResult(success=True, scene_identifier=scene_identifier)

    def run_template_build(self) -> ActionResult:
        if self._builder is None:
            return ActionResult(
                success=False,
                error_title="Template builder is not available.",
            )

        self._build_steps = []
        self._build_log = []
        self._build_durations = {}

        log_handler = _BuildLogHandler(self._build_log)
        root_logger = Logger.get_root_logger()
        root_logger.addHandler(log_handler)
        try:
            # Re-populates the placeholders that are already in the scene.
            #   The template file is not imported again, so this can be used
            #   to test the template that is currently opened.
            placeholders = self._builder.rebuild_template() or []
        except Exception:
            return self._action_failed("Failed to run template build")
        finally:
            root_logger.removeHandler(log_handler)

        self._build_steps = [
            self._create_build_step(placeholder)
            for placeholder in placeholders
        ]
        if self._build_steps:
            self._store_build_history()

        # The build can change or remove placeholders in the scene.
        self._invalidate_placeholders()

        failed = [step for step in self._build_steps if step.error]
        if failed:
            return ActionResult(
                success=False,
                error_title="{} placeholder(s) failed during build".format(
                    len(failed)
                ),
                error_detail="\n\n".join(
                    "{} ({}):\n{}".format(step.label, step.scene_identifier,
                                          step.error)
                    for step in failed
                ),
            )
        return ActionResult(success=True)

    def get_build_steps(self) -> list[BuildStep]:
        """Steps of the last template build.

        Returns:
            list[BuildStep]: Processed placeholders with status, duration and
                error.

        """
        return [
            BuildStep.from_data(step.to_data()) for step in self._build_steps
        ]

    def get_build_log(self) -> list[str]:
        """Log lines captured during the last template build."""
        return list(self._build_log)

    def get_build_history(self) -> list[list[BuildStep]]:
        """Last build results, oldest first, limited to 5 builds."""
        return [
            [
                BuildStep.from_data(step.to_data())
                for step in build_steps
            ]
            for build_steps in self._build_history
        ]

    def get_last_build_results(self) -> list[tuple[str, str, str]]:
        """Results of the last template build.

        Returns:
            list[tuple[str, str, str]]: Scene identifier, label and error
                message of each placeholder. The error message is empty when
                the placeholder was processed successfully.

        """
        return [
            (step.scene_identifier, step.label, step.error)
            for step in self._build_steps
        ]

    def _on_placeholder_finished(self, event):
        """Store duration of a finished placeholder from builder event."""
        data = event.data or {}
        scene_identifier = data.get("scene_identifier")
        if scene_identifier is None:
            return
        self._build_durations[scene_identifier] = data.get("duration", 0.0)

    def _create_build_step(self, placeholder) -> BuildStep:
        """Create a build step for a processed placeholder."""
        try:
            label = placeholder.plugin.get_placeholder_label(placeholder)
        except Exception:
            label = placeholder.scene_identifier

        errors = placeholder.get_errors()
        return BuildStep(
            scene_identifier=placeholder.scene_identifier,
            label=label or placeholder.scene_identifier,
            order=placeholder.order,
            status="failed" if errors else "succeeded",
            duration=self._build_durations.get(
                placeholder.scene_identifier, 0.0
            ),
            error="\n".join(errors),
        )

    def _store_build_history(self) -> None:
        """Keep results of the last few builds."""
        self._build_history.append(
            [BuildStep.from_data(step.to_data()) for step in self._build_steps]
        )
        del self._build_history[:-MAX_BUILD_HISTORY]

    # --- Implementation -----------------------------------------------
    def _get_plugins(self) -> dict[str, PlaceholderPlugin]:
        if self._builder is None:
            return {}
        return self._builder.placeholder_plugins

    def _get_plugin(
        self, plugin_identifier: str
    ) -> Optional[PlaceholderPlugin]:
        return self._get_plugins().get(plugin_identifier)

    def _invalidate_placeholders(self) -> None:
        """Drop cached placeholders so they are collected from scene again."""
        self._placeholders_by_id = None

    def _get_placeholders(self) -> dict[str, PlaceholderItem]:
        if self._placeholders_by_id is not None:
            return self._placeholders_by_id

        placeholders_by_id = {}
        if self._builder is not None:
            # Placeholder plugins cache collected scene nodes in "populate"
            #   shared data. Clear it so changes made in the scene since the
            #   last collection are picked up. Full 'builder.refresh' is
            #   intentionally avoided, it would also re-create the plugin
            #   objects.
            self._builder.clear_shared_populate_data()
            try:
                placeholders = self._builder.get_placeholders()
            except Exception:
                self._log.warning(
                    "Failed to collect placeholders from scene.",
                    exc_info=True
                )
                placeholders = []

            placeholders_by_id = {
                placeholder.scene_identifier: placeholder
                for placeholder in placeholders
            }

        self._placeholders_by_id = placeholders_by_id
        return placeholders_by_id

    def _get_placeholder(
        self, scene_identifier: str
    ) -> Optional[PlaceholderItem]:
        return self._get_placeholders().get(scene_identifier)

    def _create_placeholder_item_info(
        self, placeholder: PlaceholderItem
    ) -> PlaceholderItemInfo:
        plugin = placeholder.plugin
        plugin_label = plugin.label or plugin.identifier
        try:
            label = plugin.get_placeholder_label(placeholder)
        except Exception:
            self._log.warning(
                "Failed to get label of placeholder"
                f" '{placeholder.scene_identifier}'.",
                exc_info=True
            )
            label = placeholder.scene_identifier

        return PlaceholderItemInfo(
            scene_identifier=placeholder.scene_identifier,
            plugin_identifier=plugin.identifier,
            plugin_label=plugin_label,
            label=label or placeholder.scene_identifier,
            order=placeholder.order,
            icon=plugin.icon,
            data=placeholder.to_dict(),
            delete_supported=plugin.is_delete_placeholder_supported(),
            run_supported=plugin.is_run_placeholder_supported(),
        )

    def _action_failed(
        self, error_title: str, scene_identifier: Optional[str] = None
    ) -> ActionResult:
        self._log.warning(error_title, exc_info=True)
        return ActionResult(
            success=False,
            scene_identifier=scene_identifier,
            error_title=error_title,
            error_detail=traceback.format_exc(),
        )

    def _placeholder_not_found(self, scene_identifier: str) -> ActionResult:
        return ActionResult(
            success=False,
            scene_identifier=scene_identifier,
            error_title=(
                "Placeholder is not available in the scene anymore."
            ),
        )
