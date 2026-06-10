"""Publish report generation and persistence.

Provides :class:`PublishReportMaker` for building a report that is compatible
with the Publish report viewer, plus helpers for saving it to disk.

Environment variable ``AYON_PUBLISH_REPORT_PATH`` can point to either:
- a file path  → the report JSON is written to that exact file
- a directory  → the report JSON is written as ``<dir>/<report_id>.json``

When the env var is not set, :func:`save_publish_report` falls back to the
default launcher-local reports directory so the report shows up in the
Publish report viewer.
"""

import copy
import inspect
import json
import os
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import arrow
import pyblish.api

from ayon_core.lib import get_launcher_local_dir
from ayon_core.pipeline.plugin_discover import DiscoverResult
from ayon_core.pipeline.publish.lib import get_publish_instance_label


def get_publish_reports_dir() -> str:
    """Root directory where publish reports are stored for the report viewer.

    Returns:
        str: Path to directory where reports are stored.
    """
    report_dir = get_launcher_local_dir("publish_report_viewer")
    os.makedirs(report_dir, exist_ok=True)
    return report_dir


def get_publish_report_path_from_env() -> Optional[str]:
    """Return the publish report output path from the environment.

    The env var ``AYON_PUBLISH_REPORT_PATH`` may be set to a file or directory
    path.

    Returns:
        str | None: Value of ``AYON_PUBLISH_REPORT_PATH`` or ``None``.
    """
    return os.getenv("AYON_PUBLISH_REPORT_PATH")


def save_publish_report(
    report_data: Dict[str, Any],
    report_path: Optional[str] = None,
) -> str:
    """Write *report_data* to disk as JSON.

    Args:
        report_data: The report dict as returned by
            :meth:`PublishReportMaker.get_report`.
        report_path: Destination path.  May be an existing directory (the
            file is placed inside it as ``<report_id>.json``), an explicit
            file path, or ``None``.  When ``None`` the report is written to
            the default :func:`get_publish_reports_dir` so it appears in the
            Publish report viewer.

    Returns:
        str: Absolute path of the written JSON file.
    """
    if report_path is None:
        dest = Path(get_publish_reports_dir()) / f"{report_data['id']}.json"
    else:
        dest = Path(report_path)
        if dest.is_dir():
            dest = dest / f"{report_data['id']}.json"

    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as fh:
        json.dump(report_data, fh)
    return str(dest)


