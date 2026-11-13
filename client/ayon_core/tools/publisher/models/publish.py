from __future__ import annotations

import traceback
import typing
from typing import Any, Iterable

import pyblish

from ayon_core.lib import env_value_to_bool
from ayon_core.pipeline.publish.logic import (
    PublishLogic,
    PublishFailReason,
)
from ayon_core.tools.publisher.abstract import (
    UIFailInfo,
    UIPublishErrorReport,
    PublishDebugState,
    PublishDebugPluginItem,
    PublishDebugDataItem,
    PublishDebugExecResult,
    PublishDebugValue,
)

from .publish_debug import PublishDebugger

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.publish.logic import (
        PublishIterTask,
        PublishActionResult,
    )
    from ayon_core.pipeline.publish.report import PublishReport
    from ayon_core.tools.publisher.abstract import (
        AbstractPublisherBackend,
        PublishDebugStepType,
    )

PUBLISH_EVENT_SOURCE = "publisher.publish.model"


class CurrentPublishState:
    plugin: pyblish.api.Plugin | None = None
    item_label: str | None = None
    validated: bool = False


class PublishModel:
    def __init__(self, controller: AbstractPublisherBackend):
        self._controller = controller

        self._logic: PublishLogic = PublishLogic(reset=False)
        self._logic.set_strict_validation_error_handling(False)
        self._logic.set_log_to_console(
            env_value_to_bool("AYON_PUBLISHER_PRINT_LOGS", default=False)
        )
        self._publish_iter = None

        self._publish_state = CurrentPublishState()
        self._debugger = PublishDebugger()

    def reset(self):
        create_context = self._controller.get_create_context()

        self._logic.reset_from_create_context(create_context)
        self._logic.set_strict_validation_error_handling(False)
        # Allow to change behavior during process lifetime
        self._logic.set_log_to_console(
            env_value_to_bool("AYON_PUBLISHER_PRINT_LOGS", default=False)
        )
        self._publish_iter = None
        self._publish_state = CurrentPublishState()
        self._debugger.reset()

        self._emit_event("publish.reset.finished")

    def set_publish_stop_after_validation(self, value: bool) -> None:
        self._logic.set_stop_after_validation(value)

    def get_publish_stop_after_validation(self) -> bool:
        return self._logic.get_stop_after_validation()

    def start_publish(
        self,
        wait: bool = True,
        debug_step_type: PublishDebugStepType | None = None,
    ) -> None:
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).

        Args:
            wait (bool): Process all plugins before returning. Debugger
                is not used in that case.
            debug_step_type (PublishDebugStepType | None): How far
                should publishing go before debugger pauses it.

        """
        if self._logic.is_running():
            return

        self._debugger.resume(debug_step_type)
        self._emit_event("publish.process.started")
        self._publish_iter = self._logic.publish_iter()
        if wait:
            for task in self._publish_iter:
                task()

    def process_next_iter(self) -> bool:
        """Process next iteration of publishing.

        Returns:
            bool: True if publishing is still running, False if finished.

        """
        # Task held by debugger is processed first
        task: PublishIterTask | None = self._debugger.pop_pending_task()
        is_resumed_task = task is not None
        if task is None and self._publish_iter is not None:
            task = next(self._publish_iter, None)

        if task is None:
            self._emit_event("publish.process.stopped")
            if not self._logic.has_failed() and self._logic.has_finished():
                self._emit_event("publish.finished")
            return False

        plugin = task.plugin
        item_label = task.item_label
        if (
            plugin is not None
            and self._publish_state.plugin is not plugin
        ):
            self._publish_state.plugin = plugin
            plugin_label = getattr(plugin, "label", None)
            if not plugin_label:
                plugin_label = plugin.__name__
            self._emit_event(
            "publish.process.plugin.changed",
            {"plugin_label": plugin_label}
            )

        if (
            item_label is not None
            and self._publish_state.item_label != item_label
        ):
            self._publish_state.item_label = item_label
            self._emit_event(
                "publish.process.instance.changed",
                {"instance_label": item_label}
            )

        if not is_resumed_task and self._debugger.should_pause(task):
            self._debugger.pause(task)
            self._logic.stop_publish()
            self._emit_event("publish.process.stopped")
            self._emit_event("publish.debug.paused")
            return False

        task()
        self._debugger.task_processed(task)
        if not self._publish_state.validated and self._logic.has_validated():
            self._publish_state.validated = True
            self._emit_event("publish.has_validated")

        return True

    def stop_publish(self) -> None:
        self._logic.stop_publish()

    def is_running(self) -> bool:
        return self._logic.is_running()

    def has_crashed(self) -> bool:
        return self._logic.get_fail_reason() == PublishFailReason.Error

    def has_started(self) -> bool:
        return self._logic.has_started()

    def has_finished(self) -> bool:
        return self._logic.has_finished()

    def has_validated(self) -> bool:
        return self._logic.has_validated()

    def has_validation_errors(self) -> bool:
        return self._logic.has_validation_errors()

    def publish_can_continue(self) -> bool:
        return self._logic.publish_can_continue()

    def get_progress(self) -> int:
        return self._logic.get_progress()

    def get_max_progress(self) -> int:
        return self._logic.get_max_progress()

    def get_publish_report(self) -> PublishReport:
        return self._logic.get_publish_report()

    def get_publish_report_data(self) -> dict[str, Any]:
        return self._logic.get_publish_report_data()

    def get_publish_errors_reports(self) -> list[UIPublishErrorReport]:
        return UIPublishErrorReport.get_items_grouped_by_title(self._logic)

    def get_publish_fail_info(self) -> UIFailInfo | None:
        fail_reason = self._logic.get_fail_reason()
        if fail_reason != PublishFailReason.Error:
            return None

        error_info = self._logic.get_error_info()
        if error_info is None:
            return None
        return UIFailInfo.from_exception(error_info.exception)

    def store_publish_report(self, filepath: str) -> None:
        self._logic.store_publish_report(filepath)

    def set_comment(self, comment: str):
        self._logic.set_comment(comment)

    def run_action(self, plugin_id: str, action_id: str):
        result: PublishActionResult = self._logic.run_action(
            plugin_id, action_id
        )
        if result.success is False:
            exception = result.exception
            action = result.action
            self._emit_event(
                "publish.action.failed",
                {
                    "title": "Action failed",
                    "message": "Action failed.",
                    "traceback": "".join(
                        traceback.format_exception(
                            type(exception),
                            exception,
                            exception.__traceback__
                        )
                    ),
                    "label": action.__name__,
                    "identifier": action.id
                }
            )

        self._controller.emit_card_message("Action finished.")

    def get_debug_state(self) -> PublishDebugState:
        return self._debugger.get_state()

    def get_debug_plugin_items(self) -> list[PublishDebugPluginItem]:
        return self._debugger.get_plugin_items(self._logic)

    def get_breakpoints(self) -> set[str]:
        return self._debugger.get_breakpoints()

    def set_breakpoints(
        self, plugin_names: Iterable[str], enabled: bool
    ) -> None:
        self._debugger.set_breakpoints(plugin_names, enabled)
        self._emit_event("publish.debug.breakpoints.changed")

    def clear_breakpoints(self) -> None:
        self._debugger.clear_breakpoints()
        self._emit_event("publish.debug.breakpoints.changed")

    def get_debug_data_items(self) -> list[PublishDebugDataItem]:
        return self._debugger.get_data_items(self._logic.pyblish_context)

    def get_debug_value_children(
        self, item_id: str, path: tuple[str, ...]
    ) -> list[PublishDebugValue] | None:
        return self._debugger.get_value_children(
            self._logic.pyblish_context, item_id, path
        )

    def debug_execute(
        self, code: str, instance_id: str | None
    ) -> PublishDebugExecResult:
        result = self._debugger.execute(
            code, self._logic.pyblish_context, instance_id
        )
        self._emit_event("publish.debug.code.executed")
        return result

    def _emit_event(self, topic: str, data: dict[str, Any] | None = None):
        self._controller.emit_event(topic, data, PUBLISH_EVENT_SOURCE)
