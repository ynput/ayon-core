from __future__ import annotations

import collections
from contextlib import contextmanager
from dataclasses import dataclass
from enum import auto, Enum
import inspect
import logging
import typing
from typing import Any, Iterable, Generator
import uuid

import pyblish.api
import pyblish.logic
import pyblish.plugin

from ayon_core.lib import env_value_to_bool
from ayon_core.settings import get_project_settings
from ayon_core.pipeline.plugin_discover import DiscoverResult

from .lib import filter_crashed_publish_paths, publish_plugins_discover
from .publish_plugins import (
    PublishError,
    PublishValidationError,
    KnownPublishError,
    OptionalPyblishPluginMixin,
)
from .report import (
    PublishReportMaker,
    PublishReport,
)
if typing.TYPE_CHECKING:
    from ayon_core.pipeline.create import CreateContext

# Define constant for plugin orders offset
PLUGIN_ORDER_OFFSET = 0.5
VALIDATION_ORDER: int = pyblish.api.ValidatorOrder + PLUGIN_ORDER_OFFSET


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
        description: str | None = None,
        title: str | None = None,
        detail: str | None = None,
    ):
        self.message: str = message
        self.is_unknown_error = is_unknown_error
        self.description: str = description or message
        self.title: str = title or "Unknown error"
        self.detail: str | None = detail

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
        icon (str | None) Action's icon.
    """

    def __init__(
        self,
        action_id: str,
        plugin_id: str,
        active: bool,
        on_filter: str,
        label: str,
        icon: str | None,
    ):
        self.action_id: str = action_id
        self.plugin_id: str = plugin_id
        self.active: bool = active
        self.on_filter: str = on_filter
        self.label: str = label
        self.icon: str | None = icon

    def to_data(self) -> dict[str, str | bool | None]:
        """Serialize object to dictionary.

        Returns:
            dict[str, str | bool | None]: Serialized object.

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
    def from_data(
        cls, data: dict[str, str | bool | None]
    ) -> "PublishPluginActionItem":
        """Create object from data.

        Args:
            data (dict[str, str | bool | None]): Data used to recreate
                object.

        Returns:
            PublishPluginActionItem: Object created using data.
        """

        return cls(**data)


