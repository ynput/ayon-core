from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import auto, Enum
import inspect
import logging
import typing
from typing import Any, Iterable, Generator

import pyblish.api
import pyblish.logic
import pyblish.plugin

from ayon_core.settings import get_project_settings
from ayon_core.pipeline.plugin_discover import DiscoverResult

from .lib import filter_crashed_publish_paths, publish_plugins_discover
from .publish_plugins import (
    PublishError,
    PublishValidationError,
    OptionalPyblishPluginMixin,
)
from .report import (
    PublishReportMaker,
    PublishReport,
)
if typing.TYPE_CHECKING:
    from ayon_core.pipeline.create import CreateContext

    from .typing import PluginType, ActionType

# Define constant for plugin orders offset
PLUGIN_ORDER_OFFSET = 0.5
VALIDATION_ORDER: float = pyblish.api.ValidatorOrder + PLUGIN_ORDER_OFFSET


class MessageHandler(logging.Handler):
    """Helper to collect log records during publishing.

    This is used to collect log records during publishing and store them in
        a list. The list can be cleared and retrieved as needed.

    This is needed to create the log message at the moment of their emit. The
        fill data may change during publishing and stored records might not
        reflect data at the moment of their emit.

    ```python
    data = {"key": 1}
    log.info("Data: %s", data)
    data["key"] = 2
    log.info("Data: %s", data)
    ```
    Without the handle would this code snippet product 2 records:
    - 'Data: {"key": 1}' -> But this should be 'Data: {"key": 2}'
    - 'Data: {"key": 1}'

    """
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


@dataclass
class PublishErrorInfo:
    """Data driven publish error item.

    Prepared data container with information about publish error and it's
    source plugin.

    Can be converted to raw data and recreated should be used for controller
    and UI connection.

    Attributes:
        exception (Exception): The exception that caused the publish error.
        instance_id (str | None): Pyblish instance id to which is
            publish error connected.
        instance_label (str | None): Prepared instance label.
        plugin_id (str): Pyblish plugin id which triggered the publish
            error.
        is_context_plugin (bool): Error happened on context.
        is_validation_error (bool): Error is a validation error.
        title (str | None): Error title.
        description (str | None): Error description.
        detail (str): Error detail.

    """
    exception: Exception
    instance_id: str | None
    instance_label: str | None
    plugin_id: str
    is_context_plugin: bool
    is_validation_error: bool
    title: str | None
    description: str | None
    detail: str | None

    @classmethod
    def from_result(
        cls,
        plugin: PluginType,
        instance: pyblish.api.Instance | None,
        exception: Exception,
    ) -> "PublishErrorInfo":
        """Hold information about publishing error.

        Returns:
            PublishErrorInfo: New object with filled data.

        """
        plugin_id = PublishLogic.get_publish_plugin_id(plugin)
        instance_label = instance_id = title = description = detail = None
        if instance is not None:
            instance_label = (
                instance.data.get("label") or instance.data.get("name")
            )
            instance_id = instance.id

        if isinstance(exception, PublishError):
            title = exception.title
            description = exception.description
            detail = exception.detail

        if not title:
            if hasattr(plugin, "label") and plugin.label:
                plugin_label = plugin.label
            else:
                plugin_label = plugin.__name__
            title = plugin_label

        return cls(
            exception,
            instance_id,
            instance_label,
            plugin_id,
            instance is None,
            isinstance(exception, PublishValidationError),
            title,
            description,
            detail,
        )


