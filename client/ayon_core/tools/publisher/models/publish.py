from __future__ import annotations

import traceback
from functools import partial
from typing import Any, Iterable

import pyblish.plugin

from ayon_core.pipeline.publish.logic import (
    PublishIterInfo,
    PublishLogic,
    PublishActionResult,
    PublishErrorInfo,
    PublishErrorsReport,
)
from ayon_core.pipeline.publish.report import PublishReport
from ayon_core.tools.publisher.abstract import AbstractPublisherBackend

PUBLISH_EVENT_SOURCE = "publisher.publish.model"


def collect_families_from_instances(
    instances: list[pyblish.api.Instance],
    only_active: bool = False,
) -> list[str]:
    """Collect all families for passed publish instances.

    Args:
        instances (list[pyblish.api.Instance]): List of publish instances from
            which are families collected.
        only_active (bool): Return families only for active instances.

    Returns:
        list[str]: Families available on instances.

    """
    all_families = set()
    for instance in instances:
        if only_active:
            if instance.data.get("publish") is False:
                continue
        family = instance.data.get("family")
        if family:
            all_families.add(family)

        families = instance.data.get("families") or tuple()
        for family in families:
            all_families.add(family)

    return list(all_families)


class PublishModel:
    def __init__(self, controller: AbstractPublisherBackend):
        self._controller = controller

        self._logic: PublishLogic = PublishLogic()

    def reset(self):
        create_context = self._controller.get_create_context()

        self._logic.reset_from_create_context(create_context)

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
        if self._logic.has_crashed():
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
        return self._logic.has_crashed()

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

    def get_publish_errors_report(self) -> PublishErrorsReport:
        return self._logic.get_publish_errors_report()

    def get_error_info(self) -> PublishErrorInfo | None:
        return self._logic.get_error_info()

    def store_publish_report(self, filepath: str) -> None:
        report: PublishReport = self.get_publish_report()
        report.store_to_file(filepath)

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

    def _publish_iterator(self) -> Iterable[partial]:
        """Main logic center of publishing.

        Iterator returns `partial` objects with callbacks that should be
        processed in main thread (threaded in future?). Cares about changing
        states of currently processed publish plugin and instance. Also
        change state of processed orders like validation order has passed etc.

        Also stops publishing, if should stop on validation.
        """

        for idx, plugin in enumerate(self._publish_plugins):
            self._publish_progress = idx

            # Check if plugin is over validation order
            if (
                not self._publish_has_validated
                and plugin.order >= self._validation_order
            ):
                self._set_has_validated(True)
                if (
                    self._publish_up_validation
                    or self._publish_has_validation_errors
                ):
                    yield partial(self.stop_publish)

            # Add plugin to publish report
            self._publish_report.add_plugin_iter(
                plugin.id, self._publish_context)

            # WARNING This is hack fix for optional plugins
            if not self._is_publish_plugin_active(plugin):
                self._publish_report.set_plugin_skipped(plugin.id)
                continue

            # Trigger callback that new plugin is going to be processed
            plugin_label = plugin.__name__
            if hasattr(plugin, "label") and plugin.label:
                plugin_label = plugin.label
            self._emit_event(
                "publish.process.plugin.changed",
                {"plugin_label": plugin_label}
            )

            # Plugin is instance plugin
            if plugin.__instanceEnabled__:
                instances = pyblish.logic.instances_by_plugin(
                    self._publish_context, plugin
                )
                if not instances:
                    self._publish_report.set_plugin_skipped(plugin.id)
                    continue

                for instance in instances:
                    if instance.data.get("publish") is False:
                        continue

                    instance_label = (
                        instance.data.get("label")
                        or instance.data["name"]
                    )
                    self._emit_event(
                        "publish.process.instance.changed",
                        {"instance_label": instance_label}
                    )

                    yield partial(
                        self._process_and_continue, plugin, instance
                    )
            else:
                families = collect_families_from_instances(
                    self._publish_context, only_active=True
                )
                plugins = pyblish.logic.plugins_by_families(
                    [plugin], families
                )
                if not plugins:
                    self._publish_report.set_plugin_skipped(plugin.id)
                    continue

                instance_label = (
                    self._publish_context.data.get("label")
                    or self._publish_context.data.get("name")
                    or "Context"
                )
                self._emit_event(
                    "publish.process.instance.changed",
                    {"instance_label": instance_label}
                )
                yield partial(
                    self._process_and_continue, plugin, None
                )

            self._publish_report.set_plugin_passed(plugin.id)

        # Cleanup of publishing process
        self._set_finished(True)
        self._set_progress(self._publish_max_progress)
        yield partial(self.stop_publish)
