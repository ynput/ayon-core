from __future__ import annotations

import traceback
import typing
from typing import Any

import pyblish

from ayon_core.lib import env_value_to_bool
from ayon_core.pipeline.publish.logic import (
    PublishLogic,
    PublishFailReason,
)
from ayon_core.tools.publisher.abstract import (
    UIFailInfo,
    UIPublishErrorReport,
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.publish.logic import (
        PublishIterInfo,
        PublishActionResult,
    )
    from ayon_core.pipeline.publish.report import PublishReport
    from ayon_core.tools.publisher.abstract import AbstractPublisherBackend

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

        self._emit_event("publish.reset.finished")

    def set_publish_stop_after_validation(self, value: bool) -> None:
        self._logic.set_stop_after_validation(value)

    def start_publish(self, wait: bool = True) -> None:
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        if self._logic.is_running():
            return

        self._emit_event("publish.process.started")
        self._publish_iter = self._logic.publish_iter()
        if wait:
            for info in self._publish_iter:
                info()

    def process_next_iter(self) -> bool:
        """Process next iteration of publishing.

        Returns:
            bool: True if publishing is still running, False if finished.

        """
        func: PublishIterInfo | None = None
        if self._publish_iter is not None:
            func = next(self._publish_iter, None)
        if func is None:
            self._emit_event("publish.process.stopped")
            if not self._logic.has_failed() and self._logic.has_finished():
                self._emit_event("publish.finished")
            return False

        plugin = func.plugin
        item_label = func.item_label
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

        func()
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

    def _emit_event(self, topic: str, data: dict[str, Any] | None = None):
        self._controller.emit_event(topic, data, PUBLISH_EVENT_SOURCE)