def collect_families_from_instances(
    instances: list[pyblish.api.Instance],
    only_active: bool = False,
) -> set[str]:
    """Collect all families for passed publish instances.

    Args:
        instances (list[pyblish.api.Instance]): List of publish instances from
            which are families collected.
        only_active (bool): Return families only for active instances.

    Returns:
        set[str]: Families available on instances.

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

    return all_families


class PublishFailReason(Enum):
    """Reason why publishing failed.

    Attributes:
        No - Publishing did not fail.
        BlockingPaths - Strict validation of crashed publish plugin paths
            during discovery.
        ValidationErrors - Publishing failed because of validation errors.
        Error - An error happened during publishing.

    """
    No = auto()
    Error = auto()
    ValidationErrors = auto()
    BlockingPaths = auto()


@dataclass
class PublishState:
    """Keep state of PublishLogic at one place."""
    # Publishing should stop at validation stage
    stop_after_validation: bool = False
    # 'PublishValidationError' won't stop the publishing until the end of
    #   the validation order if set to 'False'. Other exceptions will stop
    #   the publishing.
    strict_validation_error_handling: bool = True
    comment_is_set: bool = False

    # Publishing started -> can prevent some actions
    started: bool = False
    # Publishing is in progress -> can be used to stop/pause publishing
    is_running: bool = False
    # Publishing is over validation order
    validated: bool = False
    # Finished successfully
    finished: bool = False

    progress: int = 0
    max_progress: int = 0

    fail_reason: PublishFailReason = PublishFailReason.No
    error_info: PublishErrorInfo | None = None
    validation_errors: list[PublishErrorInfo] = field(
        default_factory=list
    )

    def can_continue(self) -> bool:
        """Check if publishing can continue.

        Does not respect 'is_running' value as this should tell if it can be
            continued even though is currently paused.

        Returns:
            bool: Can publishing continue.

        """
        if self.finished:
            return False

        if self.fail_reason == PublishFailReason.No:
            return True

        if self.fail_reason == PublishFailReason.ValidationErrors:
            if self.strict_validation_error_handling or self.validated:
                return False
            return True
        return False

    def should_stop(self) -> bool:
        if not self.can_continue():
            return True

        # Stop if validation is over and validation errors happened
        #   or publishing should stop at validation
        if self.validated and self.stop_after_validation:
            return True
        return False


@dataclass
class PublishIterInfo:
    """Information about next processing function in publishing.

    Holds reference to PublishLogic that defined the next processing function.

    This wrapper is needed for UI purposes as the UI has to have access to
        currently processed plugin and instance, also has to trigger the
        process in between UI updates, but in main thread.

    Attributes 'plugin', 'instance' and 'item_label'.

    Attributes:
        logic (PublishLogic): PublishLogic that defined the next processing
            function.
        plugin (PluginType): Currently processed plugin.
        instance (pyblish.api.Instance | None): Currently processed instance.
        item_label (str): Label of currently processed item. Can be
            plugin or instance label.

    """
    logic: "PublishLogic"
    plugin: PluginType
    instance: pyblish.api.Instance | None
    item_label: str
    executed: bool = False

    def __call__(self) -> None:
        self.executed = True
        self.logic._process_plugin(self.plugin, self.instance)


if typing.TYPE_CHECKING:
    PublishIterGen = Generator[PublishIterInfo | None, None, None]


@dataclass
class PublishActionResult:
    """Result of triggered action.

    Attributes:
        success (bool): Whether action was successful.
        action (ActionType): Triggered action.
        exception (Exception | None): Exception that happened if success is
            'False'.

    """
    success: bool
    action: ActionType
    exception: Exception | None = None


# def _plugin_is_hosts_compatible(
#     plugin: PluginType,
#     hosts: list[str] | set[str],
# ) -> bool:
#     """Determine whether plugin is compatible with the hosts.
#
#     Arguments:
#         plugin (Plugin): Plug-in to assess.
#         hosts (list[str] | set[str]): List or set of hosts to check against.
#
#     """
#     if "*" in plugin.hosts:
#         return True
#
#     return any(host in plugin.hosts for host in hosts)


class _PublishIterator:
    """Iterator for PublishLogic.

    Allows to "pause" iteration and continue later.
    """
    def __init__(self) -> None:
        self._iter: PublishIterGen | None = None

    def __iter__(self):
        return self

    def __next__(self) -> PublishIterInfo:
        if self._iter is None:
            raise StopIteration

        for item in self._iter:
            if item is not None:
                return item
            raise StopIteration
        raise StopIteration

    def update_iter(
        self, publish_iter: PublishIterGen
    ) -> None:
        self._iter = publish_iter


