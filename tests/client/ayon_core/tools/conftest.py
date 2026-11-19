"""pytest configuration for tool tests.

Tools import Qt and vendored modules (e.g. ``qargparse``) at module
level, so make both importable headless.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

import pytest

# Must be set before any Qt import.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = Path(__file__).resolve().parents[4]
VENDOR_ROOT = REPO_ROOT / "client" / "ayon_core" / "vendor" / "python"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.append(str(VENDOR_ROOT))


@pytest.fixture(scope="session", autouse=True)
def _stop_task_queue():
    """Stop thread of the shared task queue before the process exits.

    Qt application of the tests never quits, so the queue is not stopped
    on 'aboutToQuit' and the process crashes on exit.
    """
    yield
    task_queue = sys.modules.get("ayon_core.ui.components.task_queue")
    if task_queue is not None:
        task_queue.shutdown_task_queue()
