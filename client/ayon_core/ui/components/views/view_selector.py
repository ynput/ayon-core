"""View-selector widget for table / card view configurations.

The :class:`AYViewSelector` is the user-facing entry point for the
Views feature.  It is a single icon button that opens a dropdown
listing the available views (grouped by visibility) along with a
"Create new view" entry and an inline reset button on the current
view row.

It owns the wiring between :class:`ViewManager` (persistence),
:class:`ViewBindings` (apply/capture) and :class:`AYViewEditor`
(metadata editing).
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Qt, Signal  # type: ignore[attr-defined]
from qtpy.QtWidgets import QDialog, QFrame, QSizePolicy, QWidget

from ..buttons import AYButton, AYButtonMenu
from ..container import AYContainer
from ..label import AYLabel

from .data_models import View, Visibility
from .view_bindings import ViewBindings
from .view_editor import AYViewEditor
from .view_manager import ViewManager

log = logging.getLogger(__name__)


# Default access level granted to the current user in standalone demos.
# Real consumer apps should pass the user's actual project access level
# when constructing the selector so View.can_edit() works correctly.
_DEFAULT_USER_ACCESS: int = 50


class AYViewSelector(AYButtonMenu):
    """Icon button exposing the Views feature.

    Public API:

    - :meth:`set_view_type` — switch the view-type identifier and reload.
    - :meth:`refresh` — re-pull the view list from the manager.
    - :meth:`current_view` — return the active :class:`View` (or
      ``None``).

    Signals:
        view_applied(View): Emitted after a view has been applied to
            the bindings.
        view_saved(View): Emitted after a view has been persisted.
        view_deleted(str): Emitted with the view id after deletion.
        binding_error(str, str): Emitted with ``(stage, message)`` when
            :class:`ViewBindings` reports a non-fatal failure while
            applying or capturing a view.
    """

    view_applied = Signal(object)
    view_saved = Signal(object)
    view_deleted = Signal(str)
    binding_error = Signal(str, str)

    def __init__(
        self,
        bindings: ViewBindings,
        manager: ViewManager,
        view_type: str,
        current_user: str = "",
        user_access_level: int = _DEFAULT_USER_ACCESS,
        allow_studio_scope: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        # Store state before super().__init__() because the base class
        # invokes ``populate_callback`` during construction.
        self._bindings = bindings
        self._manager = manager
        self._view_type = view_type
        self._current_user = current_user
        self._user_access = int(user_access_level)
        self._allow_studio_scope = bool(allow_studio_scope)

        self._current_view: View | None = None
        self._views: list[View] = []
        # When True, :meth:`refresh` skips its auto-apply-working-view
        # branch.  Toggled by :class:`_SuspendAutoApply` around save
        # operations so the manager-driven refresh during save_view
        # does not trigger a redundant page-0 refetch.
        self._suppress_auto_apply: bool = False

        self._dropdown_layout = None  # type: ignore[assignment]

        super().__init__(
            populate_callback=self._populate_menu,
            icon="view_quilt",
            variant=AYButton.Variants.Surface,
            tooltip="Views",
            parent=parent,
        )
        self.setObjectName("AYViewSelector")
        self.setFixedSize(32, 32)

        # Rebuild the menu contents each time it opens, since the view
        # list may change between openings.
        self.menu_opened.connect(self._rebuild_menu)

        # Refresh when the manager changes.
        self._manager.views_changed.connect(self._on_manager_changed)

        # Forward binding errors via the public ``binding_error`` signal so
        # hosts can surface them.  Overrides any pre-existing
        # ``on_error`` hook (the caller can wrap it themselves to chain).
        if self._bindings.on_error is None:
            self._bindings.on_error = self._on_binding_error

        self.refresh()

    # ------------------------------------------------------------------
    # Menu population
    # ------------------------------------------------------------------

    def _populate_menu(self, container: QFrame) -> None:
        """Initial populate callback invoked by :class:`AYButtonMenu`.

        We only cache the container's layout here; actual contents are
        (re)built on every menu open via :meth:`_rebuild_menu`.

        Args:
            container: The dropdown ``QFrame`` provided by the base.
        """
        layout = container.layout()
        if layout is not None:
            layout.setContentsMargins(4, 4, 4, 4)
            layout.setSpacing(2)
        self._dropdown_layout = layout

    def _rebuild_menu(self) -> None:
        """Rebuild the dropdown contents from the current view list."""
        layout = self._dropdown_layout
        if layout is None:
            return

        # Wipe previous contents.
        while layout.count():
            item = layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        # Current view row with inline reset button.
        if self._current_view is not None:
            layout.addWidget(self._make_current_row(self._current_view))
            layout.addWidget(self._make_separator())

        private = [
            v for v in self._views if v.visibility == Visibility.PRIVATE
        ]
        shared = [v for v in self._views if v.visibility == Visibility.SHARED]

        if private:
            layout.addWidget(self._make_header("My views"))
            for view in private:
                layout.addWidget(self._make_row(view))

        if shared:
            layout.addWidget(self._make_header("Shared views"))
            for view in shared:
                layout.addWidget(self._make_row(view))

        if not self._views:
            layout.addWidget(AYLabel("No saved views.", dim=True))

        layout.addWidget(self._make_separator())

        new_btn = AYButton(
            "Create new view…",
            icon="add",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        new_btn.clicked.connect(self._on_create_clicked)
        layout.addWidget(new_btn)

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        return sep

    def _make_header(self, text: str) -> AYLabel:
        """Return a section header label."""
        label = AYLabel(text, dim=True)
        label.setContentsMargins(6, 4, 6, 2)
        return label

    def _make_current_row(self, view: View) -> AYContainer:
        """Build the current-view row with an inline reset button."""
        row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=4,
            layout_margin=0,
        )

        label_btn = AYButton(
            view.label or "(unnamed view)",
            icon="check",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        label_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        label_btn.setEnabled(False)
        row.add_widget(label_btn, stretch=1)

        reset_btn = AYButton(
            icon="restart_alt",
            variant=AYButton.Variants.Nav_Small,
            tooltip="Reset to default",
        )
        reset_btn.setFixedSize(24, 24)
        reset_btn.clicked.connect(self._on_reset_clicked)
        row.add_widget(reset_btn)

        return row

    def _make_row(self, view: View) -> AYContainer:
        """Build one selectable row for *view*."""
        row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=4,
            layout_margin=0,
        )

        icon = "star" if view.working else "view_list"
        select_btn = AYButton(
            view.label or "(unnamed view)",
            icon=icon,
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        select_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        select_btn.clicked.connect(
            lambda _checked=False, v=view: self._on_view_selected(v)
        )
        row.add_widget(select_btn, stretch=1)

        if view.can_edit(self._current_user, self._user_access):
            edit_btn = AYButton(
                icon="more_horiz",
                variant=AYButton.Variants.Nav_Small,
                tooltip="Edit view…",
            )
            edit_btn.setFixedSize(24, 24)
            edit_btn.clicked.connect(
                lambda _checked=False, v=view: self._on_edit_clicked(v)
            )
            row.add_widget(edit_btn)

        return row

    def _on_binding_error(self, stage: str, exc: BaseException) -> None:
        """Forward a :class:`ViewBindings` error via :attr:`binding_error`."""
        self.binding_error.emit(stage, str(exc) or exc.__class__.__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_view_type(self, view_type: str) -> None:
        """Switch to a new view-type identifier."""
        if view_type == self._view_type:
            return
        self._view_type = view_type
        self._current_view = None
        self.refresh()

    def refresh(self) -> None:
        """Re-pull the view list from the manager.

        Also picks the manager's working view (if any) and applies it
        when no view is currently active.
        """
        try:
            self._views = list(self._manager.list_views(self._view_type))
        except Exception:
            log.exception("Failed to list views for %r", self._view_type)
            self._views = []

        if self._current_view is None and not self._suppress_auto_apply:
            working = next((v for v in self._views if v.working), None)
            if working is not None:
                self._apply_view(working, emit=True)

    def current_view(self) -> View | None:
        """Return the currently active view, or ``None``."""
        return self._current_view

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_view_selected(self, view: View) -> None:
        """Handle a view-row click in the dropdown."""
        self._apply_view(view, emit=True)
        self._close_menu()

    def _on_edit_clicked(self, view: View) -> None:
        """Open the editor for an existing view."""
        self._close_menu()
        editor = AYViewEditor(
            view,
            current_user=self._current_user,
            allow_studio_scope=self._allow_studio_scope,
            parent=self,
        )
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        with self._suspend_auto_apply():
            if editor.delete_requested():
                self._delete_view(editor.get_view())
                return
            saved = self._save_view(editor.get_view())
        if saved is not None and (
            self._current_view is not None
            and self._current_view.id == saved.id
        ):
            self._apply_view(saved, emit=True)

    def _on_create_clicked(self) -> None:
        """Open the editor for a new view, then save it."""
        self._close_menu()
        new_view = View(view_type=self._view_type)
        new_view.settings = self._bindings.capture()
        editor = AYViewEditor(
            new_view,
            current_user=self._current_user,
            allow_studio_scope=self._allow_studio_scope,
            parent=self,
        )
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        with self._suspend_auto_apply():
            if editor.delete_requested():
                self._delete_view(editor.get_view())
                return
            saved = self._save_view(editor.get_view())
        if saved is not None:
            self._apply_view(saved, emit=True)

    def _delete_view(self, view: View) -> None:
        if not view.id:
            return
        if self._current_view is not None and self._current_view.id == view.id:
            self._current_view = None
        try:
            self._manager.delete_view(view.id)
        except Exception:
            log.exception("Failed to delete view %r", view.id)
            return
        self.view_deleted.emit(view.id)

    def _on_reset_clicked(self) -> None:
        """Clear the active view (does *not* persist anything)."""
        self._current_view = None
        self._close_menu()

    def _on_manager_changed(self, view_type: str) -> None:
        """Refresh when the manager signals a change for our type.

        An empty *view_type* is treated as a sentinel meaning "all types
        changed" (emitted by :class:`ServerViewManager` when it switches
        project before any view type has been listed).
        """
        if not view_type or view_type == self._view_type:
            self.refresh()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _close_menu(self) -> None:
        """Close the dropdown popup if currently open."""
        try:
            self._dropdown.close()
        except Exception:
            pass

    def _apply_view(self, view: View, emit: bool) -> None:
        """Apply *view* to the bindings and update the local state."""
        try:
            self._bindings.apply(view.settings)
        except Exception:
            log.exception("Failed to apply view %r", view.id)
            return

        self._current_view = view
        if emit:
            self.view_applied.emit(view)

    def _save_view(self, view: View) -> View | None:
        """Persist *view* and return the manager's response."""
        try:
            if view.working:
                self._manager.set_working_view(view)
                saved = view
            else:
                saved = self._manager.save_view(view)
        except Exception:
            log.exception("Failed to save view %r", view.label)
            return None
        self.view_saved.emit(saved)
        return saved

    def _suspend_auto_apply(self) -> "_SuspendAutoApply":
        """Return a context manager that suppresses the auto-apply branch
        of :meth:`refresh` while a save is in flight.
        """
        return _SuspendAutoApply(self)