class PublishLogic:
    """Wrapper for publising logic.

    This class is used to manage publishing logic. Can be used to run
        publishing and then create publish report.

    Args:
        reset (bool): Reset publish logic with current context
            on initialization. If False, an explicit reset has to be called
            before publishing.

    """
    def __init__(self, *, reset=True) -> None:
        self._log_handler: MessageHandler = MessageHandler()

        self._log_to_console: bool = True

        self._publish_state: PublishState = PublishState()

        self._publish_plugins: list[PluginType] = []
        self._publish_plugins_by_id: dict[str, PluginType] = {}
        self._publish_plugins_by_name: dict[str, PluginType] = {}

        # pyblish.api.Context
        self._pyblish_context: pyblish.api.Context = pyblish.api.Context()
        # Pyblish report
        self._publish_report: PublishReportMaker = PublishReportMaker()

        # Plugin iterator
        self._publish_iterator: _PublishIterator = _PublishIterator()

        if reset:
            self.reset_with_current_context()

    def reset_with_current_context(self) -> None:
        """Reset publish logic with current context."""
        from ayon_core.pipeline.create import CreateContext
        from ayon_core.pipeline.context_tools import (
            registered_host,
            get_current_project_name,
        )

        host = registered_host()
        create_context = None
        if host is not None:
            create_context = CreateContext(host)

        if create_context is not None:
            self.reset_from_create_context(create_context)
            return

        project_name = get_current_project_name()
        self.reset(project_name)

    def reset(
        self,
        project_name: str,
        context: pyblish.api.Context | None = None,
        plugins: list[PluginType] | None = None,
        targets: list[str] | None = None,
        create_context: CreateContext | None = None,
        publish_discover_result: DiscoverResult | None = None,
        project_settings: dict[str, Any] | None = None,
    ) -> None:
        """Reset publish logic with given parameters.

        Args:
            project_name (str): Name of the project.
            context (pyblish.api.Context | None): Pyblish context to use.
                If None, a new context will be created.
            plugins (list[PluginType] | None): List of publish plugins to use.
                If None, plugins will be discovered.
            targets (list[str] | None): List of publish targets to use.
                If None, all registered targets will be used.
            create_context (CreateContext | None): Create context to use.
                If None, a new create context will be created if possible.
            publish_discover_result (DiscoverResult | None): Discover result
                for publish plugins. If None, plugins will be discovered.

        """
        if plugins is not None and publish_discover_result is None:
            publish_discover_result = DiscoverResult(pyblish.api.Plugin)
            publish_discover_result.plugins = plugins

        self._reset(
            project_name,
            publish_context=context,
            publish_targets=targets,
            create_context=create_context,
            publish_discover_result=publish_discover_result,
            project_settings=project_settings,
        )

    def reset_from_create_context(
        self,
        create_context: CreateContext,
        context: pyblish.api.Context | None = None,
        targets: list[str] | None = None,
    ) -> None:
        """Reset publish logic with given create context.

        Args:
            create_context (CreateContext): Create context to use.
            context (pyblish.api.Context | None): Pyblish context to use.
                If None, a new context will be created.
            targets (list[str] | None): List of publish targets to use.
                If None, all registered targets will be used.

        """
        self._reset(
            create_context.project_name,
            publish_context=context,
            publish_targets=targets,
            publish_discover_result=create_context.publish_discover_result,
            creator_discover_result=create_context.creator_discover_result,
            convertor_discover_result=create_context.convertor_discover_result,
            create_context=create_context,
        )

    @staticmethod
    def get_publish_plugin_id(plugin: PluginType) -> str:
        """Get id of plugin based on plugin object.

        It's used for validation errors report.

        Args:
            plugin (PluginType): Publish plugin for which id should
                be returned.

        Returns:
            str: Plugin id.

        """
        return plugin.id

    def get_pyblish_context(self) -> pyblish.api.Context:
        """Get pyblish context used for publishing."""
        return self._pyblish_context

    pyblish_context: pyblish.api.Context = property(get_pyblish_context)

    def get_publish_plugin_by_id(
        self, plugin_id: str
    ) -> PluginType | None:
        return self._publish_plugins_by_id.get(plugin_id)

    def get_publish_plugin_by_name(
        self, plugin_name: str
    ) -> PluginType | None:
        return self._publish_plugins_by_name.get(plugin_name)

    def set_log_to_console(self, value: bool) -> None:
        """Set whether to log to console."""
        self._log_to_console = value

    def iter_publish_plugins(self) -> Iterable[PluginType]:
        """Iterate over publish plugins.

        Give developers access to publish plugins that are used in current
            publishing process. Can be used to change their attributes, e.g.
            to disable them.

        Returns:
            Iterable[PluginType]: Iterable with publish plugins.

        """
        yield from self._publish_plugins

    def publish(self) -> None:
        for info in self.publish_iter():
            info()

    def publish_iter(self) -> Generator[PublishIterInfo, None, None]:
        """Publish iteration generator.

        Yields:
            PublishIterInfo: Information about next processing function in
                publishing. Can be called to process the next function.

        """
        self._publish_state.is_running = True
        self._publish_state.started = True
        for item in self._publish_iterator:
            yield item

    def get_stop_after_validation(self) -> bool:
        """Check if publishing will stop after validation.

        Returns:
            bool: True if publishing will stop after validation,
                False otherwise.

        """
        return self._publish_state.stop_after_validation

    def set_stop_after_validation(self, value: bool) -> None:
        """Publishing will stop after validation.

        Args:
            value (bool): If True, publishing will stop after validation.

        """
        self._publish_state.stop_after_validation = value

    def set_strict_validation_error_handling(self, value: bool) -> None:
        """Set strict validation error handling.

        Args:
            value (bool): If True, publishing will stop after validation.

        """
        self._publish_state.strict_validation_error_handling = value

    def stop_publish(self) -> None:
        """Mark publishing to stop on next iteration.

        This is useful for UI purposes.
        """
        self._publish_state.is_running = False

    def is_running(self) -> bool:
        """Check if publishing is currently meant to be running.

        It is possible that publishing is currently in process of stopping,
            but this method will return False.

        Returns:
            bool: True if publishing is currently meant to be running,
                False otherwise.

        """
        return self._publish_state.is_running

    def has_started(self) -> bool:
        """Publishing has started."""
        return self._publish_state.started

    def has_finished(self) -> bool:
        """Publishing has successfully finished.

        Returns:
            bool: True if publishing has successfully finished,
                False otherwise.

        """
        return self._publish_state.finished

    def has_validated(self) -> bool:
        """Validation order passed.

        Returns:
            bool: True if validation order passed, False otherwise.

        """
        return self._publish_state.validated

    def publish_can_continue(self) -> bool:
        """Publishing can continue.

        Returns:
            bool: True if publishing still can continue, False otherwise.

        """
        return self._publish_state.can_continue()

    def get_progress(self) -> int:
        """Get current progress of publishing.

        Returns:
            int: Current progress of publishing. Value is between 0 and
                max progress. 0 means no plugin was processed yet.

        """
        return self._publish_state.progress

    def get_max_progress(self) -> int:
        """Get max progress of publishing."""
        return self._publish_state.max_progress

    def has_validation_errors(self) -> bool:
        """Check if publishing has validation errors."""
        return bool(self._publish_state.validation_errors)

    def has_failed(self) -> bool:
        """Check if publishing has failed.

        It is possible that publishing even didn't start, or still can
            continue even if publishing has crashed. Don't use this method
            to check if publishing should be running.

        Returns:
            bool: True if publishing has crashed, False otherwise.

        """
        return self._publish_state.fail_reason != PublishFailReason.No

    def get_fail_reason(self) -> PublishFailReason:
        """Get the reason for publishing failure.

        Returns:
            PublishFailReason: The reason for publishing failure.

        """
        return self._publish_state.fail_reason

    def get_publish_report(self) -> PublishReport:
        """Get report for the current state of publishing."""
        self._publish_report.update_publish_instances(self._pyblish_context)
        return self._publish_report.get_report()

    def get_publish_report_data(self) -> dict[str, Any]:
        """Extract publish report data for the current state of publishing.

        This method should be used if report data are being stored to a file.
            It does mark the current plugin as 'passed' for UI report viewer.

        Returns:
            dict[str, Any]: Publish report data.

        """
        report: PublishReport = self.get_publish_report()
        return report.to_data(self._publish_report.current_plugin_id)

    def store_publish_report(self, filepath: str) -> None:
        """Store publish report to a file."""
        report: PublishReport = self.get_publish_report()
        report.store_to_file(
            filepath,
            self._publish_report.current_plugin_id
        )

    def get_error_info(self) -> PublishErrorInfo | None:
        """Get information about publish error.

        Use to get error if fail reason is 'Error'.

        Returns:
            PublishErrorInfo | None: Information about publish error or None
                if no error happened.

        """
        return self._publish_state.error_info

    def get_validation_errors_info(self) -> list[PublishErrorInfo]:
        """Get information about validation errors.

        Use to get errors if fail reason is 'ValidationErrors'.

        Returns:
            list[PublishErrorInfo]: Validation errors info.

        """
        return self._publish_state.validation_errors

    def iter_all_error_info(self) -> Iterable[PublishErrorInfo]:
        """Iterate over all error information."""
        if self._publish_state.error_info is not None:
            yield self._publish_state.error_info
        yield from self._publish_state.validation_errors

    def set_comment(self, comment: str) -> None:
        # Ignore change of comment when publishing started
        if self._publish_state.started:
            raise ValueError(
                "Cannot change comment when publishing started."
            )
        self._pyblish_context.data["comment"] = comment
        self._publish_state.comment_is_set = True

    @staticmethod
    def get_publish_plugin_actions(
        plugin: PluginType
    ) -> list[ActionType]:
        actions = getattr(plugin, "actions", None)
        if isinstance(actions, list):
            return actions
        return []

    def run_action(
        self,
        plugin: PluginType | str,
        action: ActionType | str,
    ) -> PublishActionResult:
        if isinstance(plugin, str):
            _plugin = self._publish_plugins_by_id.get(plugin)
            if _plugin is None:
                _plugin = self._publish_plugins_by_name[plugin]
            plugin = _plugin

        if isinstance(action, str):
            action_id = action
            action = None
            for plugin_action in self.get_publish_plugin_actions(plugin):
                if plugin_action.id == action_id:
                    action = plugin_action
                    break

            if action is None:
                raise ValueError(
                    f"Action '{action_id}' not found in plugin '{plugin}'"
                )

        result = pyblish.plugin.process(
            plugin, self._pyblish_context, None, action.id
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
            publish_targets = pyblish.logic.registered_targets()

        publish_targets = list(publish_targets)
        if "default" not in publish_targets:
            publish_targets.append("default")

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
                self._publish_report.set_plugin_skipped(
                    self.get_publish_plugin_id(plugin)
                )

        self._pyblish_context = publish_context
        self._publish_plugins = plugins_by_targets
        self._publish_plugins_by_id = {
            self.get_publish_plugin_id(plugin): plugin
            for plugin in plugins_by_targets
        }
        self._publish_plugins_by_name = {
            plugin.__name__: plugin
            for plugin in plugins_by_targets
        }
        strict_validation_error_handling = (
            self._publish_state.strict_validation_error_handling
        )
        self._publish_state = PublishState()
        self._publish_state.strict_validation_error_handling = (
            strict_validation_error_handling
        )
        self._publish_state.max_progress = len(plugins_by_targets)
        if blocking_crashed_paths:
            self._publish_state.fail_reason = PublishFailReason.BlockingPaths

        self._publish_iterator.update_iter(self._inner_publish_iter())

    def _inner_publish_iter(self) -> PublishIterGen:
        """Main logic center of publishing.

        Iterator returns `PublishIterInfo` objects with callbacks that should
        be processed in main thread (threaded in future?). Cares about
        changing states of currently processed publish plugin and instance.
        Also change state of processed orders like validation order
        has passed etc.

        Also stops publishing, if should stop on validation.

        Yields:
            PublishIterInfo: Information about next processing function in
                publishing.
            None: If publishing should stop, yields None to indicate
                that publishing should stop.

        Raises:
            ValueError: If a previous item did not execute and the next one
                was requested.

        """
        for idx, plugin in enumerate(self._publish_plugins):
            if self._publish_state.should_stop():
                self.stop_publish()

            while not self.is_running():
                yield None

            plugin_id = self.get_publish_plugin_id(plugin)
            self._publish_state.progress = idx

            # Check if plugin is over validation order and stop if needed
            if (
                not self._publish_state.validated
                and plugin.order >= VALIDATION_ORDER
            ):
                self._publish_state.validated = True
                if (
                    self._publish_state.stop_after_validation
                    or self.has_validation_errors()
                ):
                    self.stop_publish()
                    yield None

            # Add plugin to publish report
            self._publish_report.add_plugin_iter(
                plugin_id, self._pyblish_context
            )

            # Check if plugin should be skipped because is not enabled
            #   or active.
            if self._should_skip_plugin(plugin):
                self._publish_report.set_plugin_skipped(plugin_id)
                continue

            # Plugin is instance plugin
            if plugin.__instanceEnabled__:
                instances = pyblish.logic.instances_by_plugin(
                    self._pyblish_context, plugin
                )
                if not instances:
                    self._publish_report.set_plugin_skipped(plugin_id)
                    continue

                for instance in instances:
                    while not self.is_running():
                        yield None

                    if instance.data.get("publish") is False:
                        continue

                    item_label = (
                        instance.data.get("label")
                        or instance.data["name"]
                    )
                    info = PublishIterInfo(
                        self,
                        plugin,
                        instance,
                        item_label,
                    )
                    yield info

                    if not info.executed:
                        raise ValueError("Previous item did not execute")

            else:
                families = collect_families_from_instances(
                    self._pyblish_context, only_active=True
                )
                plugins = pyblish.logic.plugins_by_families(
                    [plugin], families
                )
                if not plugins:
                    self._publish_report.set_plugin_skipped(plugin_id)
                    continue

                item_label = (
                    self._pyblish_context.data.get("label")
                    or self._pyblish_context.data.get("name")
                    or "Context"
                )
                item = PublishIterInfo(
                    self,
                    plugin,
                    None,
                    item_label,
                )
                yield item
                if not item.executed:
                    raise ValueError("Previous item did not execute")

            self._publish_report.set_plugin_passed(plugin_id)

        # Cleanup of publishing process
        self._publish_state.finished = True
        self._publish_state.progress = self._publish_state.max_progress

        self.stop_publish()
        while True:
            yield None

    @contextmanager
    def _log_manager(self, plugin: PluginType):
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
        plugin: PluginType,
        instance: pyblish.api.Instance | None
    ) -> None:
        plugin_id = self.get_publish_plugin_id(plugin)
        with self._log_manager(plugin) as log_handler:
            result = pyblish.plugin.process(
                plugin, self._pyblish_context, instance
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
            error_info = PublishErrorInfo.from_result(
                plugin, instance, exception
            )
            is_validation_error = False
            if (
                isinstance(exception, PublishValidationError)
                and not self._publish_state.validated
            ):
                is_validation_error = True
                self._publish_state.validation_errors.append(error_info)
                self._publish_state.fail_reason = (
                    PublishFailReason.ValidationErrors
                )

            else:
                if (
                    isinstance(exception, PublishError)
                    and not exception.title
                ):
                    exception.title = plugin.label or plugin.__name__

                self._publish_state.error_info = error_info
                self._publish_state.fail_reason = PublishFailReason.Error

            # Store additional metadata to result for report maker
            result["is_validation_error"] = is_validation_error

        self._publish_report.add_result(plugin_id, result)

    def _should_skip_plugin(self, plugin: PluginType) -> bool:
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
            plugin (PluginType): Plugin which should be checked
                if it should be skipped.

        Returns:
            bool: Skip the plugin.

        """
        if getattr(plugin, "enabled", True) is False:
            return True

        if plugin.active:
            return False

        # Custom handling of AYON's optional plugins
        if (
            plugin.optional
            and OptionalPyblishPluginMixin in inspect.getmro(plugin)
        ):
            return False
        return True
