import uuid
import copy
import inspect
import logging
import traceback
import collections
from contextlib import contextmanager
from functools import partial
from typing import Optional, Dict, List, Union, Any, Iterable

import arrow
import pyblish.plugin

from ayon_core.lib import env_value_to_bool
from ayon_core.pipeline import (
    PublishValidationError,
    KnownPublishError,
    OptionalPyblishPluginMixin,
)
from ayon_core.pipeline.plugin_discover import DiscoverResult
from ayon_core.pipeline.publish import (
    get_publish_instance_label,
    PublishError,
)
from ayon_core.tools.publisher.abstract import AbstractPublisherBackend

PUBLISH_EVENT_SOURCE = "publisher.publish.model"
# Define constant for plugin orders offset
PLUGIN_ORDER_OFFSET = 0.5


class MessageHandler(logging.Handler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._records = []

    def clear_records(self):
        self._records = []

    def emit(self, record):
        try:
            record.msg = record.getMessage()
        except Exception:
            record.msg = str(record.msg)
        self._records.append(record)

    def get_records(self):
        return self._records


class PublishErrorInfo:
    def __init__(
        self,
        message: str,
        is_unknown_error: bool,
        description: Optional[str] = None,
        title: Optional[str] = None,
        detail: Optional[str] = None,
    ):
        self.message: str = message
        self.is_unknown_error = is_unknown_error
        self.description: str = description or message
        self.title: Optional[str] = title or "Unknown error"
        self.detail: Optional[str] = detail

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, PublishErrorInfo):
            return False
        return (
            self.description == other.description
            and self.is_unknown_error == other.is_unknown_error
            and self.title == other.title
            and self.detail == other.detail
        )

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    @classmethod
    def from_exception(cls, exc) -> "PublishErrorInfo":
        if isinstance(exc, PublishError):
            return cls(
                exc.message,
                False,
                exc.description,
                title=exc.title,
                detail=exc.detail,
            )
        if isinstance(exc, KnownPublishError):
            msg = str(exc)
        else:
            msg = (
                "Something went wrong. Send report"
                " to your supervisor or Ynput team."
            )
        return cls(msg, True)


class PublishReportMaker:
    """Report for single publishing process.

    Report keeps current state of publishing and currently processed plugin.
    """

    def __init__(
        self,
        creator_discover_result: Optional[DiscoverResult] = None,
        convertor_discover_result: Optional[DiscoverResult] = None,
        publish_discover_result: Optional[DiscoverResult] = None,
    ):
        self._create_discover_result: Union[DiscoverResult, None] = None
        self._convert_discover_result: Union[DiscoverResult, None] = None
        self._publish_discover_result: Union[DiscoverResult, None] = None

        self._all_instances_by_id: Dict[str, pyblish.api.Instance] = {}
        self._plugin_data_by_id: Dict[str, Any] = {}
        self._current_plugin_id: Optional[str] = None

        self.reset(
            creator_discover_result,
            convertor_discover_result,
            publish_discover_result,
        )

    def reset(
        self,
        creator_discover_result: Union[DiscoverResult, None],
        convertor_discover_result: Union[DiscoverResult, None],
        publish_discover_result: Union[DiscoverResult, None],
    ):
        """Reset report and clear all data."""

        self._create_discover_result = creator_discover_result
        self._convert_discover_result = convertor_discover_result
        self._publish_discover_result = publish_discover_result

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
            "id": uuid.uuid4().hex,
            "created_at": now.isoformat(),
            "report_version": "1.1.0",
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
        # Get docstring
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