class _SuspendAutoApply:
    """Context manager that toggles
    :attr:`AYViewSelector._suppress_auto_apply`.
    """

    def __init__(self, selector: "AYViewSelector") -> None:
        self._selector = selector

    def __enter__(self) -> "_SuspendAutoApply":
        self._selector._suppress_auto_apply = True
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._selector._suppress_auto_apply = False


__all__ = ("AYViewSelector",)


# =============================================================================
# __main__ - standalone tester
# =============================================================================

if __name__ == "__main__":  # pragma: no cover
    from qtpy import QtWidgets

    from ...tester import Style, test
    from ..table_filter import AYTableFilter
    from ..table_model import (
        HIERARCHICAL_TEST_DATA,
        PaginatedTableModel,
        TableColumn,
        make_hierarchical_test_fetch,
    )
    from ..table_view import AYTableView
    from .data_models import (
        ColumnState,
        FilterDef,
        Scope,
        View,
        ViewSettings,
        Visibility,
    )
    from .view_bindings import ViewBindings
    from .view_manager import InMemoryViewManager

    _USER = "demo_user"
    _VIEW_TYPE = "versions"

    def _seed_views() -> list[View]:
        """Return a small set of demo views."""
        working = View(
            id="",
            label="Working",
            view_type=_VIEW_TYPE,
            settings=ViewSettings(
                columns=[
                    ColumnState(name="name", visible=True, width=250),
                    ColumnState(name="status", visible=True),
                    ColumnState(name="type", visible=True),
                    ColumnState(name="author", visible=True),
                    ColumnState(name="version", visible=True),
                ],
                sort_by="name",
                sort_desc=False,
                row_height=32,
            ),
            owner=_USER,
            scope=Scope.PROJECT,
            visibility=Visibility.PRIVATE,
            working=True,
        )

        approved = View(
            id="",
            label="My Approved Shots",
            view_type=_VIEW_TYPE,
            settings=ViewSettings(
                columns=[
                    ColumnState(name="name", visible=True, width=280),
                    ColumnState(name="status", visible=True, width=120),
                    ColumnState(name="version", visible=True, width=80),
                ],
                sort_by="version",
                sort_desc=True,
                filter=FilterDef(
                    conditions=[
                        {
                            "key": "status",
                            "label": "Status",
                            "values": ["Approved"],
                            "useSubstring": False,
                        }
                    ],
                    operator="and",
                ),
            ),
            owner=_USER,
            visibility=Visibility.PRIVATE,
        )

        producer = View(
            id="",
            label="Producer review",
            view_type=_VIEW_TYPE,
            settings=ViewSettings(
                columns=[
                    ColumnState(name="name", visible=True, width=250),
                    ColumnState(name="status", visible=True),
                    ColumnState(name="author", visible=True),
                ],
                sort_by="status",
            ),
            owner="producer",
            scope=Scope.PROJECT,
            visibility=Visibility.SHARED,
            access_level=20,
        )

        return [working, approved, producer]

    def _build() -> QtWidgets.QWidget:
        columns = [
            TableColumn("name", "Name", width=250, sortable=True),
            TableColumn("status", "Status", width=120, sortable=True),
            TableColumn("type", "Type", width=120, sortable=True),
            TableColumn("author", "Author", width=120, sortable=False),
            TableColumn("version", "Version", width=80, sortable=True),
        ]

        # Restrict to leaf rows so the demo is flat (the selector itself
        # does not yet manage tree-mode toggling).
        leaf_rows = [
            row
            for rows in HIERARCHICAL_TEST_DATA.values()
            for row in rows
            if not row.get("has_children", False)
        ]
        leaf_fetch = make_hierarchical_test_fetch({None: leaf_rows})
        model = PaginatedTableModel(
            fetch_page=leaf_fetch, columns=columns, page_size=50
        )

        filter_bar = AYTableFilter(model=model)
        table = AYTableView()
        table.setModel(filter_bar.filter_model)
        table.setMinimumHeight(420)

        manager = InMemoryViewManager(views=_seed_views())
        bindings = ViewBindings(
            model=model,
            table_view=table,
            filter_bar=filter_bar,
        )
        selector = AYViewSelector(
            bindings=bindings,
            manager=manager,
            view_type=_VIEW_TYPE,
            current_user=_USER,
            allow_studio_scope=False,
        )
        selector.view_applied.connect(
            lambda v: print(f"[demo]  applied view {v.label!r}")
        )
        selector.view_saved.connect(
            lambda v: print(f"[demo]  saved view {v.label!r} ({v.id})")
        )
        selector.view_deleted.connect(
            lambda vid: print(f"[demo]  deleted view {vid}")
        )

        outer = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=6,
        )
        # The view selector lives on the right side of the filter bar.
        filter_row = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=8,
            layout_margin=0,
        )
        filter_row.add_widget(filter_bar, stretch=1)
        filter_row.add_widget(selector)
        outer.add_widget(filter_row)
        outer.add_widget(table, stretch=1)
        outer.setMinimumWidth(900)
        return outer

    test(_build, style=Style.AyonStyleOverCSS)
