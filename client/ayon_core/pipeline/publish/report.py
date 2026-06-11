from __future__ import annotations

from dataclasses import InitVar, dataclass, field
import inspect
from typing import Any, Literal
import traceback
import uuid

import arrow
import pyblish.api

from ayon_core.pipeline.plugin_discover import DiscoverResult

from .lib import get_publish_instance_label


@dataclass
class ReportLog:
    type: Literal["record", "error"]
    instance_id: str | None
    message: str
    filename: str
    lineno: int
    name: str | None = None
    levelno: int | None = None
    levelname: str | None = None
    thread_name: str | None = None
    threadName: InitVar[str | None] = None
    pathname: str | None = None
    msecs: float | None = None
    exc_info: str | None = None
    func: str | None = None
    traceback: str | None = None
    is_validation_error: bool | None = None

    def __post_init__(self, threadName: str | None) -> None:
        # Backward compatibility for camelCase payloads.
        if self.thread_name is None:
            self.thread_name = threadName

    def to_data(self) -> dict[str, Any]:
        if self.type == "error":
            return {
                "type": self.type,
                "msg": self.message,
                "filename": self.filename,
                "lineno": self.lineno,
                "func": self.func,
                "traceback": self.traceback,
                "is_validation_error": self.is_validation_error,
            }
        return {
            "type": "record",
            "msg": self.message,
            "name": self.name,
            "lineno": self.lineno,
            "levelno": self.levelno,
            "levelname": self.levelname,
            "threadName": self.thread_name,
            "filename": self.filename,
            "pathname": self.pathname,
            "msecs": self.msecs,
            "exc_info": self.exc_info,
        }

    @classmethod
    def log_items_from_result(
        cls, result: dict[str, Any], instance_id: str | None = None
    ) -> list[ReportLog]:
        output = []
        records = result.get("records") or []
        for record in records:
            record_exc_info = record.exc_info
            if record_exc_info is not None:
                record_exc_info = "".join(
                    traceback.format_exception(*record_exc_info)
                )

            try:
                msg = record.getMessage()
            except Exception:
                msg = str(record.msg)

            output.append(ReportLog(
                type="record",
                instance_id=instance_id,
                message=msg,
                name=record.name,
                lineno=record.lineno,
                levelno=record.levelno,
                levelname=record.levelname,
                thread_name=record.threadName,
                filename=record.filename,
                pathname=record.pathname,
                msecs=record.msecs,
                exc_info=record_exc_info,
            ))

        exception = result.get("error")
        if exception:
            fname, line_no, func, _ = exception.traceback

            # Conversion of exception into string may crash
            try:
                msg = str(exception)
            except BaseException:
                msg = (
                    "Publisher Controller: ERROR"
                    " - Failed to get exception message"
                )

            # Action result does not have 'is_validation_error'
            output.append(ReportLog(
                type="error",
                instance_id=instance_id,
                message=msg,
                lineno=line_no,
                filename= str(fname),
                func=str(func),
                traceback=exception.formatted_traceback,
                is_validation_error=result.get("is_validation_error", False),
            ))

        return output


@dataclass
class PublishPluginActionReport:
    success: bool
    name: str
    label: str
    logs: list[ReportLog]