class PublishPluginsProxy:
    """Wrapper around publish plugin.

    Prepare mapping for publish plugins and actions. Also can create
    serializable data for plugin actions for UI purposes.

    This object is created in process where publishing is actually running.

    Notes:
        Actions have id but single action can be used on multiple plugins so
            to run an action is needed combination of plugin and action.

    Args:
        plugins [list[pyblish.api.Plugin]]: Discovered plugins that will be
            processed.
    """

    def __init__(self, plugins: list[pyblish.api.Plugin]):
        plugins_by_id: dict[str, pyblish.api.Plugin] = {}
        actions_by_plugin_id: dict[str, dict[str, pyblish.api.Action]] = {}
        action_ids_by_plugin_id: dict[str, list[str]] = {}
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

        self._plugins_by_id: dict[str, pyblish.api.Plugin] = plugins_by_id
        self._actions_by_plugin_id: dict[
            str, dict[str, pyblish.api.Action]
        ] = actions_by_plugin_id
        self._action_ids_by_plugin_id: dict[str, list[str]] = (
            action_ids_by_plugin_id
        )

    def get_action(
        self, plugin_id: str, action_id: str
    ) -> pyblish.api.Action:
        return self._actions_by_plugin_id[plugin_id][action_id]

    def get_plugin(self, plugin_id: str) -> pyblish.api.Plugin:
        return self._plugins_by_id[plugin_id]

    @staticmethod
    def get_plugin_id(plugin: pyblish.api.Plugin) -> str:
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
    ) -> list[PublishPluginActionItem]:
        """Get plugin action items for plugin by its id.

        Args:
            plugin_id (str): Publish plugin id.

        Returns:
            list[PublishPluginActionItem]: Items with information about publish
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
        instance_id (str | None): Pyblish instance id to which is
            publish error connected.
        instance_label (str | None): Prepared instance label.
        plugin_id (str): Pyblish plugin id which triggered the publish
            error. Id is generated using 'PublishPluginsProxy'.
        is_context_plugin (bool): Error happened on context.
        title (str): Error title.
        description (str): Error description.
        detail (str): Error detail.

    """
    def __init__(
        self,
        instance_id: str | None,
        instance_label: str | None,
        plugin_id: str,
        is_context_plugin: bool,
        is_validation_error: bool,
        title: str | None,
        description: str | None,
        detail: str
    ):
        self.instance_id: str | None = instance_id
        self.instance_label: str | None = instance_label
        self.plugin_id: str = plugin_id
        self.is_context_plugin: bool = is_context_plugin
        self.is_validation_error: bool = is_validation_error
        self.title: str | None = title
        self.description: str | None = description
        self.detail: str = detail

    @classmethod
    def from_result(
        cls,
        plugin_id: str,
        error: PublishError,
        instance: pyblish.api.Instance | None
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

    def to_data(self) -> dict[str, str | bool | None]:
        """Serialize object to dictionary.

        Returns:
            dict[str, str | bool | None]: Serialized object data.

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
    def from_data(cls, data):
        return cls(**data)


class PublishErrorsReport:
    """Publish errors report that can be parsed to raw data.

    Args:
        error_items (list[PublishErrorItem]): List of publish errors.
        plugin_action_items (dict[str, list[PublishPluginActionItem]]): Action
            items by plugin id.

    """
    def __init__(
        self,
        error_items: list[PublishErrorItem],
        plugin_action_items: dict[str, list[PublishPluginActionItem]],
    ):
        self._error_items = error_items
        self._plugin_action_items = plugin_action_items

    def __iter__(self) -> Iterable[PublishErrorItem]:
        for item in self._error_items:
            yield item

    def group_items_by_title(self) -> list[dict[str, Any]]:
        """Group errors by plugin and their titles.

        Items are grouped by plugin and title -> same title from different
        plugin is different item. Items are ordered by plugin order.

        Returns:
            list[dict[str, Any]]: List where each item title, instance
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
            dict[str, Any]: Serialized data.
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
        cls, data: dict[str, Any]
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
        self._plugins_proxy: PublishPluginsProxy | None = None
        self._error_items: list[PublishErrorItem] = []
        self._plugin_action_items: dict[
            str, list[PublishPluginActionItem]
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
        instance: pyblish.api.Instance | None
    ):
        """Add error from pyblish result.

        Args:
            plugin (pyblish.api.Plugin): Plugin which triggered error.
            error (PublishError): Publish error.
            instance (pyblish.api.Instance | None): Instance on which was
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


@dataclass
class PublishState:
    # Publishing should stop at validation stage
    up_validation: bool = False
    comment_is_set: bool = False

    # Publishing is in progress
    is_running: bool = False
    # Publishing is over validation order
    validated: bool = False
    has_validation_errors: bool = False
    crashed: bool = False
    started: bool = False
    finished: bool = False
    max_progress: int = 0
    progress: int = 0

    # Any other exception that happened during publishing
    error_info: PublishErrorInfo | None = None

    def can_continue(self) -> bool:
        """Check if publishing can continue.

        Returns:
            bool: Can publishing continue.

        """
        return (
            not self.crashed
            and not self.has_validation_errors
            and not self.finished
        )

    def should_stop(self) -> bool:
        if self.crashed:
            return True

        # Stop if validation is over and validation errors happened
        #   or publishing should stop at validation
        if (
            self.validated
            and (self.has_validation_errors or self.up_validation)
        ):
            return True
        return False


class PublishIterAction(Enum):
    Stop = auto()
    Continue = auto()


@dataclass
class PublishIterInfo:
    logic: "PublishLogic"
    action: PublishIterAction
    plugin: pyblish.api.Plugin | None = None
    instance: pyblish.api.Instance | None = None
    item_label: str | None = None

    def __call__(self):
        if self.action == PublishIterAction.Stop:
            self.logic.stop_publish()
            return

        if self.plugin is None:
            raise ValueError("Plugin is None but action is Continue")

        self.logic._process_plugin(self.plugin, self.instance)


@dataclass
class PublishActionResult:
    success: bool
    action: pyblish.api.Action
    exception: Exception | None = None


def _plugin_is_hosts_compatible(
    plugin: pyblish.api.Plugin,
    hosts: list[str] | set[str],
) -> bool:
    """Determine whether plugin is compatible with the hosts.

    Arguments:
        plugin (Plugin): Plug-in to assess.
        hosts (list[str] | set[str]): List or set of hosts to check against.

    """
    if "*" in plugin.hosts:
        return True

    return any(host in plugin.hosts for host in hosts)


class PublishLogic:
    def __init__(self) -> None:
        self._log_handler: MessageHandler = MessageHandler()

        self._log_to_console: bool = env_value_to_bool(
            "AYON_PUBLISHER_PRINT_LOGS", default=False
        )

        self._publish_state = PublishState()

        self._publish_plugins: list[pyblish.api.Plugin] = []
        self._publish_plugins_proxy: PublishPluginsProxy = (
            PublishPluginsProxy([])
        )

        # pyblish.api.Context
        self._publish_context: pyblish.api.Context = pyblish.api.Context()
        # Pyblish report
        self._publish_report: PublishReportMaker = PublishReportMaker()
        # Store exceptions of publish error
        self._publish_errors: PublishErrors = PublishErrors()

        # Plugin iterator
        self._main_thread_iter: Generator[PublishIterInfo] = (
            self._default_iterator()
        )

    def reset(
        self,
        project_name: str,
        context: pyblish.api.Context | None = None,
        plugins: list[pyblish.api.Plugin] | None = None,
        targets: list[str] | None = None,
        publish_discover_result: DiscoverResult | None = None,
        project_settings: dict[str, Any] | None = None,
    ) -> None:
        if plugins is not None and publish_discover_result is None:
            publish_discover_result = DiscoverResult(pyblish.api.Plugin)
            publish_discover_result.plugins = plugins

        self._reset(
            project_name,
            publish_context=context,
            publish_targets=targets,
            publish_discover_result=publish_discover_result,
            project_settings=project_settings,
        )

    def reset_from_create_context(
        self,
        create_context: CreateContext,
        context: pyblish.api.Context | None = None,
        targets: list[str] | None = None,
    ):
        self._reset(
            create_context.project_name,
            publish_context=context,
            publish_targets=targets,
            publish_discover_result=create_context.publish_discover_result,
            creator_discover_result=create_context.creator_discover_result,
            convertor_discover_result=create_context.convertor_discover_result,
            create_context=create_context,
        )

    def publish_up_validation(self) -> bool:
        return self._publish_state.up_validation

    def set_publish_up_validation(self, value: bool):
        self._publish_state.up_validation = value

    def start_publish(self, wait: bool = True):
        """Run publishing.

        Make sure all changes are saved before method is called (Call
        'save_changes' and check output).
        """
        if self._publish_state.is_running:
            return

        if self._publish_state.should_stop():
            return

        self._publish_state.is_running = True
        self._publish_state.started = True

        if wait:
            while self.is_running():
                func = self.get_next_process_func()
                func()

    def get_next_process_func(self) -> PublishIterInfo:
        # Raise error if this function is called when publishing
        #   is not running
        if not self._publish_state.is_running:
            raise ValueError("Publish is not running")

        if self._publish_state.should_stop():
            return PublishIterInfo(self, PublishIterAction.Stop)

        # Everything is ok so try to get new processing item
        return next(self._main_thread_iter)

    def stop_publish(self) -> None:
        if self._publish_state.is_running:
            self._publish_state.is_running = False

    def is_running(self) -> bool:
        return self._publish_state.is_running

    def has_crashed(self) -> bool:
        return self._publish_state.crashed

    def has_started(self) -> bool:
        return self._publish_state.started

    def has_finished(self) -> bool:
        return self._publish_state.finished

    def has_validated(self) -> bool:
        return self._publish_state.validated

    def has_validation_errors(self) -> bool:
        return self._publish_state.has_validation_errors

    def publish_can_continue(self) -> bool:
        return self._publish_state.can_continue()

    def get_progress(self) -> int:
        return self._publish_state.progress

    def get_max_progress(self) -> int:
        return self._publish_state.max_progress

    def get_publish_report(self) -> PublishReport:
        self._publish_report.update_publish_instances(self._publish_context)
        return self._publish_report.get_report()

    def get_publish_report_data(self) -> dict[str, Any]:
        report: PublishReport = self.get_publish_report()
        return report.to_data(self._publish_report.current_plugin_id)

    def get_publish_errors_report(self) -> PublishErrorsReport:
        return self._publish_errors.create_report()

    def get_error_info(self) -> PublishErrorInfo | None:
        return self._publish_state.error_info

    def store_publish_report(self, filepath: str) -> None:
        report: PublishReport = self.get_publish_report()
        report.store_to_file(filepath)

    def set_comment(self, comment: str) -> None:
        # Ignore change of comment when publishing started
        if self._publish_state.started:
            return
        self._publish_context.data["comment"] = comment
        self._publish_state.comment_is_set = True

    def run_action(
        self, plugin_id: str, action_id: str
    ) -> PublishActionResult:
        plugin = self._publish_plugins_proxy.get_plugin(plugin_id)
        action = self._publish_plugins_proxy.get_action(plugin_id, action_id)

        result = pyblish.plugin.process(
            plugin, self._publish_context, None, action.id
        )
        self._publish_report.add_action_result(action, result)

        exception = result.get("error")
        if not exception:
            return PublishActionResult(True, action)
        return PublishActionResult(False, action, exception)

    def _reset(
        self,
        project_name: str,
        publish_context: pyblish.api.Context | None = None,
        publish_targets: list[str] | None = None,
        # Hosts filtering is embedded into pyblish register and discover.
        # - hard to change how it works, can be changed only for paths
        #   discovery
        # publish_hosts: list[str] | None = None,
        publish_discover_result: DiscoverResult | None = None,
        creator_discover_result: DiscoverResult | None = None,
        convertor_discover_result: DiscoverResult | None = None,
        create_context: CreateContext | None = None,
        project_settings: dict[str, Any] | None = None,
    ) -> None:
        # Allow to change behavior during process lifetime
        self._log_to_console = env_value_to_bool(
            "AYON_PUBLISHER_PRINT_LOGS", default=False
        )

        self._publish_state = PublishState()

        # Publish context preparation
        if publish_context is None:
            publish_context = pyblish.api.Context()

        if publish_context.data.get("comment") is None:
            publish_context.data["comment"] = ""

        # Plugins preparation
        if create_context is not None:
            publish_context.data["create_context"] = create_context

            # Use discover results from create context
            if publish_discover_result is None:
                publish_discover_result = (
                    create_context.publish_discover_result
                )
            if creator_discover_result is None:
                creator_discover_result = (
                    create_context.creator_discover_result
                )
            if convertor_discover_result is None:
                convertor_discover_result = (
                    create_context.convertor_discover_result
                )

            if project_settings is None:
                project_settings = (
                    create_context.get_current_project_settings()
                )

        if publish_discover_result is None:
            publish_discover_result: DiscoverResult = (
                publish_plugins_discover()
            )

        if creator_discover_result is None:
            creator_discover_result = DiscoverResult(None)

        if convertor_discover_result is None:
            convertor_discover_result = DiscoverResult(None)

        if project_settings is None:
            project_settings = get_project_settings(project_name)

        discovered_publish_plugins = publish_discover_result.plugins
        crashed_file_paths = publish_discover_result.crashed_file_paths

        if publish_targets is None:
            publish_targets = set(pyblish.logic.registered_targets())
            publish_targets.add("default")
            publish_targets = list(publish_targets)

        plugins_by_targets = pyblish.logic.plugins_by_targets(
            discovered_publish_plugins, publish_targets
        )

        blocking_crashed_paths = filter_crashed_publish_paths(
            project_name,
            set(crashed_file_paths),
            project_settings=project_settings,
        )

        self._publish_report.reset_with_discover_results(
            creator_discover_result,
            convertor_discover_result,
            publish_discover_result,
            blocking_crashed_paths,
        )

        for plugin in discovered_publish_plugins:
            if plugin not in plugins_by_targets:
                self._publish_report.set_plugin_skipped(plugin.id)

        self._publish_context = publish_context
        self._publish_plugins = plugins_by_targets
        self._publish_plugins_proxy = PublishPluginsProxy(
            plugins_by_targets
        )
        self._publish_errors.reset(self._publish_plugins_proxy)

        self._publish_state.max_progress = len(plugins_by_targets)

        self._main_thread_iter = self._publish_iterator()

    def _default_iterator(self):
        """Iterator used on initialization.

        Should be replaced by real iterator when 'reset' is called.

        Returns:
            collections.abc.Generator[PublishIterInfo]: Generator with partial
                functions that should be called in main thread.

        """
        while True:
            yield PublishIterInfo(self, PublishIterAction.Stop)

    def _publish_iterator(self) -> Generator[PublishIterInfo, None, None]:
        """Main logic center of publishing.

        Iterator returns `PublishIterInfo` objects with callbacks that should
        be processed in main thread (threaded in future?). Cares about
        changing states of currently processed publish plugin and instance.
        Also change state of processed orders like validation order
        has passed etc.

        Also stops publishing, if should stop on validation.
        """

        for idx, plugin in enumerate(self._publish_plugins):
            self._publish_state.progress = idx

            # Check if plugin is over validation order
            if (
                not self._publish_state.validated
                and plugin.order >= VALIDATION_ORDER
            ):
                self._publish_state.validated = True
                if (
                    self._publish_state.up_validation
                    or self._publish_state.has_validation_errors
                ):
                    yield PublishIterInfo(self, PublishIterAction.Stop)

            # Add plugin to publish report
            self._publish_report.add_plugin_iter(
                plugin.id, self._publish_context
            )

            # Check if plugin should be skipped because is not enabled
            #   or active.
            if self._should_skip_plugin(plugin):
                self._publish_report.set_plugin_skipped(plugin.id)
                continue

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

                    item_label = (
                        instance.data.get("label")
                        or instance.data["name"]
                    )
                    yield PublishIterInfo(
                        self,
                        PublishIterAction.Continue,
                        plugin,
                        instance,
                        item_label,
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

                item_label = (
                    self._publish_context.data.get("label")
                    or self._publish_context.data.get("name")
                    or "Context"
                )
                yield PublishIterInfo(
                    self,
                    PublishIterAction.Continue,
                    plugin,
                    None,
                    item_label,
                )

            self._publish_report.set_plugin_passed(plugin.id)

        # Cleanup of publishing process
        self._publish_state.finished = True
        self._publish_state.progress = self._publish_state.max_progress

        yield PublishIterInfo(self, PublishIterAction.Stop)

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

    def _process_plugin(
        self,
        plugin: pyblish.api.Plugin,
        instance: pyblish.api.Instance
    ) -> None:
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
                and not self._publish_state.validated
            ):
                result["is_validation_error"] = True
                self._add_validation_error(result)

            else:
                if isinstance(exception, PublishError):
                    if not exception.title:
                        exception.title = plugin.label or plugin.__name__
                    self._add_publish_error_to_report(result)

                error_info = PublishErrorInfo.from_exception(exception)
                self._publish_state.error_info = error_info
                self._publish_state.crashed = True

                result["is_validation_error"] = False

        self._publish_report.add_result(plugin.id, result)

    def _add_validation_error(self, result: dict[str, Any]):
        self._publish_state.has_validation_errors = True
        self._add_publish_error_to_report(result)

    def _add_publish_error_to_report(self, result: dict[str, Any]):
        self._publish_errors.add_error(
            result["plugin"],
            result["error"],
            result["instance"]
        )

    def _should_skip_plugin(self, plugin: pyblish.api.Plugin) -> bool:
        """Decide if publish plugin should be skipped.

        The pyblish base does define 'active' on plugin which is used to mark
            plugin as active or not. But if plugin is also 'optional' it is
            possible to change the 'active' value.

        AYON does use 'optional' to mark plugin as optional. But the
            optional logic does not change 'active', instead it is handled by
            'process' logic. So AYON's 'OptionalPyblishPluginMixin' will
            always be 'active'.

        With that AYON plugins have to somehow mark plugin as disabled, that
            is why 'enabled' can be set on plugins. If plugin is disabled
            it is skipped no matter what.

        Args:
            plugin (pyblish.api.Plugin): Plugin which should be checked
                if it should be skipped.

        Returns:
            bool: Skip the plugin.

        """
        if getattr(plugin, "enabled", True) is False:
            return True

        if plugin.active:
            return False

        if not plugin.optional:
            return True

        if OptionalPyblishPluginMixin in inspect.getmro(plugin):
            return False
        return True
