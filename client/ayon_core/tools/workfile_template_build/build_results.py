"""Build result collection for the template builder controller."""

from __future__ import annotations

import logging
from contextlib import contextmanager

from ayon_core.lib import Logger

from .abstract import BuildStep

# Maximum number of log lines kept from a single build
MAX_BUILD_LOG_LINES = 2000

# Maximum number of builds kept in the history
MAX_BUILD_HISTORY = 5


def _can_run_placeholder(plugin) -> bool:
    """Plugin can re-run a placeholder.

    Prefer the dedicated 'repopulate_placeholder', but fall back to
    'populate_placeholder' for older integrations.
    """
    return (
        plugin.is_method_implemented("repopulate_placeholder")
        or plugin.is_method_implemented("populate_placeholder")
    )


class _BuildLogHandler(logging.Handler):
    """Collect log records emitted during a template build.

    Args:
        lines (list[str]): List the formatted records are appended to.

    """

    def __init__(self, lines: list[str]):
        super().__init__()
        self._lines = lines
        self.setFormatter(logging.Formatter(
            "%(levelname)s [%(name)s]: %(message)s"
        ))

    def emit(self, record):
        # The handler may be attached to both the standard and AYON root
        #   loggers; capture each record only once.
        if getattr(record, "_ayon_build_log_seen", False):
            return
        record._ayon_build_log_seen = True
        try:
            message = self.format(record)
        except Exception:
            return
        self._lines.append(message)


class BuildResultsMixin:
    def get_build_steps(self) -> list[BuildStep]:
        """Steps of the last template build.

        Returns:
            list[BuildStep]: Processed placeholders with status, duration and
                error.

        """
        return [
            BuildStep.from_data(step.to_data()) for step in self._build_steps
        ]

    def get_build_log(self) -> list[str]:
        """Log lines captured during the last template build."""
        return list(self._build_log)

    @contextmanager
    def _capture_build_log(self):
        """Capture log output emitted while a template build runs."""
        self._build_log = []
        handler = _BuildLogHandler(self._build_log)
        # Standard root receives records propagated from the AYON logger
        #   hierarchy; also attach to the AYON root so logger
        #   re-initialization or a non-propagating AYON logger cannot hide
        #   build logs. The handler captures each record only once.
        loggers = [logging.getLogger(), Logger.get_root_logger()]
        for logger in loggers:
            logger.addHandler(handler)
        try:
            yield
        finally:
            for logger in loggers:
                logger.removeHandler(handler)
            self._trim_build_log()

    def _trim_build_log(self) -> None:
        """Keep the head and tail so the build report stays readable."""
        if len(self._build_log) <= MAX_BUILD_LOG_LINES:
            return
        head_count = MAX_BUILD_LOG_LINES // 2
        tail_count = MAX_BUILD_LOG_LINES - head_count
        omitted = len(self._build_log) - MAX_BUILD_LOG_LINES
        self._build_log = (
            self._build_log[:head_count]
            + ["... {} log lines omitted ...".format(omitted)]
            + self._build_log[-tail_count:]
        )

    def get_build_history(self) -> list[list[BuildStep]]:
        """Last build results, oldest first, limited to 5 builds."""
        return [
            [
                BuildStep.from_data(step.to_data())
                for step in build_steps
            ]
            for build_steps in self._build_history
        ]

    def get_last_build_results(self) -> list[tuple[str, str, str]]:
        """Results of the last template build.

        Returns:
            list[tuple[str, str, str]]: Scene identifier, label and error
                message of each placeholder. The error message is empty when
                the placeholder was processed successfully or skipped.

        """
        return [
            (step.scene_identifier, step.label, step.error)
            for step in self._build_steps
        ]

    def _on_placeholder_finished(self, event):
        """Store duration of a finished placeholder from builder event."""
        data = event.data or {}
        scene_identifier = data.get("scene_identifier")
        if scene_identifier is None:
            return
        self._build_durations[scene_identifier] = data.get("duration", 0.0)
        if self._progress_callback is not None:
            try:
                self._progress_callback(
                    len(self._build_durations), data
                )
            except Exception:
                self._log.debug(
                    "Failed to report build progress.", exc_info=True
                )

    def _create_build_step(self, placeholder) -> BuildStep:
        """Create a build step for a processed placeholder."""
        try:
            label = placeholder.plugin.get_placeholder_label(placeholder)
        except Exception:
            label = placeholder.scene_identifier

        plugin = placeholder.plugin
        errors = placeholder.get_errors()
        if not _can_run_placeholder(plugin):
            status = "skipped"
            error = ""
        elif errors:
            status = "failed"
            error = "\n".join(errors)
        else:
            status = "succeeded"
            error = ""

        return BuildStep(
            scene_identifier=placeholder.scene_identifier,
            label=label or placeholder.scene_identifier,
            order=placeholder.order,
            status=status,
            duration=self._build_durations.get(
                placeholder.scene_identifier, 0.0
            ),
            error=error,
        )

    def _create_build_from_template_step(self, placeholder) -> BuildStep:
        """Create a step for a placeholder processed by Build from template.

        A template build processes every placeholder regardless of whether it
        could be re-run in the current scene, so only success/failure applies.
        """
        try:
            label = placeholder.plugin.get_placeholder_label(placeholder)
        except Exception:
            label = placeholder.scene_identifier

        errors = placeholder.get_errors()
        status = "failed" if errors else "succeeded"
        return BuildStep(
            scene_identifier=placeholder.scene_identifier,
            label=label or placeholder.scene_identifier,
            order=placeholder.order,
            status=status,
            duration=self._build_durations.get(
                placeholder.scene_identifier, 0.0
            ),
            error="\n".join(errors),
        )

    def _store_build_history(self) -> None:
        """Keep results of the last few builds."""
        self._build_history.append(
            [BuildStep.from_data(step.to_data()) for step in self._build_steps]
        )
        del self._build_history[:-MAX_BUILD_HISTORY]

    # --- Implementation -----------------------------------------------
