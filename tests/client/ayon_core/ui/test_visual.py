"""Auto-discovering visual regression test runner.

Scans tests/components/ for WidgetTest subclasses and generates two
parametrized pytest items per class:
  - test_initial: initial widget state snapshot
  - test_steps:   one snapshot per step callable

Run with --force-regen to create/update reference images.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Type

import pytest

from visual_utils import capture_widget
from widget_test import WidgetTest


def _collect_widget_test_classes() -> list[Type[WidgetTest]]:
    """Import all test_*.py modules under tests/components/ and return
    WidgetTest subclasses."""
    components_dir = Path(__file__).parent / "components"
    classes: list[Type[WidgetTest]] = []
    for module_info in pkgutil.iter_modules([str(components_dir)]):
        if not module_info.name.startswith("test_"):
            continue
        module = importlib.import_module(f"components.{module_info.name}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, WidgetTest) and obj is not WidgetTest:
                classes.append(obj)
    return classes


_widget_test_classes = _collect_widget_test_classes()


def _cls_id(cls: Type[WidgetTest]) -> str:
    return cls.__name__


# ---------------------------------------------------------------------------
# Initial-state test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("widget_test_cls", _widget_test_classes, ids=_cls_id)
def test_initial(widget_test_cls: Type[WidgetTest], qtbot, image_regression):
    """Snapshot the widget in its initial state (before any steps)."""
    from ayon_core.ui.style_types import get_ayon_style

    wt = widget_test_cls(qbot=qtbot)
    widget = wt.build()
    wt.widget = widget

    widget.resize(*widget_test_cls.size)
    widget.setStyle(get_ayon_style())
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    wt.wait_loaded(qtbot)

    image_regression.check(
        capture_widget(widget),
        diff_threshold=widget_test_cls.tolerance,
        basename=f"{widget_test_cls.__name__}_00_initial",
    )


# ---------------------------------------------------------------------------
# Step tests
# ---------------------------------------------------------------------------


def _step_params() -> list[pytest.param]:
    params = []
    for cls in _widget_test_classes:
        # Instantiate to inspect step names; build() is not called.
        probe = cls()
        for i, step_fn in enumerate(probe.steps()):
            step_name = getattr(step_fn, "__name__", f"step_{i}")
            params.append(
                pytest.param(
                    cls,
                    i,
                    id=f"{cls.__name__}_{i + 1:02d}_{step_name}",
                )
            )
    return params


@pytest.mark.parametrize("widget_test_cls,step_index", _step_params())
def test_steps(
    widget_test_cls: Type[WidgetTest],
    step_index: int,
    qtbot,
    image_regression,
):
    """Snapshot the widget after applying all steps up to and including
    step_index."""
    from ayon_core.ui.style_types import get_ayon_style

    wt = widget_test_cls(qbot=qtbot)
    widget = wt.build()
    wt.widget = widget

    widget.resize(*widget_test_cls.size)
    widget.setStyle(get_ayon_style())
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    wt.wait_loaded(qtbot)

    steps = wt.steps()
    for i in range(step_index + 1):
        steps[i]()
        wt.wait_loaded(qtbot)
        qtbot.wait(10)  # process pending events / repaints
        if i < step_index:
            intermediate_name = getattr(steps[i], "__name__", f"step_{i}")
            wt.cleanup(intermediate_name)

    step_fn = steps[step_index]
    step_name = getattr(step_fn, "__name__", f"step_{step_index}")
    basename = f"{widget_test_cls.__name__}_{step_index + 1:02d}_{step_name}"

    image_regression.check(
        capture_widget(widget),
        diff_threshold=widget_test_cls.tolerance,
        basename=basename,
    )
