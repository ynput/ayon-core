"""Tests for InMemoryViewManager."""

from __future__ import annotations

from ayon_core.ui.components.views import (
    InMemoryViewManager,
    View,
    ViewSettings,
)


def _make_view(
    label: str = "v",
    view_type: str = "versions",
    working: bool = False,
    position: int = 0,
    owner: str = "alice",
) -> View:
    """Build a minimal View instance for tests."""
    return View(
        label=label,
        view_type=view_type,
        owner=owner,
        working=working,
        position=position,
        settings=ViewSettings(),
    )


def test_save_view_assigns_id_when_missing() -> None:
    """save_view assigns a non-empty id to new views."""
    mgr = InMemoryViewManager()
    view = _make_view("New")
    assert view.id == ""
    saved = mgr.save_view(view)
    assert saved.id
    assert saved is view


def test_list_views_filters_by_view_type_and_sorts() -> None:
    """list_views returns only matching views, sorted by position+label."""
    mgr = InMemoryViewManager()
    mgr.save_view(_make_view("Z", position=0))
    mgr.save_view(_make_view("A", position=0))
    mgr.save_view(_make_view("M", position=-1))
    mgr.save_view(_make_view("Other", view_type="folders"))

    labels = [v.label for v in mgr.list_views("versions")]
    assert labels == ["M", "A", "Z"]


def test_delete_view_removes_and_emits(qtbot) -> None:
    """delete_view removes the view and emits view_deleted+views_changed."""
    mgr = InMemoryViewManager()
    view = mgr.save_view(_make_view("ToDelete"))

    deleted_ids: list[str] = []
    changed_types: list[str] = []
    mgr.view_deleted.connect(deleted_ids.append)
    mgr.views_changed.connect(changed_types.append)

    mgr.delete_view(view.id)

    assert view.id not in {v.id for v in mgr.list_views("versions")}
    assert deleted_ids == [view.id]
    assert changed_types == ["versions"]


def test_delete_view_ignores_unknown_id() -> None:
    """Deleting an unknown id is a no-op."""
    mgr = InMemoryViewManager()
    deleted: list[str] = []
    mgr.view_deleted.connect(deleted.append)
    mgr.delete_view("does-not-exist")
    assert deleted == []


def test_save_view_emits_signals() -> None:
    """save_view emits view_saved and views_changed for the type."""
    mgr = InMemoryViewManager()
    saved_ids: list[str] = []
    changed_types: list[str] = []
    mgr.view_saved.connect(saved_ids.append)
    mgr.views_changed.connect(changed_types.append)

    view = mgr.save_view(_make_view("X"))
    assert saved_ids == [view.id]
    assert changed_types == ["versions"]


def test_get_working_view_returns_flagged_view() -> None:
    """get_working_view returns the one view flagged working=True."""
    mgr = InMemoryViewManager()
    mgr.save_view(_make_view("A"))
    working = mgr.save_view(_make_view("Default", working=True))
    assert mgr.get_working_view("versions") is working
    assert mgr.get_working_view("folders") is None


def test_set_working_view_exclusively_marks_one() -> None:
    """set_working_view clears the flag from previous working views."""
    mgr = InMemoryViewManager()
    a = mgr.save_view(_make_view("A", working=True))
    b = mgr.save_view(_make_view("B"))

    mgr.set_working_view(b)

    a_after = next(v for v in mgr.list_views("versions") if v.id == a.id)
    b_after = next(v for v in mgr.list_views("versions") if v.id == b.id)
    assert a_after.working is False
    assert b_after.working is True


def test_initial_views_seeded() -> None:
    """Manager can be seeded with initial views (with or without ids)."""
    seed = [
        _make_view("Seed1"),
        _make_view("Seed2"),
    ]
    mgr = InMemoryViewManager(views=seed)
    listed = mgr.list_views("versions")
    assert len(listed) == 2
    assert all(v.id for v in listed)


def test_clear_emits_views_changed_per_type() -> None:
    """clear() emits views_changed for every view_type that had views."""
    mgr = InMemoryViewManager()
    mgr.save_view(_make_view("A", view_type="versions"))
    mgr.save_view(_make_view("B", view_type="folders"))
    changed: list[str] = []
    mgr.views_changed.connect(changed.append)
    mgr.clear()
    assert set(changed) == {"versions", "folders"}
    assert mgr.all_views() == []
