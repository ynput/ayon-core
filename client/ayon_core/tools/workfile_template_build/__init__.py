"""Workfile template builder tool.

Backend ('abstract' and 'control') does not require Qt, so it can be used in
a process that does not run the UI. UI objects are imported lazily for the
same reason.
"""

import typing

from .abstract import (
    AbstractTemplateBuilderController,
    ActionResult,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from .control import WorkfileTemplateBuilderController

if typing.TYPE_CHECKING:
    # Lazily imported at runtime, see '__getattr__'
    from .lib import open_template_ui, show_workfile_template_builder
    from .ui import WorkfileTemplateBuilderWindow
    from .window import WorkfileBuildPlaceholderDialog

# Name of module the UI object lives in, by attribute name
_UI_OBJECTS = {
    "WorkfileTemplateBuilderWindow": ".ui",
    "WorkfileBuildPlaceholderDialog": ".window",
    "open_template_ui": ".lib",
    "show_workfile_template_builder": ".lib",
}


def __getattr__(name):
    module_name = _UI_OBJECTS.get(name)
    if module_name is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        )

    from importlib import import_module

    module = import_module(module_name, __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = (
    "AbstractTemplateBuilderController",
    "ActionResult",
    "PlaceholderItemInfo",
    "PlaceholderPluginItem",

    "WorkfileTemplateBuilderController",

    "open_template_ui",
    "show_workfile_template_builder",

    "WorkfileTemplateBuilderWindow",

    "WorkfileBuildPlaceholderDialog",
)
