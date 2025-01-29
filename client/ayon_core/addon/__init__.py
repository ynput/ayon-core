"""Addons for AYON."""
from . import click_wrap
from .base import (
    AddonsManager,
    AYONAddon,
    ProcessContext,
    ProcessPreparationError,
    load_addons,
)
from .interfaces import (
    IHostAddon,
    IPluginPaths,
    ITraits,
    ITrayAction,
    ITrayAddon,
    ITrayService,
)
from .utils import (
    ensure_addons_are_process_context_ready,
    ensure_addons_are_process_ready,
)

__all__ = (
    "click_wrap",

    "IPluginPaths",
    "ITrayAddon",
    "ITrayAction",
    "ITrayService",
    "IHostAddon",
    "ITraits",

    "ProcessPreparationError",
    "ProcessContext",
    "AYONAddon",
    "AddonsManager",
    "load_addons",

    "ensure_addons_are_process_context_ready",
    "ensure_addons_are_process_ready",
)