@dataclass
class PublishInstanceReportInfo:
    id: str | None
    logs: list[ReportLog]
    process_time: float

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "logs": [log.to_data() for log in self.logs],
            "process_time": self.process_time,
        }

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> PublishInstanceReportInfo:
        instance = result["instance"]
        instance_id = None
        if instance is not None:
            instance_id = instance.id
        return cls(
            id=instance_id,
            logs=ReportLog.log_items_from_result(result),
            process_time=result["duration"]
        )

    @classmethod
    def _extract_log_items(cls, result: dict[str, Any]) -> list[ReportLog]:
        instance = result["instance"]
        instance_id = None
        if instance:
            instance_id = instance.id

        output = []
        records = result.get("records") or []
        for record in records:
            record_exc_info = record.exc_info
            if record_exc_info is not None:
                record_exc_info = "".join(
                    traceback.format_exception(*record_exc_info)
                )

            try:
                msg = record.getMessage()
            except Exception:
                msg = str(record.msg)

            output.append(ReportLog(
                type="record",
                instance_id=instance_id,
                message=msg,
                name=record.name,
                lineno=record.lineno,
                levelno=record.levelno,
                levelname=record.levelname,
                thread_name=record.threadName,
                filename=record.filename,
                pathname=record.pathname,
                msecs=record.msecs,
                exc_info=record_exc_info,
            ))

        exception = result.get("error")
        if exception:
            fname, line_no, func, _ = exception.traceback

            # Conversion of exception into string may crash
            try:
                msg = str(exception)
            except BaseException:
                msg = (
                    "Publisher Controller: ERROR"
                    " - Failed to get exception message"
                )

            # Action result does not have 'is_validation_error'
            output.append(ReportLog(
                type="error",
                instance_id=instance_id,
                message=msg,
                lineno=line_no,
                filename= str(fname),
                func=str(func),
                traceback=exception.formatted_traceback,
                is_validation_error=result.get("is_validation_error", False),
            ))

        return output


@dataclass
class PublishPluginReportInfo:
    """Information about single plugin in publish process."""
    id: str
    name: str
    label: str
    order: float
    filepath: str
    docstring: str | None
    plugin_type: Literal["instance", "context"]
    families: list[str]
    targets: list[str]
    skipped: bool = False
    passed: bool = False
    instances_data: list[PublishInstanceReportInfo] = field(
        default_factory=list
    )
    actions_data: list[PublishPluginActionReport] = field(
        default_factory=list
    )

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "order": self.order,
            "filepath": self.filepath,
            "docstring": self.docstring,
            "plugin_type": self.plugin_type,
            "families": self.families,
            "targets": self.targets,
            "instances_data": self.instances_data,
            "actions_data": self.actions_data,
            "skipped": self.skipped,
            "passed": self.passed,
        }

    @classmethod
    def from_plugin(cls, plugin: pyblish.api.Plugin) -> PublishPluginReportInfo:
        label = None
        if hasattr(plugin, "label"):
            label = plugin.label

        plugin_type = "instance" if plugin.__instanceEnabled__ else "context"
        # Get docstring
        # NOTE we do care only about docstring from the plugin so we can't
        #   use 'inspect.getdoc' which also looks for docstring in parent
        #   classes.
        docstring = getattr(plugin, "__doc__", None)
        if docstring:
            docstring = inspect.cleandoc(docstring)
        return cls(
            id=plugin.id,
            name=plugin.__name__,
            label=label,
            order=plugin.order,
            filepath=inspect.getfile(plugin),
            docstring=docstring,
            plugin_type=plugin_type,
            families=list(plugin.families),
            targets=list(plugin.targets),
        )


