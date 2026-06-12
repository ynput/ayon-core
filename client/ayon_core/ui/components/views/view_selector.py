"""View-selector widget for table / card view configurations.

The :class:`AYViewSelector` is the user-facing entry point for the
Views feature.  It owns:

- a button that opens a dropdown listing the available views (grouped
  by visibility),
- a small toolbar with *Save*, *Save as…*, *Delete* and *Reset*
  actions,
- the wiring between :class:`ViewManager` (persistence),
  :class:`ViewBindings` (apply/capture) and :class:`AYViewEditor`
  (metadata editing).

The widget is agnostic of the storage backend: the consumer plugs in
its own :class:`ViewManager` subclass.  In standalone demos / tests
the bundled :class:`InMemoryViewManager` is enough.
"""

from __future__ import annotations

import logging

from qtpy.QtCore import Qt, Signal  # type: ignore[attr-defined]
from qtpy.QtWidgets import QDialog, QFrame, QSizePolicy, QWidget

from ..buttons import AYButton
from ..container import AYContainer
from ..dropdown import AYDropdownPopup
from ..label import AYLabel
from ..layouts import AYVBoxLayout

from .data_models import View, Visibility
from .view_bindings import ViewBindings
from .view_editor import AYViewEditor
from .view_manager import ViewManager

log = logging.getLogger(__name__)


# Default access level granted to the current user in standalone demos.
# Real consumer apps should pass the user's actual project access level
# when constructing the selector so View.can_edit() works correctly.
_DEFAULT_USER_ACCESS: int = 50


