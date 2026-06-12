from __future__ import annotations

from copy import deepcopy
from dataclasses import InitVar, dataclass, field
import inspect
import logging
from typing import Any, Literal, Iterable, Generator
import traceback
import uuid

import arrow
import pyblish.api

from ayon_core.pipeline.plugin_discover import DiscoverResult

from .lib import get_publish_instance_label


@dataclass
class ReportLog:
    type: Literal["record", "error"]
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
        cls, result: dict[str, Any]
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

    def to_data(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "name": self.name,
            "label": self.label,
            "logs": [log.to_data() for log in self.logs],
        }


@dataclass
class PublishProcessReport:
    instance_id: str | None
    logs: list[ReportLog]
    process_time: float

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.instance_id,
            "logs": [log.to_data() for log in self.logs],
            "process_time": self.process_time,
        }

    @classmethod
    def from_result(cls, result: dict[str, Any]) -> PublishProcessReport:
        instance = result["instance"]
        instance_id = None
        if instance is not None:
            instance_id = instance.id
        return cls(
            instance_id=instance_id,
            logs=ReportLog.log_items_from_result(result),
            process_time=result["duration"],
        )


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
    process_reports: list[PublishProcessReport] = field(
        default_factory=list
    )
    actions_reports: list[PublishPluginActionReport] = field(
        default_factory=list
    )

    def to_data(self, current_plugin_id: str | None = None) -> dict[str, Any]:
        passed = self.passed
        if current_plugin_id == self.id:
            passed = True
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
            "instances_data": [r.to_data() for r in self.process_reports],
            "actions_data": [r.to_data() for r in self.actions_reports],
            "skipped": self.skipped,
            "passed": passed,
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


@dataclass
class PublishContextInfo:
    label: str

    @classmethod
    def new(cls):
        return PublishContextInfo("Context")

    def to_data(self) -> dict[str, Any]:
        return {
            "label": self.label,
        }


@dataclass
class PublishInstanceInfo:
    id: str
    name: str | None
    label: str | None
    product_type: str | None
    product_base_type: str | None
    family: str | None
    families: list[str]
    creator_identifier: str | None
    create_instance_id: str | None
    exists: bool

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "product_type": self.product_type,
            "product_base_type": self.product_base_type,
            "family": self.family,
            "families": list(self.families),
            "creator_identifier": self.creator_identifier,
            "instance_id": self.create_instance_id,
            "exists": self.exists,
        }

    @classmethod
    def from_instance(
        cls, instance: pyblish.api.Instance
    ) -> PublishInstanceInfo:
        return cls(
            id=instance.id,
            name=instance.data.get("name"),
            label=get_publish_instance_label(instance),
            product_type=instance.data.get("productType"),
            product_base_type=instance.data.get("productBaseType"),
            family=instance.data.get("family"),
            families=instance.data.get("families") or [],
            creator_identifier=instance.data.get("creator_identifier"),
            create_instance_id=instance.data.get("instance_id"),
            exists=instance in instance.context,
        )


def _new_id() -> str:
    return uuid.uuid4().hex


def _new_created_at() -> str:
    return arrow.utcnow().to("local").isoformat()


@dataclass
class LogsSummary:
    warned_instance_ids: set[str]
    errored_instance_ids: set[str]
    errored_plugin_ids: set[str]


@dataclass
class PublishReport:
    # TODO add conversions from older versions
    version: str = "1.1.1"
    id: str = field(default_factory=_new_id)
    created_at: str = field(default_factory=_new_created_at)
    crashed_filepaths: dict[str, str] = field(default_factory=dict)
    blocking_crashed_paths: list[str] = field(default_factory=list)
    plugins_info: list[PublishPluginReportInfo] = field(default_factory=list)
    instances_by_id: dict[str, PublishInstanceInfo] = field(
        default_factory=dict
    )
    context: PublishContextInfo = field(
        default_factory=PublishContextInfo.new
    )

    def to_data(self, current_plugin_id: str | None = None) -> dict[str, Any]:
        return {
            "plugins_data": [
                p.to_data(current_plugin_id) for p in self.plugins_info
            ],
            "instances": {
                instance_id: instance_info.to_data()
                for instance_id, instance_info in self.instances_by_id.items()
            },
            "context": self.context.to_data(),
            "crashed_file_paths": deepcopy(self.crashed_filepaths),
            "blocking_crashed_paths": list(self.blocking_crashed_paths),
            "created_at": self.created_at,
            "report_version": self.version,
            "id": self.id,
        }

    def update_created_at(self) -> None:
        self.created_at = _new_created_at()

    def set_publish_instances(
        self, instances: Iterable[pyblish.api.Instance]
    ) -> None:
        instances_by_id = {
            instance.id: PublishInstanceInfo.from_instance(instance)
            for instance in instances
        }
        self.instances_by_id = instances_by_id

    def get_logs_summary(self) -> LogsSummary:
        warned_instance_ids = set()
        errored_instance_ids = set()
        errored_plugin_ids = set()
        for plugin_info in self.plugins_info:
            for process_report in plugin_info.process_reports:
                for log in process_report.logs:
                    if log.type == "error":
                        errored_instance_ids.add(process_report.instance_id)
                        errored_plugin_ids.add(plugin_info.id)
                    elif (
                        log.type == "record"
                        and log.levelno
                        and log.levelno >= logging.WARNING
                    ):
                        warned_instance_ids.add(process_report.instance_id)

        return LogsSummary(
            warned_instance_ids=warned_instance_ids,
            errored_instance_ids=errored_instance_ids,
            errored_plugin_ids=errored_plugin_ids,
        )

    def iter_logs(
        self,
        plugin_ids_filter: set[str | None] | None = None,
        instance_ids_filter: set[str | None] | None = None,
    ) -> Generator[tuple[str, str | None, ReportLog]]:
        if plugin_ids_filter is not None and not plugin_ids_filter:
            return

        if instance_ids_filter is not None and not instance_ids_filter:
            return

        for plugin_info in self.plugins_info:
            if (
                plugin_ids_filter is not None
                and plugin_info.id not in plugin_ids_filter
            ):
                continue

            for process_report in plugin_info.process_reports:
                if (
                    instance_ids_filter is not None
                    and process_report.instance_id not in instance_ids_filter
                ):
                    continue

                for log in process_report.logs:
                    yield plugin_info.id, process_report.instance_id, log