class PublishPluginActionItem:
    """Representation of publish plugin action.

    Data driven object which is used as proxy for controller and UI.

    Args:
        action_id (str): Action id.
        plugin_id (str): Plugin id.
        active (bool): Action is active.
        on_filter (Literal["all", "notProcessed", "processed", "failed",
            "warning", "failedOrWarning", "succeeded"]): Actions have 'on'
            attribute which define  when can be action triggered
            (e.g. 'all', 'failed', ...).
        label (str): Action's label.
        icon (Optional[str]) Action's icon.
    """

    def __init__(
        self,
        action_id: str,
        plugin_id: str,
        active: bool,
        on_filter: str,
        label: str,
        icon: Optional[str],
    ):
        self.action_id: str = action_id
        self.plugin_id: str = plugin_id
        self.active: bool = active
        self.on_filter: str = on_filter
        self.label: str = label
        self.icon: Optional[str] = icon

    def to_data(self) -> Dict[str, Any]:
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
    def from_data(cls, data: Dict[str, Any]) -> "PublishPluginActionItem":
        """Create object from data.

        Args:
            data (Dict[str, Union[str,bool,None]]): Data used to recreate
                object.

        Returns:
            PublishPluginActionItem: Object created using data.
        """

        return cls(**data)


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

    def __init__(self, plugins: List[pyblish.api.Plugin]):
        plugins_by_id: Dict[str, pyblish.api.Plugin] = {}
        actions_by_plugin_id: Dict[str, Dict[str, pyblish.api.Action]] = {}
        action_ids_by_plugin_id: Dict[str, List[str]] = {}
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

        self._plugins_by_id: Dict[str, pyblish.api.Plugin] = plugins_by_id
        self._actions_by_plugin_id: Dict[
            str, Dict[str, pyblish.api.Action]
        ] = actions_by_plugin_id
        self._action_ids_by_plugin_id: Dict[str, List[str]] = (
            action_ids_by_plugin_id
        )

    def get_action(
        self, plugin_id: str, action_id: str
    ) -> pyblish.api.Action:
        return self._actions_by_plugin_id[plugin_id][action_id]

    def get_plugin(self, plugin_id: str) -> pyblish.api.Plugin:
        return self._plugins_by_id[plugin_id]

    def get_plugin_id(self, plugin: pyblish.api.Plugin) -> str:
        """Get id of plugin based on plugin object.

        It's used for validation errors report.

        Args:
            plugin (pyblish.api.Plugin): Publish plugin for which id should be
                returned.

        Returns:
            str: Plugin id.
        """

        return plugin.id

    def get_plugin_action_items(
        self, plugin_id: str
    ) -> List[PublishPluginActionItem]:
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

    def _create_action_item(
        self, action: pyblish.api.Action, plugin_id: str
    ) -> PublishPluginActionItem:
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


class PublishErrorItem:
    """Data driven publish error item.

    Prepared data container with information about publish error and it's
    source plugin.

    Can be converted to raw data and recreated should be used for controller
    and UI connection.

    Args:
        instance_id (Optional[str]): Pyblish instance id to which is
            publish error connected.
        instance_label (Optional[str]): Prepared instance label.
        plugin_id (str): Pyblish plugin id which triggered the publish
            error. Id is generated using 'PublishPluginsProxy'.
        is_context_plugin (bool): Error happened on context.
        title (str): Error title.
        description (str): Error description.
        detail (str): Error detail.

    """
    def __init__(
        self,
        instance_id: Optional[str],
        instance_label: Optional[str],
        plugin_id: str,
        is_context_plugin: bool,
        is_validation_error: bool,
        title: str,
        description: str,
        detail: str
    ):
        self.instance_id: Optional[str] = instance_id
        self.instance_label: Optional[str] = instance_label
        self.plugin_id: str = plugin_id
        self.is_context_plugin: bool = is_context_plugin
        self.is_validation_error: bool = is_validation_error
        self.title: str = title
        self.description: str = description
        self.detail: str = detail

    def to_data(self) -> Dict[str, Any]:
        """Serialize object to dictionary.

        Returns:
            Dict[str, Union[str, bool, None]]: Serialized object data.
        """

        return {
            "instance_id": self.instance_id,
            "instance_label": self.instance_label,
            "plugin_id": self.plugin_id,
            "is_context_plugin": self.is_context_plugin,
            "is_validation_error": self.is_validation_error,
            "title": self.title,
            "description": self.description,
            "detail": self.detail,
        }

    @classmethod
    def from_result(
        cls,
        plugin_id: str,
        error: PublishError,
        instance: Union[pyblish.api.Instance, None]
    ):
        """Create new object based on resukt from controller.

        Returns:
            PublishErrorItem: New object with filled data.
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
            isinstance(error, PublishValidationError),
            error.title,
            error.description,
            error.detail,
        )

    @classmethod
    def from_data(cls, data):
        return cls(**data)


class PublishErrorsReport:
    """Publish errors report that can be parsed to raw data.

    Args:
        error_items (List[PublishErrorItem]): List of publish errors.
        plugin_action_items (Dict[str, List[PublishPluginActionItem]]): Action
            items by plugin id.

    """
    def __init__(self, error_items, plugin_action_items):
        self._error_items = error_items
        self._plugin_action_items = plugin_action_items

    def __iter__(self) -> Iterable[PublishErrorItem]:
        for item in self._error_items:
            yield item

    def group_items_by_title(self) -> List[Dict[str, Any]]:
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
    def from_data(
        cls, data: Dict[str, Any]
    ) -> "PublishErrorsReport":
        """Recreate object from data.

        Args:
            data (dict[str, Any]): Data to recreate object. Can be created
                using 'to_data' method.

        Returns:
            PublishErrorsReport: New object based on data.
        """

        error_items = [
            PublishErrorItem.from_data(error_item)
            for error_item in data["error_items"]
        ]
        plugin_action_items = {}
        for action_item in data["plugin_action_items"]:
            item = PublishPluginActionItem.from_data(action_item)
            action_items = plugin_action_items.setdefault(item.plugin_id, [])
            action_items.append(item)

        return cls(error_items, plugin_action_items)


class PublishErrors:
    """Object to keep track about publish errors by plugin."""

    def __init__(self):
        self._plugins_proxy: Union[PublishPluginsProxy, None] = None
        self._error_items: List[PublishErrorItem] = []
        self._plugin_action_items: Dict[
            str, List[PublishPluginActionItem]
        ] = {}

    def __bool__(self):
        return self.has_errors

    @property
    def has_errors(self) -> bool:
        """At least one error was added."""

        return bool(self._error_items)

    def reset(self, plugins_proxy: PublishPluginsProxy):
        """Reset object to default state.

        Args:
            plugins_proxy (PublishPluginsProxy): Proxy which store plugins,
                actions by ids and create mapping of action ids by plugin ids.
        """

        self._plugins_proxy = plugins_proxy
        self._error_items = []
        self._plugin_action_items = {}

    def create_report(self) -> PublishErrorsReport:
        """Create report based on currently existing errors.

        Returns:
            PublishErrorsReport: Publish error report with all
                error information and publish plugin action items.
        """

        return PublishErrorsReport(
            self._error_items, self._plugin_action_items
        )

    def add_error(
        self,
        plugin: pyblish.api.Plugin,
        error: PublishError,
        instance: Union[pyblish.api.Instance, None]
    ):
        """Add error from pyblish result.

        Args:
            plugin (pyblish.api.Plugin): Plugin which triggered error.
            error (PublishError): Publish error.
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
            PublishErrorItem.from_result(plugin_id, error, instance)
        )
        if plugin_id in self._plugin_action_items:
            return

        plugin_actions = self._plugins_proxy.get_plugin_action_items(
            plugin_id
        )
        self._plugin_action_items[plugin_id] = plugin_actions


