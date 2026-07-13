"""Base class for visual widget tests."""

from __future__ import annotations

from abc import abstractmethod
from typing import Callable, Optional

from qtpy.QtWidgets import QWidget


class WidgetTest:
    """Base class for visual regression tests of AYON UI components.

    Subclass this in tests/components/test_*.py, implement build() and
    optionally steps(). The runner in test_visual.py discovers subclasses
    and drives the snapshot lifecycle.

    Class attributes:
        size: Widget dimensions (width, height) applied before first snapshot.
        tolerance: Per-pixel diff tolerance in the 0.0-1.0 range, passed to
            image_regression.check(diff_threshold=...).
    """

    size: tuple[int, int] = (800, 600)
    tolerance: float = 0.0

    def __init__(self, qbot=None) -> None:
        self.widget: Optional[QWidget] = None
        self._qbot = qbot

    @abstractmethod
    def build(self) -> QWidget:
        """Build and return the widget under test.

        Called once per test run. Store any widgets you need to manipulate in
        steps as instance attributes here.
        """

    def steps(self) -> list[Callable[[], None]]:
        """Return ordered list of callables that mutate widget state.

        Each callable is invoked once and followed by a snapshot. Method names
        become part of the snapshot filename, so keep them descriptive.
        Default implementation returns an empty list (initial snapshot only).
        """
        return []

    def wait_loaded(self, qtbot) -> None:  # type: ignore[no-untyped-def]
        """Block until the widget's data has finished loading.

        Called by the test runner immediately after the widget is shown
        and after each step, before the snapshot is taken.

        The default implementation is a no-op.  Override in subclasses
        that need to wait for data to appear:

        * **Synchronous / ``no_async=True`` models** — call
          ``QApplication.processEvents()`` to flush pending paint events::

              def wait_loaded(self, qtbot) -> None:
                  from qtpy.QtWidgets import QApplication
                  QApplication.processEvents()

        * **Truly async models** — use ``qtbot.waitUntil`` to block until
          the model signals that all in-flight fetches have completed::

              def wait_loaded(self, qtbot) -> None:
                  qtbot.waitUntil(lambda: not self._model.is_loading)
        """
        return

    def cleanup(self, step_name: str) -> None:
        """Clean up after a step.

        Called by the test runner after each step, before the next step is
        executed. The default implementation is a no-op. Override in subclasses
        that need to clean up after a step, e.g. to close a popup menu or reset
        the mouse position.
        """
        return
