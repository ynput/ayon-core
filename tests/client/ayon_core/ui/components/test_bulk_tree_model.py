"""Unit tests for BulkTreeModel.

Unlike LazyTreeModel, BulkTreeModel fetches the whole hierarchy in one
shot (via a single fetch_all callback, run on the shared task queue)
rather than one query per expanded level. These tests verify:

* The whole tree - including deep, never-expanded branches - is
  available as soon as the single fetch resolves.
* loading_changed emits True then False around the fetch.
* Stale results from a pre-reset fetch are discarded after reset().
* fetch_error is emitted on failure and the model ends up empty
  (not crashed).
* FILTER_ROLE exposes filter_text, falling back to the label.
* get_index_by_id finds nodes anywhere in the tree, not just the root.
"""

from __future__ import annotations

from unittest.mock import Mock

from ayon_core.ui.components.tree_model import BulkTreeModel, TreeNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATA: dict[str | None, list[TreeNode]] = {
    None: [
        TreeNode("a", "Alpha", has_children=True, filter_text="/alpha"),
        TreeNode("b", "Beta", has_children=False),
    ],
    "a": [
        TreeNode(
            "a1", "Alpha-1", has_children=True,
            filter_text="/alpha/alpha-1",
        ),
    ],
    "a1": [
        TreeNode(
            "a1x", "Alpha-1-X", has_children=False,
            filter_text="/alpha/alpha-1/alpha-1-x",
        ),
    ],
}


def _fetch_all() -> dict[str | None, list[TreeNode]]:
    return _DATA


def _started_model(fetch_all, **kwargs) -> BulkTreeModel:
    """Create a model and start its first fetch.

    The model does not fetch on construction - the owner starts it
    with :meth:`BulkTreeModel.reset` once the data is actually needed.
    """
    model = BulkTreeModel(fetch_all=fetch_all, **kwargs)
    model.reset()
    return model


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_fetch_on_construction(qtbot) -> None:
    fetch_all = Mock(return_value=_DATA)

    model = BulkTreeModel(fetch_all=fetch_all, no_async=True)

    fetch_all.assert_not_called()
    assert not model.is_loading
    assert model.rowCount() == 0


def test_whole_tree_available_without_any_expand(qtbot) -> None:
    """Deep, never-expanded branches are present from the single fetch."""
    model = _started_model(_fetch_all, no_async=True)

    a1x_index = model.get_index_by_id("a1x")
    assert a1x_index.isValid()
    assert model.data(a1x_index) == "Alpha-1-X"

    # No fetchMore()/canFetchMore() protocol involved: everything is
    # already materialised as real rows.
    assert model.rowCount(model.get_index_by_id("a1")) == 1


def test_async_tree_delivered(qtbot) -> None:
    """The tree is built asynchronously via the shared task queue."""
    model = _started_model(_fetch_all)
    assert model.rowCount() == 0, "Tree not yet delivered"

    qtbot.waitUntil(lambda: not model.is_loading, timeout=3000)

    assert model.rowCount() == 2
    labels = [model.data(model.index(r, 0)) for r in range(model.rowCount())]
    assert labels == ["Alpha", "Beta"]
    assert model.get_index_by_id("a1x").isValid()


def test_loading_changed_signal_sequence(qtbot) -> None:
    model = _started_model(_fetch_all)

    assert model.is_loading, (
        "Model should be loading immediately after reset"
    )

    with qtbot.waitSignal(model.loading_changed, timeout=3000) as blocker:
        pass

    assert blocker.args == [False]
    assert not model.is_loading


def test_stale_results_discarded_after_reset(qtbot) -> None:
    """Results from a pre-reset fetch are silently discarded."""
    import time as _time

    state: dict = {"call_count": 0, "barrier": False}

    def slow_fetch() -> dict[str | None, list[TreeNode]]:
        state["call_count"] += 1
        if not state["barrier"]:
            deadline = _time.monotonic() + 5.0
            while not state["barrier"] and _time.monotonic() < deadline:
                _time.sleep(0.01)
        return _DATA

    model = _started_model(slow_fetch)
    qtbot.waitUntil(lambda: state["call_count"] >= 1, timeout=3000)

    model.reset()

    state["barrier"] = True

    qtbot.waitUntil(lambda: not model.is_loading, timeout=5000)

    # No crash, and the second (post-reset) fetch landed cleanly.
    assert not model.is_loading
    assert model.get_index_by_id("a1x").isValid()


def test_fetch_error_emits_signal_and_leaves_model_empty(qtbot) -> None:
    errors: list[str] = []

    def failing_fetch() -> dict[str | None, list[TreeNode]]:
        raise RuntimeError("simulated network error")

    model = BulkTreeModel(fetch_all=failing_fetch)
    model.fetch_error.connect(errors.append)
    model.reset()

    qtbot.waitUntil(lambda: len(errors) > 0, timeout=3000)

    assert errors
    assert not model.is_loading
    assert model.rowCount() == 0


def test_filter_role_falls_back_to_label_without_filter_text(qtbot) -> None:
    model = _started_model(_fetch_all, no_async=True)

    b_index = model.get_index_by_id("b")
    assert model.data(b_index, BulkTreeModel.FILTER_ROLE) == "Beta"


def test_filter_role_returns_filter_text_when_set(qtbot) -> None:
    model = _started_model(_fetch_all, no_async=True)

    a1x_index = model.get_index_by_id("a1x")
    assert (
        model.data(a1x_index, BulkTreeModel.FILTER_ROLE)
        == "/alpha/alpha-1/alpha-1-x"
    )


def test_get_index_by_id_finds_nested_nodes(qtbot) -> None:
    model = _started_model(_fetch_all, no_async=True)

    assert model.get_index_by_id("a1").isValid()
    assert model.get_index_by_id("a1x").isValid()
    assert not model.get_index_by_id("does-not-exist").isValid()