def collect_families_from_instances(
    instances: List[pyblish.api.Instance],
    only_active: Optional[bool] = False
) -> List[str]:
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

        self._log_to_console: bool = env_value_to_bool(
            "AYON_PUBLISHER_PRINT_LOGS", default=False
        )

        # Publishing should stop at validation stage
        self._publish_up_validation: bool = False
        self._publish_comment_is_set: bool = False

        # Any other exception that happened during publishing
        self._publish_error_info: Optional[PublishErrorInfo] = None
        # Publishing is in progress
        self._publish_is_running: bool = False
        # Publishing is over validation order
        self._publish_has_validated: bool = False

        self._publish_has_validation_errors: bool = False
        self._publish_has_crashed: bool = False
        # All publish plugins are processed
        self._publish_has_started: bool = False
        self._publish_has_finished: bool = False
        self._publish_max_progress: int = 0
        self._publish_progress: int = 0

        self._publish_plugins: List[pyblish.api.Plugin] = []
        self._publish_plugins_proxy: PublishPluginsProxy = (
            PublishPluginsProxy([])
        )

        # pyblish.api.Context
        self._publish_context = None
        # Pyblish report
        self._publish_report: PublishReportMaker = PublishReportMaker()
        # Store exceptions of publish error
        self._publish_errors: PublishErrors = PublishErrors()

        # This information is not much important for controller but for widget
        #   which can change (and set) the comment.
        self._publish_comment_is_set: bool = False

        # Validation order
        # - plugin with order same or higher than this value is extractor or
        #   higher
        self._validation_order: int = (
            pyblish.api.ValidatorOrder + PLUGIN_ORDER_OFFSET
        )

        # Plugin iterator
        self._main_thread_iter: collections.abc.Generator[partial] = (
            self._default_iterator()
        )

        self._log_handler: MessageHandler = MessageHandler()

    def reset(self):
        # Allow to change behavior during process lifetime
        self._log_to_console = env_value_to_bool(
            "AYON_PUBLISHER_PRINT_LOGS", default=False
        )

        create_context = self._controller.get_create_context()

        self._publish_up_validation = False
        self._publish_comment_is_set = False
        self._publish_has_started = False

        self._set_publish_error_info(None)
        self._set_progress(0)
        self._set_is_running(False)
        self._set_has_validated(False)
        self._set_is_crashed(False)
        self._set_has_validation_errors(False)
        self._set_finished(False)

        self._main_thread_iter = self._publish_iterator()
        self._publish_context = pyblish.api.Context()
        # Make sure "comment" is set on publish context
        self._publish_context.data["comment"] = ""
        # Add access to create context during publishing
        # - must not be used for changing CreatedInstances during publishing!
        # QUESTION
        # - pop the key after first collector using it would be safest option?
        self._publish_context.data["create_context"] = create_context
        publish_plugins = create_context.publish_plugins
        self._publish_plugins = publish_plugins
        self._publish_plugins_proxy = PublishPluginsProxy(
            publish_plugins
        )

        self._publish_report.reset(
            create_context.creator_discover_result,
            create_context.convertor_discover_result,
            create_context.publish_discover_result,
        )
        for plugin in create_context.publish_plugins_mismatch_targets:
            self._publish_report.set_plugin_skipped(plugin.id)
        self._publish_errors.reset(self._publish_plugins_proxy)

        self._set_max_progress(len(publish_plugins))

        self._emit_event("publish.reset.finished")

    def set_publish_up_validation(self, value: bool):
        self._publish_up_validation = value

    def start_publish(self, wait: Optional[bool] = True):
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        if self._publish_up_validation and self._publish_has_validated:
            return

        self._start_publish()

        if not wait:
            return

        while self.is_running():
            func = self.get_next_process_func()
            func()

    def get_next_process_func(self) -> partial:
        # Raise error if this function is called when publishing
        #   is not running
        if not self._publish_is_running:
            raise ValueError("Publish is not running")

        # Validations of progress before using iterator
        # Any unexpected error happened
        # - everything should stop
        if self._publish_has_crashed:
            return partial(self.stop_publish)

        # Stop if validation is over and validation errors happened
        #   or publishing should stop at validation
        if (
            self._publish_has_validated
            and (
                self._publish_has_validation_errors
                or self._publish_up_validation
            )
        ):
            return partial(self.stop_publish)

        # Everything is ok so try to get new processing item
        return next(self._main_thread_iter)

    def stop_publish(self):
        if self._publish_is_running:
            self._stop_publish()

    def is_running(self) -> bool:
        return self._publish_is_running

    def is_crashed(self) -> bool:
        return self._publish_has_crashed

    def has_started(self) -> bool:
        return self._publish_has_started

    def has_finished(self) -> bool:
        return self._publish_has_finished

    def has_validated(self) -> bool:
        return self._publish_has_validated

    def has_validation_errors(self) -> bool:
        return self._publish_has_validation_errors

    def publish_can_continue(self) -> bool:
        return (
            not self._publish_has_crashed
            and not self._publish_has_validation_errors
            and not self._publish_has_finished
        )

    def get_progress(self) -> int:
        return self._publish_progress

    def get_max_progress(self) -> int:
        return self._publish_max_progress

    def get_publish_report(self) -> Dict[str, Any]:
        return self._publish_report.get_report(
            self._publish_context
        )

    def get_publish_errors_report(self) -> PublishErrorsReport:
        return self._publish_errors.create_report()

    def get_error_info(self) -> Optional[PublishErrorInfo]:
        return self._publish_error_info

    def set_comment(self, comment: str):
        # Ignore change of comment when publishing started
        if self._publish_has_started:
            return
        self._publish_context.data["comment"] = comment
        self._publish_comment_is_set = True

    def run_action(self, plugin_id: str, action_id: str):
        # TODO handle result in UI
        plugin = self._publish_plugins_proxy.get_plugin(plugin_id)
        action = self._publish_plugins_proxy.get_action(plugin_id, action_id)

        result = pyblish.plugin.process(
            plugin, self._publish_context, None, action.id
        )
        exception = result.get("error")
        if exception:
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

        self._publish_report.add_action_result(action, result)

        self._controller.emit_card_message("Action finished.")

    def _emit_event(self, topic: str, data: Optional[Dict[str, Any]] = None):
        self._controller.emit_event(topic, data, PUBLISH_EVENT_SOURCE)

    def _set_finished(self, value: bool):
        if self._publish_has_finished != value:
            self._publish_has_finished = value
            self._emit_event(
                "publish.finished.changed",
                {"value": value}
            )

    def _set_is_running(self, value: bool):
        if self._publish_is_running != value:
            self._publish_is_running = value
            self._emit_event(
                "publish.is_running.changed",
                {"value": value}
            )

    def _set_has_validated(self, value: bool):
        if self._publish_has_validated != value:
            self._publish_has_validated = value
            self._emit_event(
                "publish.has_validated.changed",
                {"value": value}
            )

    def _set_is_crashed(self, value: bool):
        if self._publish_has_crashed != value:
            self._publish_has_crashed = value
            self._emit_event(
                "publish.has_crashed.changed",
                {"value": value}
            )

    def _set_has_validation_errors(self, value: bool):
        if self._publish_has_validation_errors != value:
            self._publish_has_validation_errors = value
            self._emit_event(
                "publish.has_validation_errors.changed",
                {"value": value}
            )

    def _set_max_progress(self, value: int):
        if self._publish_max_progress != value:
            self._publish_max_progress = value
            self._emit_event(
                "publish.max_progress.changed",
                {"value": value}
            )

    def _set_progress(self, value: int):
        if self._publish_progress != value:
            self._publish_progress = value
            self._emit_event(
                "publish.progress.changed",
                {"value": value}
            )

    def _set_publish_error_info(self, value: Optional[PublishErrorInfo]):
        if self._publish_error_info != value:
            self._publish_error_info = value
            self._emit_event(
                "publish.publish_error.changed",
                {"value": value}
            )

    def _default_iterator(self):
        """Iterator used on initialization.

        Should be replaced by real iterator when 'reset' is called.

        Returns:
            collections.abc.Generator[partial]: Generator with partial
                functions that should be called in main thread.

        """
        while True:
            yield partial(self.stop_publish)

    def _start_publish(self):
        """Start or continue in publishing."""
        if self._publish_is_running:
            return

        self._set_is_running(True)
        self._publish_has_started = True

        self._emit_event("publish.process.started")

    def _stop_publish(self):
        """Stop or pause publishing."""
        self._set_is_running(False)

        self._emit_event("publish.process.stopped")

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

    @contextmanager
    def _log_manager(self, plugin: pyblish.api.Plugin):
        root = logging.getLogger()
        if not self._log_to_console:
            plugin.log.propagate = False
            plugin.log.addHandler(self._log_handler)
            root.addHandler(self._log_handler)

        try:
            if self._log_to_console:
                yield None
            else:
                yield self._log_handler

        finally:
            if not self._log_to_console:
                plugin.log.propagate = True
                plugin.log.removeHandler(self._log_handler)
                root.removeHandler(self._log_handler)
            self._log_handler.clear_records()

    def _process_and_continue(
        self,
        plugin: pyblish.api.Plugin,
        instance: pyblish.api.Instance
    ):
        with self._log_manager(plugin) as log_handler:
            result = pyblish.plugin.process(
                plugin, self._publish_context, instance
            )
            if log_handler is not None:
                records = log_handler.get_records()
                exception = result.get("error")
                if exception is not None and records:
                    last_record = records[-1]
                    if (
                        last_record.name == "pyblish.plugin"
                        and last_record.levelno == logging.ERROR
                    ):
                        # Remove last record made by pyblish
                        # - `log.exception(formatted_traceback)`
                        records.pop(-1)
                result["records"] = records

        exception = result.get("error")
        if exception:
            if (
                isinstance(exception, PublishValidationError)
                and not self._publish_has_validated
            ):
                result["is_validation_error"] = True
                self._add_validation_error(result)

            else:
                if isinstance(exception, PublishError):
                    if not exception.title:
                        exception.title = plugin.label or plugin.__name__
                    self._add_publish_error_to_report(result)

                error_info = PublishErrorInfo.from_exception(exception)
                self._set_publish_error_info(error_info)
                self._set_is_crashed(True)

                result["is_validation_error"] = False

        self._publish_report.add_result(plugin.id, result)

    def _add_validation_error(self, result: Dict[str, Any]):
        self._set_has_validation_errors(True)
        self._add_publish_error_to_report(result)

    def _add_publish_error_to_report(self, result: Dict[str, Any]):
        self._publish_errors.add_error(
            result["plugin"],
            result["error"],
            result["instance"]
        )

    def _is_publish_plugin_active(self, plugin: pyblish.api.Plugin) -> bool:
        """Decide if publish plugin is active.

        This is hack because 'active' is mis-used in mixin
        'OptionalPyblishPluginMixin' where 'active' is used for default value
        of optional plugins. Because of that is 'active' state of plugin
        which inherit from 'OptionalPyblishPluginMixin' ignored. That affects
        headless publishing inside host, potentially remote publishing.

        We have to change that to match pyblish base, but we can do that
        only when all hosts use Publisher because the change requires
        change of settings schemas.

        Args:
            plugin (pyblish.Plugin): Plugin which should be checked if is
                active.

        Returns:
            bool: Is plugin active.
        """

        if plugin.active:
            return True

        if not plugin.optional:
            return False

        if OptionalPyblishPluginMixin in inspect.getmro(plugin):
            return True
        return False
