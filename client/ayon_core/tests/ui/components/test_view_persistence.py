"""Round-trip tests for saving and resetting Views.

These cover the paths where a captured :class:`ViewSettings` has to
survive its way to the manager and back: a view row taken straight from
the listing endpoint, and the "reset to AYON defaults" action.
"""

from unittest.mock import Mock

import pytest

from ayon_core.ui.components.views.data_models import (
    ColumnState,
    GroupingDef,
    View,
    ViewSettings,
)
from ayon_core.ui.components.views.view_bindings import ViewBindings
from ayon_core.ui.components.views.view_selector import AYViewSelector


VIEW_TYPE = "versions"


def _defaults() -> ViewSettings:
    """Return consumer defaults with every tracked slice populated."""
    return ViewSettings(
        columns=[ColumnState(name="a", visible=True)],
        sort_by="a",
        sort_desc=False,
        row_height=34,
        grouping=GroupingDef(group_by=None, show_empty_groups=False),
        extra={"myTasksFilter": False, "displayType": "table"},
    )


class _FakeTableView:
    """Minimal stand-in for :class:`AYTableView`'s bindings surface."""

    def __init__(self) -> None:
        self._row_height: int | None = None
        self.column_state: list[ColumnState] = []

    def set_row_height(self, height: int) -> None:
        self._row_height = height

    def row_height(self) -> int | None:
        return self._row_height

    def get_column_state(self) -> list[ColumnState]:
        return list(self.column_state)

    def set_column_state(self, states: list[ColumnState]) -> None:
        self.column_state = list(states)


def _make_bindings(table_view=None) -> ViewBindings:
    model = Mock()
    model.capture_settings.return_value = ViewSettings()
    return ViewBindings(
        model=model,
        table_view=table_view,
        default_settings=_defaults,
    )


# ---------------------------------------------------------------------------
# Row height
# ---------------------------------------------------------------------------

def test_capture_reports_the_live_row_height():
    table_view = _FakeTableView()
    bindings = _make_bindings(table_view)
    bindings.apply(ViewSettings(row_height=24))

    assert table_view.row_height() == 24
    assert bindings.capture().row_height == 24


def test_capture_falls_back_to_defaults_instead_of_zero():
    # No table view to measure: a captured 0 would be stored as
    # "unset" and silently reset to the defaults on the next apply.
    bindings = _make_bindings()

    assert bindings.capture().row_height == _defaults().row_height


def test_row_height_survives_a_payload_round_trip():
    settings = ViewSettings(row_height=24)
    restored = ViewSettings.from_payload(settings.to_payload())

    assert restored.row_height == 24


# ---------------------------------------------------------------------------
# Saving a view listed by the manager
# ---------------------------------------------------------------------------

class _LazyManager:
    """Manager that lists views without their settings, as the server does."""

    def __init__(self, stored: View) -> None:
        self._stored = stored
        self.saved: View | None = None

    def list_views(self, view_type: str) -> list[View]:
        summary = View(
            id=self._stored.id,
            label=self._stored.label,
            view_type=self._stored.view_type,
        )
        summary.loaded = False
        return [summary]

    def load_view(self, view: View) -> View:
        if view.loaded or not view.id:
            return view
        return View.from_payload(self._stored.to_payload())

    def save_view(self, view: View) -> View:
        # Mirrors ServerViewManager.save_view: a view that still claims
        # its settings are unfetched gets them filled in from storage.
        if not view.loaded and view.id:
            stored = self.load_view(view)
            if stored is not view:
                view.settings = stored.settings
                view.loaded = True
        self.saved = view
        return view


def test_saving_a_listed_view_keeps_the_captured_settings():
    stored = View(
        id="v1",
        label="Small rows",
        view_type=VIEW_TYPE,
        settings=ViewSettings(row_height=34),
    )
    manager = _LazyManager(stored)
    table_view = _FakeTableView()
    table_view.set_row_height(24)
    bindings = _make_bindings(table_view)

    listed = manager.list_views(VIEW_TYPE)[0]
    assert listed.loaded is False

    AYViewSelector._capture_into(
        Mock(_bindings=bindings), listed
    )
    manager.save_view(listed)

    assert manager.saved is not None
    assert manager.saved.settings.row_height == 24


# ---------------------------------------------------------------------------
# Reset to the AYON defaults
# ---------------------------------------------------------------------------

@pytest.fixture
def reset_selector():
    """A selector stub exercising only :meth:`apply_default_settings`."""
    table_view = _FakeTableView()
    bindings = _make_bindings(table_view)
    selector = Mock(spec=AYViewSelector)
    selector._bindings = bindings
    selector._manager = Mock()
    selector._manager.get_working_view.return_value = View(
        id="w1", label="Working", view_type=VIEW_TYPE, working=True
    )
    selector._view_type = VIEW_TYPE
    selector._current_user = "me"
    selector._applying_view = False
    selector._working_view_timer = Mock()
    selector.apply_default_settings = (
        lambda: AYViewSelector.apply_default_settings(selector)
    )
    return selector, bindings, table_view


def test_reset_applies_every_default_slice(reset_selector):
    selector, bindings, table_view = reset_selector
    # Diverge from the defaults on every tracked slice first.
    bindings.apply(
        ViewSettings(
            columns=[ColumnState(name="b", visible=True)],
            sort_by="b",
            sort_desc=True,
            row_height=24,
            grouping=GroupingDef(group_by="product"),
            extra={"myTasksFilter": True, "displayType": "grid"},
        )
    )

    selector.apply_default_settings()

    applied = selector.view_applied.emit.call_args.args[0]
    assert applied.settings.grouping.group_by is None
    assert applied.settings.row_height == 34
    assert applied.settings.extra["myTasksFilter"] is False
    assert applied.settings.extra["displayType"] == "table"
    assert table_view.row_height() == 34
    assert bindings._last_grouping.group_by is None


def test_reset_persists_the_working_view(reset_selector):
    selector, _bindings, _table_view = reset_selector

    selector.apply_default_settings()

    # The working view is saved, so the reset survives a restart.
    selector._update_working_view.assert_called_once_with()
    # ...and the reset is not left looking like an unsaved edit.
    selector._clear_modified.assert_called_once_with()


def test_reset_targets_the_working_view(reset_selector):
    selector, _bindings, _table_view = reset_selector

    selector.apply_default_settings()

    assert selector._current_view.working is True
    assert selector._current_view.loaded is True
