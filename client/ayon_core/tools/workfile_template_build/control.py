"""Controller of workfile template builder tool.

Wraps 'AbstractTemplateBuilder' of a host and converts its objects to plain
data that the UI can consume.
"""

from __future__ import annotations

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
    PLACEHOLDERS_REFRESHED_TOPIC,
    PLACEHOLDER_CREATED_TOPIC,
    PLACEHOLDER_UPDATED_TOPIC,
    PLACEHOLDER_DELETED_TOPIC,
    AbstractTemplateBuilderController,
    ActionResult,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)


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
