from __future__ import annotations

import traceback
from typing import Any


from ayon_core.lib import env_value_to_bool
from ayon_core.pipeline.publish.logic import (
    PublishIterInfo,
    PublishLogic,
    PublishActionResult,
    PublishFailReason,
)
from ayon_core.pipeline.publish.report import PublishReport
from ayon_core.tools.publisher.abstract import (
    AbstractPublisherBackend,
    UIFailInfo,
    UIPublishErrorReport,
)

PUBLISH_EVENT_SOURCE = "publisher.publish.model"


class PublishModel:
    def __init__(self, controller: AbstractPublisherBackend):
        self._controller = controller

        self._logic: PublishLogic = PublishLogic()
        self._logic.set_strict_validation_error_handling(False)
        self._logic.set_log_to_console(
            env_value_to_bool("AYON_PUBLISHER_PRINT_LOGS", default=False)
        )

    def reset(self):
        create_context = self._controller.get_create_context()

        self._logic.reset_from_create_context(create_context)
        self._logic.set_strict_validation_error_handling(False)
        # Allow to change behavior during process lifetime
        self._logic.set_log_to_console(
            env_value_to_bool("AYON_PUBLISHER_PRINT_LOGS", default=False)
        )

        self._emit_event("publish.reset.finished")

    def set_publish_up_validation(self, value: bool) -> None:
        self._logic.set_publish_up_validation(value)

    def start_publish(self, wait: bool = True) -> None:
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        if self._logic.is_running():
            return

        self._emit_event("publish.process.started")

        self._logic.start_publish(wait=False)
        if not wait:
            return

        plugin = None
        item_label = None
        validated = False
        while self.is_running():
            func: PublishIterInfo = self.get_next_process_func()
            if plugin is not func.plugin:
                plugin = func.plugin
                plugin_label = getattr(plugin, "label", None)
                if not plugin_label:
                    plugin_label = plugin.__name__
                self._emit_event(
                "publish.process.plugin.changed",
                {"plugin_label": plugin_label}
                )

            if item_label != func.item_label:
                item_label = func.item_label
                self._emit_event(
                    "publish.process.instance.changed",
                    {"instance_label": item_label}
                )

            func()
            if not validated and self._logic.has_validated():
                validated = True
                self._emit_event("publish.has_validated")

        self.process_stopped()

    def process_stopped(self):
        self._emit_event("publish.process.stopped")
        if self._logic.has_failed():
            pass
        elif self._logic.has_finished():
            self._emit_event("publish.finished")

    def get_next_process_func(self) -> PublishIterInfo:
        return self._logic.get_next_process_func()

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