class PublishReportMaker:
    """Report for single publishing process.

    Report keeps current state of publishing and currently processed plugin.
    """
    def __init__(
        self,
        publish_plugins: list[pyblish.api.Plugin] | None = None,
        crashed_filepaths: dict[str, str] | None = None,
        blocking_crashed_paths: set[str] | None = None,
    ) -> None:
        if publish_plugins is None:
            publish_plugins = []

        if crashed_filepaths is None:
            crashed_filepaths = {}

        if blocking_crashed_paths is None:
            blocking_crashed_paths = set()

        # Make sure plugins are sorted
        # TODO try to comment this to find out if it is necessary...
        publish_plugins.sort(key=lambda p: p.order)

        # Track information if instances have been updated since
        #   last report generation.
        self._instances_updated: bool = False

        # Current plugin id which is being processed.
        self._current_plugin_id: str | None = None

        self._plugin_info_by_id: dict[str, PublishPluginReportInfo] = {}
        self._all_instances_by_id: dict[str, pyblish.api.Instance] = {}
        self._report = PublishReport(
            crashed_filepaths=crashed_filepaths,
            blocking_crashed_paths=list(blocking_crashed_paths),
        )
        self._prepare_publish_plugin_items(publish_plugins)

    @property
    def report_version(self) -> str:
        return self._report.version

    def get_current_plugin_id(self) -> str | None:
        return self._current_plugin_id

    current_plugin_id = property(get_current_plugin_id)

    def reset(
        self,
        publish_plugins: list[pyblish.api.Plugin] | None = None,
        crashed_filepaths: dict[str, str] | None = None,
        blocking_crashed_paths: set[str] | None = None,
    ) -> None:
        """Reset report and clear all data."""
        if publish_plugins is None:
            publish_plugins = []

        if crashed_filepaths is None:
            crashed_filepaths = {}

        if blocking_crashed_paths is None:
            blocking_crashed_paths = set()

        self._instances_updated = False
        self._current_plugin_id = None
        self._plugin_info_by_id = {}
        self._all_instances_by_id = {}

        self._report = PublishReport(
            crashed_filepaths=crashed_filepaths,
            blocking_crashed_paths=list(blocking_crashed_paths),
        )

        self._prepare_publish_plugin_items(publish_plugins)

    def reset_with_discover_results(
        self,
        creator_discover_result: DiscoverResult,
        convertor_discover_result: DiscoverResult,
        publish_discover_result: DiscoverResult,
        blocking_crashed_paths: set[str],
    ) -> None:
        """Reset report and set discover results."""

        crashed_filepaths = {}
        for report in (
            creator_discover_result,
            convertor_discover_result,
            publish_discover_result,
        ):
            items = report.crashed_file_paths.items()
            for filepath, exc_info in items:
                crashed_filepaths[filepath] = "".join(
                    traceback.format_exception(*exc_info)
                )

        self.reset(
            publish_discover_result.plugins,
            crashed_filepaths,
            blocking_crashed_paths,
        )

    def add_plugin_iter(
        self, plugin_id: str, context: pyblish.api.Context
    ) -> None:
        """Add report about single iteration of plugin."""
        self.update_publish_instances(context)

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
        plugin_info.process_reports.append(
            PublishProcessReport.from_result(result)
        )

    def add_action_result(
        self, action: pyblish.api.Action, result: dict[str, Any]
    ) -> None:
        """Add result of single action."""
        plugin = result["plugin"]

        plugin_info = self._plugin_info_by_id[plugin.id]

        action_name = action.__name__
        action_label = action.label or action_name
        plugin_info.actions_reports.append(PublishPluginActionReport(
            success=result["success"],
            name=action_name,
            label=action_label,
            logs=ReportLog.log_items_from_result(result),
        ))

    def get_report(self) -> PublishReport:
        self._update_instances()
        return self._report

    def get_report_data(self) -> dict[str, Any]:
        self._update_instances()
        return self._report.to_data(
            current_plugin_id=self._current_plugin_id,
        )

    def update_publish_instances(
        self, publish_context: pyblish.api.Context
    ) -> None:
        """Report data with all details of current state."""
        for instance in publish_context:
            if instance.id not in self._all_instances_by_id:
                self._instances_updated = False
                self._all_instances_by_id[instance.id] = instance

    def _update_instances(self) -> None:
        if self._instances_updated:
            return

        self._report.set_publish_instances(
            self._all_instances_by_id.values()
        )
        self._instances_updated = True

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

            plugin_info = PublishPluginReportInfo.from_plugin(plugin)
            self._plugin_info_by_id[plugin.id] = plugin_info
            self._report.plugins_info.append(plugin_info)

