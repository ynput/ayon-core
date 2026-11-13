"""Debugger of publishing in publisher tool.

Debugger can pause publishing before a plugin processes an item (instance
    or context), so a developer can check publish data in between plugins.

Publishing in the tool is processed in small tasks from the main thread,
    debugger only holds the next task and stops the processing. The task is
    processed first when publishing continues.
"""
from __future__ import annotations

import contextlib
import inspect
import io
import traceback
import typing
from typing import Any, Iterable, Optional

import pyblish.api

from ayon_core.pipeline.publish.report import CONTEXT_ID
from ayon_core.tools.publisher.abstract import (
    PublishDebugPluginItem,
    PublishDebugValue,
    PublishDebugDataItem,
    PublishDebugState,
    PublishDebugExecResult,
)

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.publish.logic import PublishIterTask, PublishLogic
    from ayon_core.pipeline.publish.typing import PluginType
    from ayon_core.tools.publisher.abstract import PublishDebugStepType

# Limits to avoid freezing UI with huge or recursive data
MAX_DEPTH = 16
MAX_CHILDREN = 500
MAX_VALUE_LENGTH = 1000

# Values of these types are not expandable
PRIMITIVE_TYPES = (
    str, bytes, bytearray, int, float, complex, bool, type(None)
)
# Values of these types have items as children
CONTAINER_TYPES = (dict, list, tuple, set, frozenset)
# Prefix of attribute name in value path
ATTRIBUTE_PREFIX = "."

# Signatures of values by path in data '{item id: {path: signature}}'
SignaturesType = dict[str, dict[tuple[str, ...], int]]


def _value_to_str(value: Any) -> str:
    try:
        value_str = str(value)
    except Exception:
        value_str = f"<{type(value).__name__} (failed to convert to str)>"
    return value_str


def _iter_children(value: Any) -> Optional[list[tuple[str, Any]]]:
    if isinstance(value, dict):
        return [(_value_to_str(key), item) for key, item in value.items()]

    if isinstance(value, (list, tuple)):
        return [(f"[{idx}]", item) for idx, item in enumerate(value)]

    if isinstance(value, (set, frozenset)):
        items = sorted(value, key=_value_to_str)
        return [(f"[{idx}]", item) for idx, item in enumerate(items)]
    return None


class _AttributeError:
    """Placeholder of attribute value which failed to be received."""
    def __init__(self, exc: Exception):
        self.exc = exc

    def __str__(self) -> str:
        return f"<{type(self.exc).__name__}: {self.exc}>"


def _iter_attributes(value: Any) -> list[tuple[str, Any]]:
    """Attributes of an object, without dunder attributes and methods."""
    output = []
    try:
        names = dir(value)
    except Exception:
        return output

    for name in sorted(names):
        if name.startswith("__") and name.endswith("__"):
            continue
        try:
            attr_value = getattr(value, name)
        except Exception as exc:
            attr_value = _AttributeError(exc)

        if inspect.isroutine(attr_value):
            continue
        output.append((name, attr_value))
    return output


def _resolve_path(data: Any, path: tuple[str, ...]) -> Any:
    """Find value by path created from snapshot keys.

    Raises:
        KeyError: Value was not found.

    """
    value = data
    for key in path:
        children = _iter_children(value)
        if children is not None:
            for child_key, child_value in children:
                if child_key == key:
                    value = child_value
                    break
            else:
                raise KeyError(key)
            continue

        if not key.startswith(ATTRIBUTE_PREFIX):
            raise KeyError(key)
        try:
            value = getattr(value, key[len(ATTRIBUTE_PREFIX):])
        except Exception:
            raise KeyError(key)
    return value


