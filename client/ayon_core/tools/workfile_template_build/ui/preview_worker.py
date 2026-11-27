"""Background worker for placeholder preview and completions."""
from __future__ import annotations

import traceback
from typing import Any

from qtpy import QtCore

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)

from ..abstract import PlaceholderDynamicData
from ..control import WorkfileTemplateBuilderController


class PreviewWorkerSignals(QtCore.QObject):
    """Signals emitted from the worker thread."""

    finished = QtCore.Signal(int, object)


class PreviewWorker(QtCore.QRunnable):
    """Collect preview and completions without blocking the GUI thread."""

    def __init__(
        self,
        controller: WorkfileTemplateBuilderController,
        plugin_identifier: str,
        values: dict[str, Any],
        generation: int,
    ):
        super().__init__()
        self.signals = PreviewWorkerSignals()
        self._controller = controller
        self._plugin_identifier = plugin_identifier
        self._values = values
        self._generation = generation
        self.setAutoDelete(True)

    def run(self) -> None:
        try:
            data = self._controller.get_placeholder_dynamic_data(
                self._plugin_identifier, self._values
            )
        except Exception:
            data = PlaceholderDynamicData(
                preview=PlaceholderPreview(
                    title="Preview failed",
                    hint=traceback.format_exc(limit=0).strip(),
                    is_error=True,
                )
            )
        try:
            self.signals.finished.emit(self._generation, data)
        except RuntimeError:
            # The editor was deleted while the query was running.
            pass


def create_preview_worker(
    controller: WorkfileTemplateBuilderController,
    plugin_identifier: str,
    values: dict[str, Any],
    generation: int,
) -> PreviewWorker:
    """Create a preview worker."""
    return PreviewWorker(controller, plugin_identifier, values, generation)
