"""pytest configuration for visual regression tests.

Sets QT_QPA_PLATFORM=offscreen before any Qt import so tests run headless.
"""

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

# Must be set before any Qt import. pytest-qt respects this too.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Pin the font-size platform key so visual regression images are
# identical regardless of the OS running the test suite.
os.environ["AYON_CORE_UI_FONT_OS"] = "linux"

import pytest

CURRENT_DIR = Path(__file__).parent
REPO_ROOT = CURRENT_DIR.parent.parent.parent.parent
VENDOR_ROOT = REPO_ROOT / "client" / "ayon_core" / "vendor" / "python"
sys.path.append(str(VENDOR_ROOT))

# Accumulated (test_name, obtained_path, ref_path) tuples for --show-images.
_failed_image_tests: list[tuple[str, str, str]] = []


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--show-images",
        action="store_true",
        default=False,
        help=(
            "After the run, open a Qt window showing failed image comparisons."
        ),
    )


@pytest.fixture
def tmp_path(tmp_path_factory, request):
    return tmp_path_factory.mktemp(request.node.name)


@pytest.fixture(autouse=True)
def _reset_task_queue_between_tests():
    """Shut down the AsyncTaskQueue singleton after every test.

    Prevents the worker thread from carrying stale queued callbacks
    into the next test, which can cause use-after-free segfaults when
    those callbacks try to access already-destroyed Qt model/view objects.
    """
    yield
    try:
        from ayon_core.ui.components.task_queue import shutdown_task_queue

        shutdown_task_queue()
    except Exception as err:
        logging.exception("Error shutting down task queue after test: %s", err)


@pytest.fixture(autouse=True)
def _collect_image_failures(request, tmp_path):
    yield
    if not request.config.getoption("--show-images", default=False):
        return
    rep = getattr(request.node, "rep_call", None)
    if rep is None or not rep.failed:
        return
    for obtained in tmp_path.glob("*.obtained.png"):
        basename = obtained.stem.removesuffix(".obtained")
        ref = obtained.with_name(f"{basename}.png")
        if ref.exists():
            _failed_image_tests.append(
                (request.node.nodeid, str(obtained), str(ref))
            )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not session.config.getoption("--show-images", default=False):
        return
    if not _failed_image_tests:
        return
    # clean up labels
    for i, (test_name, _, _) in enumerate(_failed_image_tests):
        l = re.search(r"\[([\w\d]+)\]", test_name)  # noqa: E741
        _failed_image_tests[i] = (
            l.group(1) if l else test_name,
            _failed_image_tests[i][1],
            _failed_image_tests[i][2],
        )

    visual_utils = Path(__file__).parent / "visual_utils.py"
    env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
    subprocess.run(
        [sys.executable, str(visual_utils), json.dumps(_failed_image_tests)],
        env=env,
    )