class _SnapshotMaker:
    """Convert publish data to 'PublishDebugValue' items.

    Changes are detected using signatures of values. Signature of
        container value is made from signatures of children, so a change
        of a nested value is also visible on all parents.

    """
    def __init__(
        self,
        previous_signatures: Optional[SignaturesType],
        max_depth: int = MAX_DEPTH,
    ):
        self._previous_signatures = previous_signatures
        self._max_depth = max_depth
        self.signatures: SignaturesType = {}

    def make_item_value(self, item_id: str, data: Any) -> PublishDebugValue:
        signatures = {}
        self.signatures[item_id] = signatures
        previous = None
        if self._previous_signatures is not None:
            previous = self._previous_signatures.get(item_id, {})
        node, _ = self._make_node(
            "data", data, (), set(), signatures, previous
        )
        return node

    def make_children(self, value: Any) -> list[PublishDebugValue]:
        """Children of a value loaded on demand, without change tracking.

        Children of containers are their items, children of other objects
            are their attributes.

        """
        is_attribute = False
        children_values = _iter_children(value)
        if children_values is None:
            is_attribute = True
            children_values = _iter_attributes(value)

        output = []
        for idx, (child_key, child_value) in enumerate(children_values):
            if idx == MAX_CHILDREN:
                output.append(PublishDebugValue(
                    "...",
                    "",
                    f"{len(children_values) - idx} more items",
                ))
                break
            if isinstance(child_value, _AttributeError):
                node = PublishDebugValue(
                    child_key,
                    type(child_value.exc).__name__,
                    str(child_value),
                )
            else:
                node, _ = self._make_node(
                    child_key,
                    child_value,
                    (child_key, ),
                    {id(value)},
                    {},
                    None,
                )
            node.is_attribute = is_attribute
            output.append(node)
        return output

    def _make_node(
        self,
        key: str,
        value: Any,
        path: tuple[str, ...],
        visited: set[int],
        signatures: dict[tuple[str, ...], int],
        previous: Optional[dict[tuple[str, ...], int]],
    ) -> tuple[PublishDebugValue, int]:
        type_name = type(value).__name__
        children_values = None
        value_id = id(value)
        if len(path) < self._max_depth and value_id not in visited:
            children_values = _iter_children(value)

        children = None
        length = None
        if children_values is None:
            if isinstance(value, CONTAINER_TYPES):
                length = len(value)
            value_str = _value_to_str(value)
            signature = hash((type_name, value_str))
            if len(value_str) > MAX_VALUE_LENGTH:
                value_str = value_str[:MAX_VALUE_LENGTH] + "..."

        else:
            visited.add(value_id)
            children = []
            child_signatures = []
            for idx, (child_key, child_value) in enumerate(children_values):
                if idx == MAX_CHILDREN:
                    children.append(PublishDebugValue(
                        "...",
                        "",
                        f"{len(children_values) - idx} more items",
                    ))
                    break
                child, child_signature = self._make_node(
                    child_key,
                    child_value,
                    path + (child_key, ),
                    visited,
                    signatures,
                    previous,
                )
                children.append(child)
                child_signatures.append((child_key, child_signature))
            visited.discard(value_id)

            length = len(children_values)
            value_str = f"{length} items"
            signature = hash((type_name, tuple(child_signatures)))

        signatures[path] = signature
        status = ""
        if previous is not None:
            previous_signature = previous.get(path)
            if previous_signature is None:
                status = "new"
            elif previous_signature != signature:
                status = "changed"

        node = PublishDebugValue(
            key=key,
            type_name=type_name,
            value=value_str,
            children=children,
            status=status,
            length=length,
            is_mapping=isinstance(value, dict),
            is_expandable=(
                children is None and not isinstance(value, PRIMITIVE_TYPES)
            ),
        )
        return node, signature


def _get_instance_label(instance: pyblish.api.Instance) -> str:
    return (
        instance.data.get("label")
        or instance.data.get("name")
        or instance.name
    )