class _ViewListPopup(AYDropdownPopup):
    """Floating popup that lists available views grouped by visibility.

    Signals:
        view_selected: Emitted with the chosen :class:`View`.
        new_requested: Emitted when the user clicks "Create new view…".
        delete_requested: Emitted with the :class:`View` to delete.
        reset_requested: Emitted when the user clicks
            "Reset to default".
    """

    view_selected = Signal(object)
    new_requested = Signal()
    delete_requested = Signal(object)
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            parent,
            variant=AYDropdownPopup.Variants.Low_Framed_Thin,
            translucent_bg=False,
        )
        self.setMinimumWidth(260)
        self._layout = AYVBoxLayout(self, margin=4, spacing=2)

    # ------------------------------------------------------------------
    # Population
    # ------------------------------------------------------------------

    def populate(
        self,
        views: list[View],
        current_user: str,
        user_access: int,
    ) -> None:
        """Rebuild the popup from *views*.

        Args:
            views: Views to display.  Already sorted by the caller.
            current_user: Used by :meth:`View.can_edit` to enable the
                delete action only on editable rows.
            user_access: The viewer's access level for shared-view gating.
        """
        # Wipe previous contents.
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        private = [v for v in views if v.visibility == Visibility.PRIVATE]
        shared = [v for v in views if v.visibility == Visibility.SHARED]

        if private:
            self._layout.addWidget(self._make_header("Private"))
            for view in private:
                self._layout.addWidget(
                    self._make_row(view, current_user, user_access)
                )

        if shared:
            self._layout.addWidget(self._make_header("Shared"))
            for view in shared:
                self._layout.addWidget(
                    self._make_row(view, current_user, user_access)
                )

        if not views:
            self._layout.addWidget(AYLabel("No saved views.", dim=True))

        # Separator + actions.
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        self._layout.addWidget(sep)

        new_btn = AYButton(
            "Create new view…",
            icon="add",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        new_btn.clicked.connect(self._emit_new)
        self._layout.addWidget(new_btn)

        reset_btn = AYButton(
            "Reset to default",
            icon="refresh",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        reset_btn.clicked.connect(self._emit_reset)
        self._layout.addWidget(reset_btn)

        self.adjustSize()

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _make_header(self, text: str) -> AYLabel:
        """Return a section header label.

        Args:
            text: Section name.

        Returns:
            Styled :class:`AYLabel`.
        """
        label = AYLabel(text.upper(), dim=True)
        label.setContentsMargins(6, 4, 6, 2)
        return label

    def _make_row(
        self,
        view: View,
        current_user: str,
        user_access: int,
    ) -> AYContainer:
        """Build one selectable row for *view*.

        Args:
            view: View to render.
            current_user: Viewer identifier for edit-gating.
            user_access: Viewer access level for shared-view gating.

        Returns:
            An :class:`AYContainer` holding the select button and an
            optional delete button.
        """
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
            lambda _checked=False, v=view: self._emit_selected(v)
        )
        row.add_widget(select_btn, stretch=1)

        if view.can_edit(current_user, user_access):
            del_btn = AYButton(
                icon="delete",
                variant=AYButton.Variants.Nav_Small,
            )
            del_btn.setFixedSize(24, 24)
            del_btn.setToolTip("Delete view")
            del_btn.clicked.connect(
                lambda _checked=False, v=view: self._emit_delete(v)
            )
            row.add_widget(del_btn)

        return row

    # ------------------------------------------------------------------
    # Signal helpers (one-shot: also close the popup)
    # ------------------------------------------------------------------

    def _emit_selected(self, view: View) -> None:
        self.view_selected.emit(view)
        self.close()

    def _emit_delete(self, view: View) -> None:
        self.delete_requested.emit(view)
        self.close()

    def _emit_new(self) -> None:
        self.new_requested.emit()
        self.close()

    def _emit_reset(self) -> None:
        self.reset_requested.emit()
        self.close()


class AYViewSelector(AYContainer):
    """Toolbar-style widget exposing the Views feature.

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
            applying or capturing a view.  Hosts can connect this to a
            toast/snackbar to surface the issue to the user.
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
        super().__init__(
            parent=parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=4,
            layout_spacing=4,
        )
        self.setObjectName("AYViewSelector")
        self.setFixedHeight(32)

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

        self._popup = _ViewListPopup(parent=self)
        self._popup.view_selected.connect(self._on_view_selected)
        self._popup.new_requested.connect(self._on_create_clicked)
        self._popup.delete_requested.connect(self._on_delete_clicked)
        self._popup.reset_requested.connect(self._on_reset_clicked)

        # Refresh when the manager changes.
        self._manager.views_changed.connect(self._on_manager_changed)

        # Forward binding errors via the public ``binding_error`` signal so
        # hosts can surface them.  Overrides any pre-existing
        # ``on_error`` hook (the caller can wrap it themselves to chain).
        if self._bindings.on_error is None:
            self._bindings.on_error = self._on_binding_error

        self._build_ui()
        self.refresh()

    def _on_binding_error(self, stage: str, exc: BaseException) -> None:
        """Forward a :class:`ViewBindings` error via :attr:`binding_error`.

        Args:
            stage: Short identifier of the failing operation.
            exc: The caught exception.
        """
        self.binding_error.emit(stage, str(exc) or exc.__class__.__name__)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the toolbar buttons."""
        self._dropdown_btn = AYButton(
            "Views",
            icon="view_list",
            variant=AYButton.Variants.Nav_Small,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        self._dropdown_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._dropdown_btn.clicked.connect(self._open_popup)
        self.add_widget(self._dropdown_btn, stretch=1)

        self._save_btn = AYButton(
            icon="save",
            variant=AYButton.Variants.Nav_Small,
            tooltip="Save changes to current view",
        )
        self._save_btn.setFixedSize(24, 24)
        self._save_btn.clicked.connect(self._on_save_clicked)
        self.add_widget(self._save_btn)

        self._save_as_btn = AYButton(
            icon="add",
            variant=AYButton.Variants.Nav_Small,
            tooltip="Save as new view…",
        )
        self._save_as_btn.setFixedSize(24, 24)
        self._save_as_btn.clicked.connect(self._on_create_clicked)
        self.add_widget(self._save_as_btn)

        self._update_button_states()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_view_type(self, view_type: str) -> None:
        """Switch to a new view-type identifier.

        Args:
            view_type: The new view-type (e.g. ``"versions"``).
        """
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

        self._update_button_states()

    def current_view(self) -> View | None:
        """Return the currently active view, or ``None``.

        Returns:
            The currently active :class:`View`, or ``None`` when no
            view is active.
        """
        return self._current_view

    # ------------------------------------------------------------------
    # Popup interaction
    # ------------------------------------------------------------------

    def _open_popup(self) -> None:
        """Open the dropdown popup anchored to this widget."""
        self._popup.populate(
            self._views, self._current_user, self._user_access
        )
        self._popup.show_below(self)

    def _on_view_selected(self, view: View) -> None:
        """Handle a view-row click in the popup."""
        self._apply_view(view, emit=True)

    def _on_create_clicked(self) -> None:
        """Open the editor for a new view, then save it."""
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
        # Suppress the manager-driven refresh that fires during
        # save_view; otherwise refresh() would auto-apply the working
        # view (when _current_view is None) and trigger an extra
        # PaginatedTableModel.reset_data() that the subsequent
        # _apply_view(saved) immediately clobbers.
        with self._suspend_auto_apply():
            if editor.delete_requested():
                self._delete_view(editor.get_view())
                return
            saved = self._save_view(editor.get_view())
        if saved is not None:
            self._apply_view(saved, emit=True)

    def _on_save_clicked(self) -> None:
        """Persist the captured state into the current view.

        When no view is active this falls back to "save as new".
        """
        if self._current_view is None:
            self._on_create_clicked()
            return

        # Re-capture the live state into the current view, preserving
        # metadata (label, scope, …) unchanged.
        self._current_view.settings = self._bindings.capture()
        with self._suspend_auto_apply():
            self._save_view(self._current_view)

    def _on_delete_clicked(self, view: View) -> None:
        """Delete *view* via the manager.

        Clears ``_current_view`` *before* invoking the manager so the
        synchronous ``views_changed`` signal triggers exactly one
        :meth:`refresh` pass (which will auto-apply a working view if
        one exists).
        """
        self._delete_view(view)

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
        self._update_button_states()

    def _on_manager_changed(self, view_type: str) -> None:
        """Refresh when the manager signals a change for our type.

        Args:
            view_type: The view-type emitted by the manager.
        """
        if view_type == self._view_type:
            self.refresh()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _apply_view(self, view: View, emit: bool) -> None:
        """Apply *view* to the bindings and update the local state.

        Args:
            view: The view to apply.
            emit: When ``True`` emits :attr:`view_applied`.
        """
        try:
            self._bindings.apply(view.settings)
        except Exception:
            log.exception("Failed to apply view %r", view.id)
            return

        self._current_view = view
        self._update_button_states()
        if emit:
            self.view_applied.emit(view)

    def _save_view(self, view: View) -> View | None:
        """Persist *view* and return the manager's response.

        When ``view.working`` is True, routes through
        :meth:`ViewManager.set_working_view` so the "at most one
        working view per (user, view_type)" invariant documented on
        :attr:`View.working` is preserved.  Otherwise calls
        :meth:`ViewManager.save_view` directly.

        Args:
            view: The view to save.

        Returns:
            The saved view, or ``None`` when the manager raised.
        """
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
        """Return a context manager that suppresses the
        manager-driven refresh while a save is in flight.

        Returns:
            A context-manager that toggles ``_suppress_auto_apply``.
        """
        return _SuspendAutoApply(self)

    def _update_button_states(self) -> None:
        """Refresh button labels / enabled states from the current view."""
        if self._current_view is not None:
            label = self._current_view.label or "(unnamed)"
            self._dropdown_btn.setText(label)
        else:
            self._dropdown_btn.setText("Views")

        can_save = (
            self._current_view is not None
            and self._current_view.can_edit(
                self._current_user, self._user_access
            )
        )
        self._save_btn.setEnabled(can_save)


class _SuspendAutoApply:
    """Context manager that toggles
    :attr:`AYViewSelector._suppress_auto_apply`.

    Used around save operations: while the flag is True,
    :meth:`AYViewSelector.refresh` (triggered synchronously by the
    manager's ``views_changed`` signal) skips its working-view auto-
    apply branch, preventing a redundant
    :meth:`PaginatedTableModel.reset_data` that would be clobbered by
    the explicit :meth:`AYViewSelector._apply_view` call immediately
    following the save.
    """

    def __init__(self, selector: "AYViewSelector") -> None:
        """Store the selector to mutate on enter / exit.

        Args:
            selector: The owning :class:`AYViewSelector`.
        """
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
        """Return a small set of demo views.

        Returns:
            Three sample :class:`View` instances (working / private /
            shared) seeded into the in-memory manager.
        """
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
                            "exclude": False,
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
        toolbar = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=8,
            layout_margin=0,
        )
        toolbar.add_widget(selector, stretch=1)
        outer.add_widget(toolbar)
        outer.add_widget(filter_bar)
        outer.add_widget(table, stretch=1)
        outer.setMinimumWidth(900)
        return outer

    test(_build, style=Style.AyonStyleOverCSS)