class PublishReportMaker:
    """Report for single publishing process.

    Report keeps current state of publishing and currently processed plugin.
    """
    report_version = "1.1.1"

    def __init__(
        self,
        publish_plugins: list[pyblish.api.Plugin] | None = None,
        crashed_file_paths: dict[str, str] | None = None,
        blocking_crashed_paths: set[str] | None = None,
    ) -> None:
        if publish_plugins is None:
            publish_plugins = []

        if crashed_file_paths is None:
            crashed_file_paths = {}

        if blocking_crashed_paths is None:
            blocking_crashed_paths = set()

        self._current_plugin_id: str | None = None

        self._crashed_file_paths: dict[str, str] = crashed_file_paths
        self._blocking_crashed_paths: set[str] = blocking_crashed_paths

        self._all_instances_by_id: dict[str, pyblish.api.Instance] = {}
        self._plugin_info_by_id: dict[str, PublishPluginReportInfo] = {}

        self._prepare_publish_plugin_items(publish_plugins)

    def reset(
        self,
        publish_plugins: list[pyblish.api.Plugin] | None = None,
        crashed_file_paths: dict[str, str] | None = None,
        blocking_crashed_paths: set[str] | None = None,
    ) -> None:
        """Reset report and clear all data."""
        if publish_plugins is None:
            publish_plugins = []

        if crashed_file_paths is None:
            crashed_file_paths = {}

        if blocking_crashed_paths is None:
            blocking_crashed_paths = set()

        self._current_plugin_id = None

        self._crashed_file_paths = crashed_file_paths
        self._blocking_crashed_paths = blocking_crashed_paths

        self._all_instances_by_id = {}
        self._plugin_info_by_id = {}

        self._prepare_publish_plugin_items(publish_plugins)

    def add_plugin_iter(
        self, plugin_id: str, context: pyblish.api.Context
    ) -> None:
        """Add report about single iteration of plugin."""
        for instance in context:
            self._all_instances_by_id[instance.id] = instance

        self._current_plugin_id = plugin_id

    def set_plugin_passed(self, plugin_id: str) -> None:
        plugin_info = self._plugin_info_by_id[plugin_id]
        plugin_info.passed = True

    def set_plugin_skipped(self, plugin_id: str) -> None:
        """Set that current plugin has been skipped."""
        plugin_info = self._plugin_info_by_id[plugin_id]
        plugin_info.skipped = True

    def add_result(self, plugin_id: str, result: dict[str, Any]) -> None:
        """Handle result of one plugin and it's instance."""
        plugin_info = self._plugin_info_by_id[plugin_id]
        plugin_info.instances_data.append(
            PublishInstanceReportInfo.from_result(result)
        )

    def add_action_result(
        self, action: pyblish.api.Action, result: dict[str, Any]
    ) -> None:
        """Add result of single action."""
        plugin = result["plugin"]

        plugin_info = self._plugin_info_by_id[plugin.id]

        action_name = action.__name__
        action_label = action.label or action_name
        plugin_info.actions_data.append(PublishPluginActionReport(
            success=result["success"],
            name=action_name,
            label=action_label,
            logs=ReportLog.log_items_from_result(result),
        ))

    def get_report(
        self, publish_context: pyblish.api.Context
    ) -> dict[str, Any]:
        """Report data with all details of current state."""

        now = arrow.utcnow().to("local")
        instances_details = {
            instance.id: self._extract_instance_data(
                instance, instance in publish_context
            )
            for instance in self._all_instances_by_id.values()
        }

        plugins_data = []
        current_item = self._plugin_info_by_id.get(self._current_plugin_id)
        for plugin_info in self._plugin_info_by_id.values():
            plugin_data = plugin_info.to_data()

            # Ensure the current plug-in is marked as `passed` in the result
            # so that it shows on reports for paused publishes
            if plugin_info is current_item:
                plugin_data["passed"] = True
            plugins_data.append(plugin_data)

        return {
            "plugins_data": plugins_data,
            "instances": instances_details,
            "context": self._extract_context_data(publish_context),
            "crashed_file_paths": dict(self._crashed_file_paths),
            "blocking_crashed_paths": list(self._blocking_crashed_paths),
            "id": uuid.uuid4().hex,
            "created_at": now.isoformat(),
            "report_version": self.report_version,
        }

    def _prepare_publish_plugin_items(
        self, publish_plugins: list[pyblish.api.Plugin]
    ) -> None:
        for plugin in publish_plugins:
            if plugin.id in self._plugin_info_by_id:
                # A plugin would be processed more than once. What can cause it:
                #   - there is a bug in controller
                #   - plugin class is imported into multiple files
                #       - this can happen even with base classes from 'pyblish'
                raise ValueError(
                    f"Plugin '{plugin}' is already stored"
                )

            self._plugin_info_by_id[plugin.id] = (
                PublishPluginReportInfo.from_plugin(plugin)
            )

    def _extract_context_data(
        self, context: pyblish.api.Context
    ) -> dict[str, Any]:
        context_label = "Context"
        if context is not None:
            context_label = context.data.get("label")
        return {
            "label": context_label
        }

    def _extract_instance_data(
        self, instance: pyblish.api.Instance, exists: bool
    ) -> dict[str, Any]:
        return {
            "name": instance.data.get("name"),
            "label": get_publish_instance_label(instance),
            "product_type": instance.data.get("productType"),
            "product_base_type": instance.data.get("productBaseType"),
            "family": instance.data.get("family"),
            "families": instance.data.get("families") or [],
            "exists": exists,
            "creator_identifier": instance.data.get("creator_identifier"),
            "instance_id": instance.data.get("instance_id"),
        }