class PublishDebugger:
    """Debugger state of publishing.

    Breakpoints are stored by plugin class name, because plugin ids change
        on each reset.

    """
    def __init__(self) -> None:
        self._breakpoints: set[str] = set()

        self._step_type: Optional[PublishDebugStepType] = None
        self._executed_since_resume: int = 0
        self._last_executed_plugin: Optional[PluginType] = None

        self._pending_task: Optional[PublishIterTask] = None
        self._pause_reason: Optional[str] = None

        # Counter of processed tasks used to detect if snapshot of data
        #   should be compared with new state
        self._processed_counter: int = 0
        self._snapshot_counter: Optional[int] = None
        self._previous_signatures: Optional[SignaturesType] = None
        self._last_signatures: Optional[SignaturesType] = None

        self._namespace: dict[str, Any] = {}

    def reset(self) -> None:
        """Reset state of publishing. Breakpoints are kept."""
        self._step_type = None
        self._executed_since_resume = 0
        self._last_executed_plugin = None
        self._pending_task = None
        self._pause_reason = None
        self._processed_counter = 0
        self._snapshot_counter = None
        self._previous_signatures = None
        self._last_signatures = None
        self._namespace = {}

    def is_paused(self) -> bool:
        return self._pending_task is not None

    def get_breakpoints(self) -> set[str]:
        return set(self._breakpoints)

    def set_breakpoints(
        self, plugin_names: Iterable[str], enabled: bool
    ) -> None:
        if enabled:
            self._breakpoints |= set(plugin_names)
        else:
            self._breakpoints -= set(plugin_names)

    def clear_breakpoints(self) -> None:
        self._breakpoints.clear()

    def resume(self, step_type: Optional[PublishDebugStepType]) -> None:
        """Publishing is started or continues.

        Args:
            step_type (Optional[PublishDebugStepType]): How far should
                publishing go before pause. 'None' is used when publishing
                is not started by debugger, which works same as 'continue'.

        """
        if step_type == "continue":
            step_type = None
        self._step_type = step_type
        self._executed_since_resume = 0
        self._pause_reason = None

    def pop_pending_task(self) -> Optional[PublishIterTask]:
        """Task that was held when publishing was paused."""
        task, self._pending_task = self._pending_task, None
        return task

    def should_pause(self, task: PublishIterTask) -> bool:
        """Should publishing pause before processing the task.

        Returns:
            bool: Publishing should be paused.

        """
        if task.plugin.__name__ in self._breakpoints:
            self._pause_reason = "breakpoint"
            return True

        if self._executed_since_resume == 0:
            return False

        if self._step_type == "item" or (
            self._step_type == "plugin"
            and task.plugin is not self._last_executed_plugin
        ):
            self._pause_reason = "step"
            return True
        return False

    def pause(self, task: PublishIterTask) -> None:
        self._pending_task = task

    def task_processed(self, task: PublishIterTask) -> None:
        self._executed_since_resume += 1
        self._processed_counter += 1
        self._last_executed_plugin = task.plugin

    def get_state(self) -> PublishDebugState:
        task = self._pending_task
        if task is None:
            return PublishDebugState()

        instance_id = None
        if task.instance is not None:
            instance_id = task.instance.id
        return PublishDebugState(
            is_paused=True,
            pause_reason=self._pause_reason,
            plugin_name=task.plugin.__name__,
            plugin_label=task.plugin.label or task.plugin.__name__,
            instance_id=instance_id,
            item_label=task.item_label,
        )

    def get_plugin_items(
        self, logic: PublishLogic
    ) -> list[PublishDebugPluginItem]:
        pending_plugin = None
        if self._pending_task is not None:
            pending_plugin = self._pending_task.plugin

        progress = logic.get_progress()
        if logic.has_finished():
            progress = logic.get_max_progress()

        output = []
        for idx, plugin in enumerate(logic.iter_publish_plugins()):
            try:
                filepath = inspect.getsourcefile(plugin)
            except Exception:
                filepath = None
            is_pending = plugin is pending_plugin
            output.append(PublishDebugPluginItem(
                name=plugin.__name__,
                label=plugin.label or plugin.__name__,
                order=plugin.order,
                is_instance_plugin=bool(plugin.__instanceEnabled__),
                filepath=filepath,
                processed=idx < progress,
                is_pending=is_pending,
            ))
        return output

    def get_data_items(
        self, context: pyblish.api.Context
    ) -> list[PublishDebugDataItem]:
        """Create snapshot of context and instances data.

        Snapshot is compared to the last snapshot that was made before
            any plugin was processed in between. That means that a new
            snapshot made without processing (e.g. after code execution)
            is compared to the same previous snapshot.

        """
        if self._snapshot_counter != self._processed_counter:
            self._snapshot_counter = self._processed_counter
            self._previous_signatures = self._last_signatures

        previous_signatures = self._previous_signatures
        maker = _SnapshotMaker(previous_signatures)

        pending_instance_id = None
        is_context_pending = False
        if self._pending_task is not None:
            if self._pending_task.instance is None:
                is_context_pending = True
            else:
                pending_instance_id = self._pending_task.instance.id

        context_label = (
            context.data.get("label")
            or context.data.get("name")
            or "Context"
        )
        items = [
            PublishDebugDataItem(
                id=CONTEXT_ID,
                label=context_label,
                is_context=True,
                is_active=True,
                is_pending=is_context_pending,
                status="",
                data=maker.make_item_value(CONTEXT_ID, context.data),
            )
        ]
        for instance in context:
            items.append(PublishDebugDataItem(
                id=instance.id,
                label=_get_instance_label(instance),
                is_context=False,
                is_active=instance.data.get("publish") is not False,
                is_pending=instance.id == pending_instance_id,
                status="",
                data=maker.make_item_value(instance.id, instance.data),
            ))

        for item in items:
            item.status = item.data.status

        self._last_signatures = maker.signatures
        return items

    def get_value_children(
        self,
        context: pyblish.api.Context,
        item_id: str,
        path: tuple[str, ...],
    ) -> Optional[list[PublishDebugValue]]:
        if item_id == CONTEXT_ID:
            data = context.data
        else:
            instance = next(
                (inst for inst in context if inst.id == item_id), None
            )
            if instance is None:
                return None
            data = instance.data

        try:
            value = _resolve_path(data, tuple(path))
        except KeyError:
            return None
        # Load only one level, deeper values are also loaded on demand
        return _SnapshotMaker(None, max_depth=1).make_children(value)

    def execute(
        self,
        code: str,
        context: pyblish.api.Context,
        instance_id: Optional[str],
    ) -> PublishDebugExecResult:
        pending_plugin = None
        instance = None
        if self._pending_task is not None:
            pending_plugin = self._pending_task.plugin
            if instance_id is None:
                instance = self._pending_task.instance

        if instance_id is not None:
            instance = next(
                (inst for inst in context if inst.id == instance_id),
                None
            )

        self._namespace.update({
            "context": context,
            "instance": instance,
            "instances": list(context),
            "plugin": pending_plugin,
            "create_context": context.data.get("create_context"),
            "pyblish": pyblish,
        })

        output = io.StringIO()
        success = True
        redirect_stdout = contextlib.redirect_stdout(output)
        redirect_stderr = contextlib.redirect_stderr(output)
        with redirect_stdout, redirect_stderr:
            try:
                try:
                    compiled = compile(code, "<publish-debugger>", "eval")
                    is_expression = True
                except SyntaxError:
                    compiled = compile(code, "<publish-debugger>", "exec")
                    is_expression = False

                if is_expression:
                    result = eval(compiled, self._namespace)
                    if result is not None:
                        print(repr(result))
                else:
                    exec(compiled, self._namespace)

            except BaseException:
                success = False
                traceback.print_exc()

        return PublishDebugExecResult(success, output.getvalue())
