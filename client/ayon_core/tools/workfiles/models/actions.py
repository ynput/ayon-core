from __future__ import annotations

import threading
import typing
from typing import Any

from ayon_core.lib import Logger
from ayon_core.pipeline.actions import (
    WorkfileAreaType,
    WorkfileActionSelection,
    WorkfileActionsContext,
)
from ayon_core.tools.workfiles.abstract import ActionItem

if typing.TYPE_CHECKING:
    from ayon_core.host import IWorkfileHost
    from ayon_core.tools.workfiles.abstract import (
        ActionSelectionData,
        AbstractWorkfilesBackend,
    )

ACTIONS_MODEL_SENDER = "actions.model"


class WorkfileActionsModel:
    """Model for workfile actions.

    Wraps 'WorkfileActionsContext' and converts selection of the tool to
        selection for action plugins. Uses information that the tool
        already has cached to fill the selection. Action items of plugins
        are converted to 'ActionItem' for the UI.

    Collected action items are cached by the selection. The cache is cleared
        on reset and when an action is triggered, because available actions
        might be different afterwards.

    Args:
        host (IWorkfileHost): Host integration.
        controller (AbstractWorkfilesBackend): Workfiles tool controller.

    """
    def __init__(
        self,
        host: IWorkfileHost,
        controller: AbstractWorkfilesBackend,
    ) -> None:
        self._log = Logger.get_logger(self.__class__.__name__)
        self._host = host
        self._controller = controller
        self._context = WorkfileActionsContext(host=host)
        self._lock = threading.RLock()
        self._context_is_reset = False
        self._items_cache: dict[ActionSelectionData, list[ActionItem]] = {}
        # Changes on each cache clear, so items collected for older state
        #   are not cached
        self._items_generation = 0

    def reset(self) -> None:
        """Plugins are discovered again when are needed next time."""
        with self._lock:
            self._context_is_reset = False
            self._clear_items_cache()

    def prepare_plugin_paths(self) -> None:
        """Prepare settings and plugin paths for the discovery.

        Does not import any plugin, is safe to call out of the main thread.

        """
        self._reset_context()
        self._context.prepare_plugin_paths()

    def prepare_plugins(self) -> None:
        """Discover action plugins.

        Warning:
            Should be called from the main thread, plugin discovery executes
                plugin files which may use host APIs.

        """
        self._reset_context()
        self._context.prepare_plugins()

    def get_cached_action_items(
        self, selection_data: ActionSelectionData
    ) -> list[ActionItem] | None:
        """Get action items for the selection if are already collected.

        Args:
            selection_data (ActionSelectionData): Selection in the tool.

        Returns:
            list[ActionItem] | None: Sorted action items or None if were
                not collected yet.

        """
        with self._lock:
            items = self._items_cache.get(selection_data)
        if items is None:
            return None
        return list(items)

    def get_action_items(
        self, selection_data: ActionSelectionData
    ) -> list[ActionItem]:
        """Get action items for the selection.

        Items are collected if are not cached yet. Can be called out of
            the main thread if plugins were already prepared with
            'prepare_plugins'.

        Args:
            selection_data (ActionSelectionData): Selection in the tool.

        Returns:
            list[ActionItem]: Sorted action items.

        """
        items = self.get_cached_action_items(selection_data)
        if items is not None:
            return items

        with self._lock:
            generation = self._items_generation

        items = self._collect_action_items(selection_data)
        with self._lock:
            # Cache could be cleared in the meantime
            if generation == self._items_generation:
                self._items_cache[selection_data] = items
        return list(items)

    def _clear_items_cache(self) -> None:
        with self._lock:
            self._items_generation += 1
            self._items_cache = {}

    def _collect_action_items(
        self, selection_data: ActionSelectionData
    ) -> list[ActionItem]:
        if not self._controller.is_host_valid():
            return []

        try:
            self._reset_context()
            selection = self._create_selection(selection_data)
            action_items = self._context.get_action_items(selection)
        except Exception:
            self._log.warning(
                "Failed to collect workfile actions.", exc_info=True
            )
            return []

        return [
            ActionItem(
                identifier=item.identifier,
                label=item.label,
                order=item.order,
                group_label=item.group_label,
                icon=item.icon,
                tooltip=item.tooltip,
                description=item.description,
                quick_action=item.quick_action,
                data=item.data,
            )
            for item in action_items
        ]

    def trigger_action(
        self,
        identifier: str,
        selection_data: ActionSelectionData,
        data: dict[str, Any] | None,
        form_values: dict[str, Any],
    ) -> None:
        """Trigger action by plugin identifier.

        Triggers events "workfile_action.started" and
            "workfile_action.finished". Finished event contains "result"
            with 'WorkfileActionResult' and "crashed" if the action raised
            an exception.

        Args:
            identifier (str): Plugin identifier.
            selection_data (ActionSelectionData): Selection in the tool.
            data (dict[str, Any] | None): Additional action item data.
            form_values (dict[str, Any]): Form values.

        """
        event_data = {
            "identifier": identifier,
            "selection": selection_data.to_data(),
            "data": data,
        }
        self._controller.emit_event(
            "workfile_action.started",
            dict(event_data),
            ACTIONS_MODEL_SENDER,
        )
        result = None
        crashed = False
        try:
            self._reset_context()
            result = self._context.execute_action(
                identifier,
                self._create_selection(selection_data),
                data,
                form_values,
            )

        except Exception:
            crashed = True
            self._log.warning(
                f"Failed to execute action '{identifier}'",
                exc_info=True,
            )

        # Available actions might be different after an action
        self._clear_items_cache()

        event_data["result"] = result
        event_data["crashed"] = crashed
        self._controller.emit_event(
            "workfile_action.finished",
            event_data,
            ACTIONS_MODEL_SENDER,
        )

    def _reset_context(self) -> None:
        with self._lock:
            if self._context_is_reset:
                return
            project_name = self._controller.get_current_project_name()
            project_settings = None
            if project_name:
                project_settings = self._controller.get_project_settings(
                    project_name
                )
            self._context.reset(project_name, project_settings)
            self._context_is_reset = True

    def _create_selection(
        self, selection_data: ActionSelectionData
    ) -> WorkfileActionSelection:
        controller = self._controller
        project_name = controller.get_current_project_name()
        folder_id = selection_data.folder_id
        task_id = selection_data.task_id

        folder_entity = task_entity = None
        if folder_id:
            folder_entity = controller.get_folder_entity(
                project_name, folder_id
            )
        if task_id:
            task_entity = controller.get_task_entity(project_name, task_id)

        workdir = None
        if folder_entity and task_entity:
            try:
                workdir = controller.get_workarea_dir_by_context(
                    folder_id, task_id
                )
            except Exception:
                self._log.debug(
                    "Failed to calculate work directory.", exc_info=True
                )

        workfile_info = None
        workfile_entity = None
        repre_entity = None
        if selection_data.published:
            area = WorkfileAreaType.published
            repre_id = selection_data.representation_id
            if repre_id:
                workfile_info = controller.get_cached_published_workfile_info(
                    folder_id, repre_id
                )
                repre_entity = controller.get_cached_representation_entity(
                    repre_id
                )
        else:
            area = WorkfileAreaType.workarea
            if selection_data.rootless_path:
                workfile_info = controller.get_cached_workfile_info(
                    task_id, selection_data.rootless_path
                )
            workfile_entity_id = selection_data.workfile_entity_id
            if workfile_entity_id:
                workfile_entity = next(
                    (
                        entity
                        for entity in controller.get_workfile_entities(task_id)
                        if entity["id"] == workfile_entity_id
                    ),
                    None
                )

        return WorkfileActionSelection(
            project_name,
            area,
            folder_id=folder_id,
            task_id=task_id,
            filepath=selection_data.filepath,
            rootless_path=selection_data.rootless_path,
            workfile_entity_id=selection_data.workfile_entity_id,
            representation_id=selection_data.representation_id,
            workdir=workdir,
            workfile_info=workfile_info,
            host_name=controller.get_host_name(),
            project_entity=controller.get_project_entity(project_name),
            folder_entity=folder_entity,
            task_entity=task_entity,
            workfile_entity=workfile_entity,
            representation_entity=repre_entity,
            project_anatomy=controller.project_anatomy,
            project_settings=controller.project_settings,
        )
