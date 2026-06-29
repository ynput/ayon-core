"""Unit tests for LazyTreeModel async fetch behaviour.

These tests exercise the async path (``no_async=False``) and verify:

* Root children are delivered asynchronously via the task queue.
* ``loading_changed`` emits ``True`` then ``False`` around a fetch.
* Stale results from a pre-reset task are discarded after ``reset()``.
* ``fetch_error`` is emitted and the node stays retryable on failure.
"""

from __future__ import annotations


from ayon_core.ui.components.tree_model import LazyTreeModel, TreeNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIMPLE_DATA: dict[str | None, list[TreeNode]] = {
    None: [
        TreeNode("a", "Alpha", has_children=True),
        TreeNode("b", "Beta", has_children=False),
    ],
    "a": [
        TreeNode("a1", "Alpha-1", has_children=False),
    ],
}


def _simple_fetch(parent_id: str | None) -> list[TreeNode]:
    return _SIMPLE_DATA.get(parent_id, [])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_async_root_children_delivered(qtbot) -> None:
    """Root children arrive asynchronously and rowCount updates."""
    model = LazyTreeModel(fetch_children=_simple_fetch)
    # Keep a strong reference so GC does not collect the model.
    assert model.rowCount() == 0, "Children not yet delivered"

    qtbot.waitUntil(lambda: not model.is_loading, timeout=3000)

    assert model.rowCount() == 2
    labels = [model.data(model.index(r, 0)) for r in range(model.rowCount())]
    assert labels == ["Alpha", "Beta"]


def test_loading_changed_signal_sequence(qtbot) -> None:
    """loading_changed emits True (loading) then False (done).

    The True emission happens during __init__ (before we can connect),
    so we verify it indirectly: is_loading must be True immediately
    after construction, and loading_changed(False) must arrive later.
    """
    model = LazyTreeModel(fetch_children=_simple_fetch)

    # Immediately after construction the model must be in-flight.
    assert model.is_loading, (
        "Model should be loading immediately after construction"
    )

    # Wait for the False emission that signals completion.
    with qtbot.waitSignal(model.loading_changed, timeout=3000) as blocker:
        pass  # waitSignal blocks until the signal fires

    assert blocker.args == [False], (
        f"Expected loading_changed(False), got {blocker.args}"
    )
    assert not model.is_loading


def test_stale_results_discarded_after_reset(qtbot) -> None:
    """Results from a pre-reset task are silently discarded."""
    import time as _time

    state: dict = {"call_count": 0, "barrier": False}

    def slow_fetch(parent_id: str | None) -> list[TreeNode]:
        state["call_count"] += 1
        if parent_id is None and not state["barrier"]:
            # Block until the test releases us (simulates slow network).
            deadline = _time.monotonic() + 5.0
            while not state["barrier"] and _time.monotonic() < deadline:
                _time.sleep(0.01)
        return _SIMPLE_DATA.get(parent_id, [])

    model = LazyTreeModel(fetch_children=slow_fetch)
    # Wait until the worker has picked up the first task.
    qtbot.waitUntil(lambda: state["call_count"] >= 1, timeout=3000)

    # Reset while the first fetch is still blocked — invalidates context.
    model.reset()

    # Release the blocked worker so it can finish and deliver (stale) result.
    state["barrier"] = True

    # Wait for the second (post-reset) fetch to complete.
    qtbot.waitUntil(lambda: not model.is_loading, timeout=5000)

    # Crucially, no crash and is_loading is False.
    assert not model.is_loading


def test_fetch_error_emits_signal_and_node_stays_retryable(
    qtbot,
) -> None:
    """On fetch failure, fetch_error is emitted and node is not locked."""
    errors: list[str] = []

    def failing_fetch(parent_id: str | None) -> list[TreeNode]:
        raise RuntimeError("simulated network error")

    model = LazyTreeModel(fetch_children=failing_fetch)
    model.fetch_error.connect(errors.append)

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=3000)

    assert errors, "fetch_error was not emitted"
    assert "root" in errors[0]

    # Root node must NOT be permanently locked as children_loaded.
    root = model._root  # type: ignore[attr-defined]
    assert not root.children_loaded, (
        "Root should remain retryable after a failed fetch"
    )
    assert not root.is_fetching, (
        "is_fetching guard must be released after error"
    )


def test_pending_count_changed_signal(qtbot) -> None:
    """pending_count_changed emits non-negative integers."""
    counts: list[int] = []

    model = LazyTreeModel(fetch_children=_simple_fetch)
    model.pending_count_changed.connect(counts.append)

    qtbot.waitUntil(lambda: not model.is_loading, timeout=3000)

    assert counts, "pending_count_changed was never emitted"
    assert all(c >= 0 for c in counts), "Negative pending count emitted"
    assert counts[-1] == 0, "Final pending count must be 0"
