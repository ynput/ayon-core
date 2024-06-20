import uuid
import copy
import traceback

import arrow

from ayon_core.pipeline.publish import get_publish_instance_label


class PublishReportMaker:
    """Report for single publishing process.

    Report keeps current state of publishing and currently processed plugin.
    """

    def __init__(self, controller):
        self.controller = controller
        self._create_discover_result = None
        self._convert_discover_result = None
        self._publish_discover_result = None

        self._plugin_data_by_id = {}
        self._current_plugin = None
        self._current_plugin_data = {}
        self._all_instances_by_id = {}
        self._current_context = None

    def reset(self, context, create_context):
        """Reset report and clear all data."""

        self._create_discover_result = create_context.creator_discover_result
        self._convert_discover_result = (
            create_context.convertor_discover_result
        )
        self._publish_discover_result = create_context.publish_discover_result

        self._plugin_data_by_id = {}
        self._current_plugin = None
        self._current_plugin_data = {}
        self._all_instances_by_id = {}
        self._current_context = context

        for plugin in create_context.publish_plugins_mismatch_targets:
            plugin_data = self._add_plugin_data_item(plugin)
            plugin_data["skipped"] = True

    def add_plugin_iter(self, plugin, context):
        """Add report about single iteration of plugin."""
        for instance in context:
            self._all_instances_by_id[instance.id] = instance

        if self._current_plugin_data:
            self._current_plugin_data["passed"] = True

        self._current_plugin = plugin
        self._current_plugin_data = self._add_plugin_data_item(plugin)

    def _add_plugin_data_item(self, plugin):
        if plugin.id in self._plugin_data_by_id:
            # A plugin would be processed more than once. What can cause it:
            #   - there is a bug in controller
            #   - plugin class is imported into multiple files
            #       - this can happen even with base classes from 'pyblish'
            raise ValueError(
                "Plugin '{}' is already stored".format(str(plugin)))

        plugin_data_item = self._create_plugin_data_item(plugin)
        self._plugin_data_by_id[plugin.id] = plugin_data_item

        return plugin_data_item

    def _create_plugin_data_item(self, plugin):
        label = None
        if hasattr(plugin, "label"):
            label = plugin.label

        return {
            "id": plugin.id,
            "name": plugin.__name__,
            "label": label,
            "order": plugin.order,
            "targets": list(plugin.targets),
            "instances_data": [],
            "actions_data": [],
            "skipped": False,
            "passed": False
        }

    def set_plugin_skipped(self):
        """Set that current plugin has been skipped."""
        self._current_plugin_data["skipped"] = True

    def add_result(self, result):
        """Handle result of one plugin and it's instance."""

        instance = result["instance"]
        instance_id = None
        if instance is not None:
            instance_id = instance.id
        self._current_plugin_data["instances_data"].append({
            "id": instance_id,
            "logs": self._extract_instance_log_items(result),
            "process_time": result["duration"]
        })

    def add_action_result(self, action, result):
        """Add result of single action."""
        plugin = result["plugin"]

        store_item = self._plugin_data_by_id.get(plugin.id)
        if store_item is None:
            store_item = self._add_plugin_data_item(plugin)

        action_name = action.__name__
        action_label = action.label or action_name
        log_items = self._extract_log_items(result)
        store_item["actions_data"].append({
            "success": result["success"],
            "name": action_name,
            "label": action_label,
            "logs": log_items
        })

    def get_report(self, publish_plugins=None):
        """Report data with all details of current state."""

        now = arrow.utcnow().to("local")
        instances_details = {}
        for instance in self._all_instances_by_id.values():
            instances_details[instance.id] = self._extract_instance_data(
                instance, instance in self._current_context
            )

        plugins_data_by_id = copy.deepcopy(
            self._plugin_data_by_id
        )

        # Ensure the current plug-in is marked as `passed` in the result
        # so that it shows on reports for paused publishes
        if self._current_plugin is not None:
            current_plugin_data = plugins_data_by_id.get(
                self._current_plugin.id
            )
            if current_plugin_data and not current_plugin_data["passed"]:
                current_plugin_data["passed"] = True

        if publish_plugins:
            for plugin in publish_plugins:
                if plugin.id not in plugins_data_by_id:
                    plugins_data_by_id[plugin.id] = \
                        self._create_plugin_data_item(plugin)

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
            "context": self._extract_context_data(self._current_context),
            "crashed_file_paths": crashed_file_paths,
            "id": uuid.uuid4().hex,
            "created_at": now.isoformat(),
            "report_version": "1.0.1",
        }

    def _extract_context_data(self, context):
        context_label = "Context"
        if context is not None:
            context_label = context.data.get("label")
        return {
            "label": context_label
        }

    def _extract_instance_data(self, instance, exists):
        return {
            "name": instance.data.get("name"),
            "label": get_publish_instance_label(instance),
            "product_type": instance.data.get("productType"),
            "family": instance.data.get("family"),
            "families": instance.data.get("families") or [],
            "exists": exists,
            "creator_identifier": instance.data.get("creator_identifier"),
            "instance_id": instance.data.get("instance_id"),
        }

    def _extract_instance_log_items(self, result):
        instance = result["instance"]
        instance_id = None
        if instance:
            instance_id = instance.id

        log_items = self._extract_log_items(result)
        for item in log_items:
            item["instance_id"] = instance_id
        return log_items

    def _extract_log_items(self, result):
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
            fname, line_no, func, exc = exception.traceback

            # Conversion of exception into string may crash
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