class PublishReportMaker:
    """Accumulates pyblish results and produces a viewer-compatible report.

    The report format is the same JSON schema consumed by the Publish report
    viewer (``ayon_core.tools.publisher.publish_report_viewer``).

    Typical usage::

        report_maker = PublishReportMaker(
            create_context.creator_discover_result,
            create_context.convertor_discover_result,
            create_context.publish_discover_result,
        )
        for result in pyblish.util.publish_iter(...):
            plugin = result["plugin"]
            if plugin.id != current_plugin_id:
                report_maker.add_plugin_iter(plugin.id, pyblish_context)
                current_plugin_id = plugin.id
            report_maker.add_result(plugin.id, result)
            if not result["error"]:
                report_maker.set_plugin_passed(plugin.id)

        report_data = report_maker.get_report(pyblish_context)
        save_publish_report(report_data)
    """

    def __init__(
        self,
        creator_discover_result: Optional[DiscoverResult] = None,
        convertor_discover_result: Optional[DiscoverResult] = None,
        publish_discover_result: Optional[DiscoverResult] = None,
        blocking_crashed_paths: Optional[List[str]] = None,
    ):
        self._create_discover_result: Union[DiscoverResult, None] = None
        self._convert_discover_result: Union[DiscoverResult, None] = None
        self._publish_discover_result: Union[DiscoverResult, None] = None

        self._blocking_crashed_paths: List[str] = []

        self._all_instances_by_id: Dict[str, pyblish.api.Instance] = {}
        self._plugin_data_by_id: Dict[str, Any] = {}
        self._current_plugin_id: Optional[str] = None

        self.reset(
            creator_discover_result,
            convertor_discover_result,
            publish_discover_result,
            blocking_crashed_paths,
        )

    def reset(
        self,
        creator_discover_result: Union[DiscoverResult, None],
        convertor_discover_result: Union[DiscoverResult, None],
        publish_discover_result: Union[DiscoverResult, None],
        blocking_crashed_paths: Union[List[str], None],
    ):
        """Reset report and clear all data."""

        self._create_discover_result = creator_discover_result
        self._convert_discover_result = convertor_discover_result
        self._publish_discover_result = publish_discover_result
        self._blocking_crashed_paths = blocking_crashed_paths or []

        self._all_instances_by_id = {}
        self._plugin_data_by_id = {}
        self._current_plugin_id = None

        publish_plugins = []
        if publish_discover_result is not None:
            publish_plugins = publish_discover_result.plugins

        for plugin in publish_plugins:
            self._add_plugin_data_item(plugin)

    def add_plugin_iter(self, plugin_id: str, context: pyblish.api.Context):
        """Add report about single iteration of plugin."""
        for instance in context:
            self._all_instances_by_id[instance.id] = instance

        self._current_plugin_id = plugin_id

    def set_plugin_passed(self, plugin_id: str):
        plugin_data = self._plugin_data_by_id[plugin_id]
        plugin_data["passed"] = True

    def set_plugin_skipped(self, plugin_id: str):
        """Set that current plugin has been skipped."""
        plugin_data = self._plugin_data_by_id[plugin_id]
        plugin_data["skipped"] = True

    def add_result(self, plugin_id: str, result: Dict[str, Any]):
        """Handle result of one plugin and it's instance."""

        instance = result["instance"]
        instance_id = None
        if instance is not None:
            instance_id = instance.id
        plugin_data = self._plugin_data_by_id[plugin_id]
        plugin_data["instances_data"].append({
            "id": instance_id,
            "logs": self._extract_instance_log_items(result),
            "process_time": result["duration"]
        })

    def add_action_result(
        self, action: pyblish.api.Action, result: Dict[str, Any]
    ):
        """Add result of single action."""
        plugin = result["plugin"]

        store_item = self._plugin_data_by_id[plugin.id]

        action_name = action.__name__
        action_label = action.label or action_name
        log_items = self._extract_log_items(result)
        store_item["actions_data"].append({
            "success": result["success"],
            "name": action_name,
            "label": action_label,
            "logs": log_items
        })

    def get_report(
        self, publish_context: pyblish.api.Context
    ) -> Dict[str, Any]:
        """Report data with all details of current state."""

        now = arrow.utcnow().to("local")
        instances_details = {
            instance.id: self._extract_instance_data(
                instance, instance in publish_context
            )
            for instance in self._all_instances_by_id.values()
        }

        plugins_data_by_id = copy.deepcopy(
            self._plugin_data_by_id
        )

        # Ensure the current plug-in is marked as `passed` in the result
        # so that it shows on reports for paused publishes
        if self._current_plugin_id is not None:
            current_plugin_data = plugins_data_by_id.get(
                self._current_plugin_id
            )
            if current_plugin_data and not current_plugin_data["passed"]:
                current_plugin_data["passed"] = True

        reports = []
        if self._create_discover_result is not None:
            reports.append(self._create_discover_result)

        if self._convert_discover_result is not None:
            reports.append(self._convert_discover_result)

        if self._publish_discover_result is not None:
            reports.append(self._publish_discover_result)

        crashed_file_paths = {}
        for report in reports:
            items = report.crashed_file_paths.items()
            for filepath, exc_info in items:
                crashed_file_paths[filepath] = "".join(
                    traceback.format_exception(*exc_info)
                )

        return {
            "plugins_data": list(plugins_data_by_id.values()),
            "instances": instances_details,
            "context": self._extract_context_data(publish_context),
            "crashed_file_paths": crashed_file_paths,
            "blocking_crashed_paths": list(self._blocking_crashed_paths),
            "id": uuid.uuid4().hex,
            "created_at": now.isoformat(),
            "report_version": "1.1.1",
        }

    def _add_plugin_data_item(self, plugin: pyblish.api.Plugin):
        if plugin.id in self._plugin_data_by_id:
            # A plugin would be processed more than once. What can cause it:
            #   - there is a bug in controller
            #   - plugin class is imported into multiple files
            #       - this can happen even with base classes from 'pyblish'
            raise ValueError(
                "Plugin '{}' is already stored".format(str(plugin)))

        plugin_data_item = self._create_plugin_data_item(plugin)
        self._plugin_data_by_id[plugin.id] = plugin_data_item

    def _create_plugin_data_item(
        self, plugin: pyblish.api.Plugin
    ) -> Dict[str, Any]:
        label = None
        if hasattr(plugin, "label"):
            label = plugin.label

        plugin_type = "instance" if plugin.__instanceEnabled__ else "context"
        # NOTE we do care only about docstring from the plugin so we can't
        #   use 'inspect.getdoc' which also looks for docstring in parent
        #   classes.
        docstring = getattr(plugin, "__doc__", None)
        if docstring:
            docstring = inspect.cleandoc(docstring)
        return {
            "id": plugin.id,
            "name": plugin.__name__,
            "label": label,
            "order": plugin.order,
            "filepath": inspect.getfile(plugin),
            "docstring": docstring,
            "plugin_type": plugin_type,
            "families": list(plugin.families),
            "targets": list(plugin.targets),
            "instances_data": [],
            "actions_data": [],
            "skipped": False,
            "passed": False
        }

    def _extract_context_data(
        self, context: pyblish.api.Context
    ) -> Dict[str, Any]:
        context_label = "Context"
        if context is not None:
            context_label = context.data.get("label")
        return {
            "label": context_label
        }

    def _extract_instance_data(
        self, instance: pyblish.api.Instance, exists: bool
    ) -> Dict[str, Any]:
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

    def _extract_instance_log_items(
        self, result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        instance = result["instance"]
        instance_id = None
        if instance:
            instance_id = instance.id

        log_items = self._extract_log_items(result)
        for item in log_items:
            item["instance_id"] = instance_id
        return log_items

    def _extract_log_items(self, result: Dict[str, Any]) -> List[Dict[str, Any]]:
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

            output.append({
                "type": "record",
                "msg": msg,
                "name": record.name,
                "lineno": record.lineno,
                "levelno": record.levelno,
                "levelname": record.levelname,
                "threadName": record.threadName,
                "filename": record.filename,
                "pathname": record.pathname,
                "msecs": record.msecs,
                "exc_info": record_exc_info
            })

        exception = result.get("error")
        if exception:
            fname, line_no, func, _ = exception.traceback

            try:
                msg = str(exception)
            except BaseException:
                msg = (
                    "Publisher Controller: ERROR"
                    " - Failed to get exception message"
                )

            # Action result does not have 'is_validation_error'
            is_validation_error = result.get("is_validation_error", False)
            output.append({
                "type": "error",
                "is_validation_error": is_validation_error,
                "msg": msg,
                "filename": str(fname),
                "lineno": str(line_no),
                "func": str(func),
                "traceback": exception.formatted_traceback
            })

        return output
