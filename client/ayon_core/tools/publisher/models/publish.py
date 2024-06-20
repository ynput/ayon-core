import uuid
import copy
import traceback
import collections

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


class PublishPluginsProxy:
    """Wrapper around publish plugin.

    Prepare mapping for publish plugins and actions. Also can create
    serializable data for plugin actions so UI don't have to have access to
    them.

    This object is created in process where publishing is actually running.

    Notes:
        Actions have id but single action can be used on multiple plugins so
            to run an action is needed combination of plugin and action.

    Args:
        plugins [List[pyblish.api.Plugin]]: Discovered plugins that will be
            processed.
    """

    def __init__(self, plugins):
        plugins_by_id = {}
        actions_by_plugin_id = {}
        action_ids_by_plugin_id = {}
        for plugin in plugins:
            plugin_id = plugin.id
            plugins_by_id[plugin_id] = plugin

            action_ids = []
            actions_by_id = {}
            action_ids_by_plugin_id[plugin_id] = action_ids
            actions_by_plugin_id[plugin_id] = actions_by_id

            actions = getattr(plugin, "actions", None) or []
            for action in actions:
                action_id = action.id
                action_ids.append(action_id)
                actions_by_id[action_id] = action

        self._plugins_by_id = plugins_by_id
        self._actions_by_plugin_id = actions_by_plugin_id
        self._action_ids_by_plugin_id = action_ids_by_plugin_id

    def get_action(self, plugin_id, action_id):
        return self._actions_by_plugin_id[plugin_id][action_id]

    def get_plugin(self, plugin_id):
        return self._plugins_by_id[plugin_id]

    def get_plugin_id(self, plugin):
        """Get id of plugin based on plugin object.

        It's used for validation errors report.

        Args:
            plugin (pyblish.api.Plugin): Publish plugin for which id should be
                returned.

        Returns:
            str: Plugin id.
        """

        return plugin.id

    def get_plugin_action_items(self, plugin_id):
        """Get plugin action items for plugin by its id.

        Args:
            plugin_id (str): Publish plugin id.

        Returns:
            List[PublishPluginActionItem]: Items with information about publish
                plugin actions.
        """

        return [
            self._create_action_item(
                self.get_action(plugin_id, action_id), plugin_id
            )
            for action_id in self._action_ids_by_plugin_id[plugin_id]
        ]

    def _create_action_item(self, action, plugin_id):
        label = action.label or action.__name__
        icon = getattr(action, "icon", None)
        return PublishPluginActionItem(
            action.id,
            plugin_id,
            action.active,
            action.on,
            label,
            icon
        )


class PublishPluginActionItem:
    """Representation of publish plugin action.

    Data driven object which is used as proxy for controller and UI.

    Args:
        action_id (str): Action id.
        plugin_id (str): Plugin id.
        active (bool): Action is active.
        on_filter (str): Actions have 'on' attribte which define when can be
            action triggered (e.g. 'all', 'failed', ...).
        label (str): Action's label.
        icon (Union[str, None]) Action's icon.
    """

    def __init__(self, action_id, plugin_id, active, on_filter, label, icon):
        self.action_id = action_id
        self.plugin_id = plugin_id
        self.active = active
        self.on_filter = on_filter
        self.label = label
        self.icon = icon

    def to_data(self):
        """Serialize object to dictionary.

        Returns:
            Dict[str, Union[str,bool,None]]: Serialized object.
        """

        return {
            "action_id": self.action_id,
            "plugin_id": self.plugin_id,
            "active": self.active,
            "on_filter": self.on_filter,
            "label": self.label,
            "icon": self.icon
        }

    @classmethod
    def from_data(cls, data):
        """Create object from data.

        Args:
            data (Dict[str, Union[str,bool,None]]): Data used to recreate
                object.

        Returns:
            PublishPluginActionItem: Object created using data.
        """

        return cls(**data)


class ValidationErrorItem:
    """Data driven validation error item.

    Prepared data container with information about validation error and it's
    source plugin.

    Can be converted to raw data and recreated should be used for controller
    and UI connection.

    Args:
        instance_id (str): Id of pyblish instance to which is validation error
            connected.
        instance_label (str): Prepared instance label.
        plugin_id (str): Id of pyblish Plugin which triggered the validation
            error. Id is generated using 'PublishPluginsProxy'.
    """

    def __init__(
        self,
        instance_id,
        instance_label,
        plugin_id,
        context_validation,
        title,
        description,
        detail
    ):
        self.instance_id = instance_id
        self.instance_label = instance_label
        self.plugin_id = plugin_id
        self.context_validation = context_validation
        self.title = title
        self.description = description
        self.detail = detail

    def to_data(self):
        """Serialize object to dictionary.

        Returns:
            Dict[str, Union[str, bool, None]]: Serialized object data.
        """

        return {
            "instance_id": self.instance_id,
            "instance_label": self.instance_label,
            "plugin_id": self.plugin_id,
            "context_validation": self.context_validation,
            "title": self.title,
            "description": self.description,
            "detail": self.detail,
        }

    @classmethod
    def from_result(cls, plugin_id, error, instance):
        """Create new object based on resukt from controller.

        Returns:
            ValidationErrorItem: New object with filled data.
        """

        instance_label = None
        instance_id = None
        if instance is not None:
            instance_label = (
                instance.data.get("label") or instance.data.get("name")
            )
            instance_id = instance.id

        return cls(
            instance_id,
            instance_label,
            plugin_id,
            instance is None,
            error.title,
            error.description,
            error.detail,
        )

    @classmethod
    def from_data(cls, data):
        return cls(**data)


class PublishValidationErrorsReport:
    """Publish validation errors report that can be parsed to raw data.

    Args:
        error_items (List[ValidationErrorItem]): List of validation errors.
        plugin_action_items (Dict[str, PublishPluginActionItem]): Action items
            by plugin id.
    """

    def __init__(self, error_items, plugin_action_items):
        self._error_items = error_items
        self._plugin_action_items = plugin_action_items

    def __iter__(self):
        for item in self._error_items:
            yield item

    def group_items_by_title(self):
        """Group errors by plugin and their titles.

        Items are grouped by plugin and title -> same title from different
        plugin is different item. Items are ordered by plugin order.

        Returns:
            List[Dict[str, Any]]: List where each item title, instance
                information related to title and possible plugin actions.
        """

        ordered_plugin_ids = []
        error_items_by_plugin_id = collections.defaultdict(list)
        for error_item in self._error_items:
            plugin_id = error_item.plugin_id
            if plugin_id not in ordered_plugin_ids:
                ordered_plugin_ids.append(plugin_id)
            error_items_by_plugin_id[plugin_id].append(error_item)

        grouped_error_items = []
        for plugin_id in ordered_plugin_ids:
            plugin_action_items = self._plugin_action_items[plugin_id]
            error_items = error_items_by_plugin_id[plugin_id]

            titles = []
            error_items_by_title = collections.defaultdict(list)
            for error_item in error_items:
                title = error_item.title
                if title not in titles:
                    titles.append(error_item.title)
                error_items_by_title[title].append(error_item)

            for title in titles:
                grouped_error_items.append({
                    "id": uuid.uuid4().hex,
                    "plugin_id": plugin_id,
                    "plugin_action_items": list(plugin_action_items),
                    "error_items": error_items_by_title[title],
                    "title": title
                })
        return grouped_error_items

    def to_data(self):
        """Serialize object to dictionary.

        Returns:
            Dict[str, Any]: Serialized data.
        """

        error_items = [
            item.to_data()
            for item in self._error_items
        ]

        plugin_action_items = {
            plugin_id: [
                action_item.to_data()
                for action_item in action_items
            ]
            for plugin_id, action_items in self._plugin_action_items.items()
        }

        return {
            "error_items": error_items,
            "plugin_action_items": plugin_action_items
        }

    @classmethod
    def from_data(cls, data):
        """Recreate object from data.

        Args:
            data (dict[str, Any]): Data to recreate object. Can be created
                using 'to_data' method.

        Returns:
            PublishValidationErrorsReport: New object based on data.
        """

        error_items = [
            ValidationErrorItem.from_data(error_item)
            for error_item in data["error_items"]
        ]
        plugin_action_items = [
            PublishPluginActionItem.from_data(action_item)
            for action_item in data["plugin_action_items"]
        ]
        return cls(error_items, plugin_action_items)


class PublishValidationErrors:
    """Object to keep track about validation errors by plugin."""

    def __init__(self):
        self._plugins_proxy = None
        self._error_items = []
        self._plugin_action_items = {}

    def __bool__(self):
        return self.has_errors

    @property
    def has_errors(self):
        """At least one error was added."""

        return bool(self._error_items)

    def reset(self, plugins_proxy):
        """Reset object to default state.

        Args:
            plugins_proxy (PublishPluginsProxy): Proxy which store plugins,
                actions by ids and create mapping of action ids by plugin ids.
        """

        self._plugins_proxy = plugins_proxy
        self._error_items = []
        self._plugin_action_items = {}

    def create_report(self):
        """Create report based on currently existing errors.

        Returns:
            PublishValidationErrorsReport: Validation error report with all
                error information and publish plugin action items.
        """

        return PublishValidationErrorsReport(
            self._error_items, self._plugin_action_items
        )

    def add_error(self, plugin, error, instance):
        """Add error from pyblish result.

        Args:
            plugin (pyblish.api.Plugin): Plugin which triggered error.
            error (ValidationException): Validation error.
            instance (Union[pyblish.api.Instance, None]): Instance on which was
                error raised or None if was raised on context.
        """

        # Make sure the cached report is cleared
        plugin_id = self._plugins_proxy.get_plugin_id(plugin)
        if not error.title:
            if hasattr(plugin, "label") and plugin.label:
                plugin_label = plugin.label
            else:
                plugin_label = plugin.__name__
            error.title = plugin_label

        self._error_items.append(
            ValidationErrorItem.from_result(plugin_id, error, instance)
        )
        if plugin_id in self._plugin_action_items:
            return

        plugin_actions = self._plugins_proxy.get_plugin_action_items(
            plugin_id
        )
        self._plugin_action_items[plugin_id] = plugin_actions
