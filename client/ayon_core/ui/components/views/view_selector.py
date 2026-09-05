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
from typing import Callable

import ayon_api
from qtpy.QtCore import (  # type: ignore[attr-defined]
    QEvent,
    QObject,
    Qt,
    QTimer,
    Signal,
)
from qtpy.QtWidgets import (
    QDialog,
    QFrame,
    QWidget,
)

from ..buttons import AYButton, AYButtonMenu
from ..container import AYContainer
from ..frame import RowHoverTracker
from ..label import AYLabel
from ..scroll_area import AYScrollArea

from .data_models import View, ViewSettings, Visibility, Scope
from .default_view_control import DefaultViewControl
from .view_bindings import ViewBindings
from .view_editor import AYViewEditor
from .view_manager import ViewManager, DEFAULT_VIEW_LABEL

log = logging.getLogger(__name__)

# Default access level granted to the current user in standalone demos.
# Real consumer apps should pass the user's actual project access level
# when constructing the selector so View.can_edit() works correctly.
_DEFAULT_USER_ACCESS: int = 50

# Shared minimum height for every list-style dropdown row (working view,
# per-view rows, "Create new view…"). Without this, a row with no
# trailing Row_Action button (26px) collapses to just its label's own
# height, making it look visibly thinner than its siblings even though
# all rows use the same contents margins.
_ROW_MIN_HEIGHT: int = 34

# Cap on the height of the scrollable views list (working view + "My
# views" + "Shared views") before it grows a scrollbar instead of
# pushing "Default view" / "Create new view…" further down — mirrors
# the frontend's views-menu scroll behavior.
_VIEWS_LIST_MAX_HEIGHT: int = 490


class _HoverReveal(QObject):
    """Event filter that shows *widget* only while
    the watched widget is hovered.

    Args:
        widget: The widget to reveal/hide.
        parent: The watched widget (also used as the filter's parent).
        force_visible: Optional callable; when it returns ``True`` the
            widget stays visible on Leave instead of being hidden (used
            to keep a collapsed section's expand chevron visible even
            when the header isn't hovered).
    """

    def __init__(
        self,
        widget: QWidget,
        parent: QObject,
        force_visible: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(parent)
        self._widget = widget
        self._force_visible = force_visible

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._widget.setVisible(True)
        elif event.type() == QEvent.Type.Leave:
            self._widget.setVisible(
                bool(self._force_visible and self._force_visible())
            )
        return False  # never consume the event


class _ClickableRow(AYContainer):
    """A row that is itself the primary click target.

    Its label is plain, non-interactive text (not a button), so the
    row "wraps" its trailing action buttons the way a single button
    would: clicking anywhere in the row's own background or margins —
    including the gaps around a trailing icon button — triggers
    *on_click*. Clicking directly on one of those icon buttons still
    reaches that button first (Qt routes the event to the topmost
    widget under the cursor) and never reaches here.
    """

    def __init__(
        self,
        *args,
        on_click: Callable[[], None],
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._on_click = on_click
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.pos()
        ):
            self._on_click()
        super().mouseReleaseEvent(event)


class _SectionHeader(AYContainer):
    """Clickable, collapsible header for a section of the views dropdown.

    Mirrors the frontend's views-menu section header: the collapse
    chevron stays hidden until the row is hovered, except while the
    section is collapsed, where it stays visible so users can tell
    there is more to expand.
    """

    def __init__(
        self,
        title: str,
        collapsed: bool,
        on_toggle: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Popover,
            layout_spacing=4,
            layout_margin=0,
            hover_enabled=True,
            parent=parent,
        )
        self._on_toggle = on_toggle
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        label = AYLabel(title, dim=True, rel_text_size=-1)
        label.setContentsMargins(6, 4, 0, 4)
        self.add_widget(label, stretch=1)

        chevron = AYLabel(
            icon="chevron_right" if collapsed else "expand_more",
            icon_size=14,
            dim=True,
        )
        chevron.setContentsMargins(0, 4, 6, 4)
        size_policy = chevron.sizePolicy()
        size_policy.setRetainSizeWhenHidden(True)
        chevron.setSizePolicy(size_policy)
        # Parent it before toggling visibility: setVisible() on a still-
        # parentless widget makes Qt treat it as its own top-level
        # window, which steals activation from the dropdown popup and
        # triggers its Qt.WindowType.Popup auto-close.
        self.add_widget(chevron)
        chevron.setVisible(collapsed)

        self.installEventFilter(
            _HoverReveal(chevron, self, force_visible=lambda: collapsed)
        )

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.pos()
        ):
            self._on_toggle()
        super().mouseReleaseEvent(event)


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
        view_modified(str, bool): Emitted when the live UI no longer
            matches the loaded view settings, or when it returns to the
            saved state. Payload is ``(current_view_name, modified)``.
        binding_error(str, str): Emitted with ``(stage, message)`` when
            :class:`ViewBindings` reports a non-fatal failure while
            applying or capturing a view.
    """

    view_applied = Signal(object)
    view_saved = Signal(object)
    view_deleted = Signal(str)
    view_modified = Signal(str, bool)
    binding_error = Signal(str, str)
    default_view_message = Signal(str, bool)

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
        # Dirty flag: set on any UI change, cleared on apply/save/reset.
        # just highlight as soon as the user makes any change.
        self._view_modified = False

        self._current_view: View | None = None
        self._views: list[View] = []
        # The view list is only needed to draw the dropdown, so it is
        # fetched the first time the menu opens rather than at startup.
        self._views_loaded: bool = False
        # When True, :meth:`refresh` skips its auto-apply-working-view
        # branch.  Toggled by :class:`_SuspendAutoApply` around save
        # operations so the manager-driven refresh during save_view
        # does not trigger a redundant page-0 refetch.
        self._suppress_auto_apply: bool = False
        self._ensuring_working_view: bool = False
        # True while :meth:`_apply_view` is pushing settings into the
        # widgets. Those widgets emit the same change signals a user edit
        # does, and echoing them back to the server would rewrite the
        # working view with what we just read from it.
        self._applying_view: bool = False

        # Per-section collapsed state for the dropdown headers ("My
        # views", "Shared views", "Default view"). Kept for the
        # lifetime of the selector, mirroring the frontend's
        # collapsible section headers.
        self._collapsed_sections: dict[str, bool] = {}

        self._dropdown_layout = None  # type: ignore[assignment]
        self._default_view_control = DefaultViewControl(self)

        super().__init__(
            populate_callback=self._populate_menu,
            icon="view_quilt",
            variant=AYButton.Variants.Surface,
            dropdown_variant=AYContainer.Variants.Popover,
            dropdown_margin=6,
            tooltip="Views",
            parent=parent,
        )
        self.setObjectName("AYViewSelector")
        self.setFixedSize(32, 32)

        # Applying a view, or a single user gesture, moves several widgets
        # at once. Coalesce the resulting saves into one round trip.
        # Built here rather than with the state above: parenting a QTimer
        # needs this object's base class to be initialised first.
        self._working_view_timer = QTimer(self)
        self._working_view_timer.setSingleShot(True)
        self._working_view_timer.setInterval(300)
        self._working_view_timer.timeout.connect(self._update_working_view)

        # Rebuild the menu contents each time it opens, since the view
        # list may change between openings.
        self.menu_opened.connect(self._rebuild_menu)

        # Refresh when the manager changes.
        self._manager.views_changed.connect(self._on_manager_changed)
        self._manager.project_changed.connect(self._on_project_changed)
        self._connect_modified_state_sources()

        # Forward binding errors via the public ``binding_error`` signal so
        # hosts can surface them.  Overrides any pre-existing
        # ``on_error`` hook (the caller can wrap it themselves to chain).
        if self._bindings.on_error is None:
            self._bindings.on_error = self._on_binding_error

        self.refresh()
        # After refresh(), since it may apply a working view and set
        # its own "View: ..." tooltip — this call must have the final
        # say when there's no project, overriding that.
        self._update_enabled_for_project()

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

        # First open of the menu is what pays for the view list.
        self._ensure_views_listed()

        # The working view + "My views" + "Shared views" portion lives
        # in its own scrollable area, capped at _VIEWS_LIST_MAX_HEIGHT,
        # so a long view list scrolls instead of growing the dropdown
        # indefinitely — "Default view" and "Create new view…" stay
        # outside it, always visible.
        layout.addWidget(self._make_views_list_scroll_area())

        layout.addWidget(
            self._make_section_header("Default view", "default_view")
        )
        if not self._collapsed_sections.get("default_view"):
            layout.addWidget(self._make_default_view_row())
        layout.addWidget(self._make_separator())

        layout.addWidget(self._make_create_view_row())

        self.refresh_dropdown_size()

    def _make_views_list_scroll_area(self) -> AYScrollArea:
        """Build the scrollable working-view + "My views" + "Shared
        views" portion of the dropdown, capped at
        ``_VIEWS_LIST_MAX_HEIGHT``.
        """
        # A real, opaquely-painted Popover frame — same variant as the
        # dropdown and its rows — rather than a bare QWidget stylesheet
        # "background: transparent". The dropdown is a translucent
        # popup: a bare widget's "transparent" paints nothing of its
        # own, and any pixel none of its rows happen to cover (the
        # inter-row spacing, in particular) has nothing to fall back
        # to, so it stayed see-through — a visible darker gap/border
        # around the whole list. Painting Popover here directly makes
        # every pixel in the list opaque and correct, regardless of
        # what any translucent ancestor does or doesn't cover.
        scroll_content = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Popover_Square,
            layout_spacing=2,
            layout_margin=0,
        )

        # Current view row with inline reset button.
        scroll_content.add_widget(
            self._make_working_view_row(self._current_view)
        )
        scroll_content.add_widget(self._make_separator())

        # Exclude working view as it stored with private Visibility
        private_views = [
            v for v in self._views
            if v.visibility == Visibility.PRIVATE
               and not v.working
               and v.label != DEFAULT_VIEW_LABEL
        ]
        public_views = [
            v for v in self._views if v.visibility == Visibility.PUBLIC
        ]

        if private_views:
            scroll_content.add_widget(
                self._make_section_header("My views", "my_views")
            )
            if not self._collapsed_sections.get("my_views"):
                for view in private_views:
                    scroll_content.add_widget(self._make_row(view))

        if public_views:
            scroll_content.add_widget(
                self._make_section_header("Shared views", "shared_views")
            )
            if not self._collapsed_sections.get("shared_views"):
                for view in public_views:
                    scroll_content.add_widget(self._make_row(view))

        if not self._views:
            no_views_label = AYLabel("No saved views.", dim=True)
            # Match the left indent every row's own label gets from its
            # row's contents margins + the label's own inner margin
            # (2 + 6 = 8), since this one isn't wrapped in a row.
            no_views_label.setContentsMargins(8, 4, 8, 4)
            scroll_content.add_widget(no_views_label)

        scroll_area = AYScrollArea(
            scrollbar_variant=AYScrollArea.Variants.Transparent_Track
        )
        scroll_area.setWidget(scroll_content)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Natural content height, capped — lets the scroll area shrink
        # to fit a short list instead of always reserving max height.
        scroll_content.adjustSize()
        content_height = scroll_content.sizeHint().height()
        scroll_area.setFixedHeight(
            min(content_height, _VIEWS_LIST_MAX_HEIGHT)
        )
        return scroll_area

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def _style_row(self, row: AYContainer) -> None:
        """Apply the shared row inset/height to a dropdown list row.

        Uses the row's *layout* contents margins rather than the row
        widget's own ``setContentsMargins`` — ``AYFrame`` paints its own
        background using ``frameRect()`` (== ``contentsRect()``), which
        is inset by the widget's own contents margins. Insetting the
        widget itself would shrink the row's background fill by the
        same amount as its children, leaving the fill and a trailing
        action button flush against each other with no visible gap.
        The layout's margins only affect child placement, so this
        keeps the row's fill full-bleed while still inserting real
        padding around its children.
        """
        row.layout().setContentsMargins(4, 4, 8, 4)
        row.setMinimumHeight(_ROW_MIN_HEIGHT)

    def _make_separator(self) -> QFrame:
        """Return a subtle 1px divider line (outline-variant color)."""
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("QFrame { border-top: 1px solid #41474d; }")
        return sep

    def _make_section_header(self, title: str, section_key: str) -> _SectionHeader:
        """Return a clickable, collapsible section header."""
        return _SectionHeader(
            title,
            collapsed=bool(self._collapsed_sections.get(section_key)),
            on_toggle=lambda key=section_key: self._on_section_toggle(key),
        )

    def _on_section_toggle(self, section_key: str) -> None:
        """Flip a section's collapsed state and redraw the dropdown."""
        self._collapsed_sections[section_key] = not self._collapsed_sections.get(
            section_key
        )
        self._rebuild_menu()

    def _make_working_view_row(self, view: View) -> AYContainer:
        """Build the current-view row with an inline reset button.

        The row itself is the click target and carries the selected
        highlight — the label is plain text, not a button — so the
        label and the reset button read as one merged control, and
        clicking anywhere in the row (including the margins around the
        reset button) selects the working view. Matches the frontend,
        where ``.selected`` is applied to the whole row element.
        """
        is_current_view_is_working_view = view is not None and view.working
        is_selected = self._view_modified or is_current_view_is_working_view

        row = _ClickableRow(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Popover,
            layout_spacing=4,
            layout_margin=0,
            hover_enabled=True,
            on_click=self._on_working_view_clicked,
        )
        self._style_row(row)
        row.set_selected(is_selected)

        label = AYLabel("Working view")
        label.setContentsMargins(6, 0, 0, 0)
        row.add_widget(label, stretch=1)

        reset_btn = AYButton(
            icon="restart_alt",
            variant=AYButton.Variants.Row_Action,
            tooltip="Reset to default",
        )
        reset_btn.clicked.connect(self._on_reset_clicked)
        row.add_widget(reset_btn)

        RowHoverTracker(row).watch(reset_btn)

        return row

    def _make_view_label(self, view: View) -> AYLabel:
        label = AYLabel(view.label or "(unnamed view)")
        label.setContentsMargins(6, 0, 0, 0)
        return label

    def _make_save_btn(self, view: View, row: AYContainer) -> AYButton:
        """Build the save button — same size as any other row action.

        It's the plain ``Row_Action`` variant, not a bespoke bigger
        one: the "modified" highlight is just its ``checked`` state
        (like the filter chips and other checkable buttons elsewhere)
        turning it primary-blue, the same mechanism, not a special
        button.
        """
        is_modified = bool(
            self._current_view
            and view.id == self._current_view.id
            and self._view_modified
        )
        btn = AYButton(
            icon="save",
            variant=AYButton.Variants.Row_Action,
            checkable=True,
            tooltip="Save view settings from current view",
        )
        btn.setChecked(is_modified)
        btn.clicked.connect(
            lambda _checked=False, v=view: self._on_view_save_clicked(v)
        )

        if not is_modified:
            sp = btn.sizePolicy()
            sp.setRetainSizeWhenHidden(True)
            btn.setSizePolicy(sp)
            btn.setVisible(False)
            row.installEventFilter(_HoverReveal(btn, row))

        return btn

    def _make_edit_btn(self, view: View) -> AYButton:
        btn = AYButton(
            icon="more_horiz",
            variant=AYButton.Variants.Row_Action,
            tooltip="Edit view",
        )
        btn.clicked.connect(
            lambda _checked=False, v=view: self._on_edit_clicked(v)
        )
        return btn

    def _make_row(self, view: View) -> AYContainer:
        """Build one selectable row for *view*."""
        not_modified = (
                self._current_view
                and view.id == self._current_view.id
                and not self._view_modified
        )

        row = _ClickableRow(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Popover,
            layout_spacing=4,
            layout_margin=0,
            hover_enabled=True,
            on_click=lambda v=view: self._on_view_selected(v),
        )
        self._style_row(row)
        row.set_selected(bool(not_modified))

        row.add_widget(self._make_view_label(view), stretch=1)
        hover_watched = []

        if view.can_edit(self._current_user, self._user_access):
            if not not_modified:
                save_btn = self._make_save_btn(view, row)
                row.add_widget(save_btn)
                hover_watched.append(save_btn)
            edit_btn = self._make_edit_btn(view)
            row.add_widget(edit_btn)
            hover_watched.append(edit_btn)

        RowHoverTracker(row).watch(*hover_watched)

        return row

    def _make_default_view_row(self) -> AYContainer:
        """Build a row for the default view."""
        return self._default_view_control.build_row()

    def _make_create_view_row(self) -> AYContainer:
        """Build the "Create new view…" row.

        Wrapped the same way as every other row (a hover-enabled
        Popover frame whose click and hover the row itself owns) so
        its look matches the rest of the dropdown instead of the plain
        Text-button gray. No :class:`RowHoverTracker` here: unlike the
        other rows, this one has no interactive child button to steal
        Enter/Leave events, so the frame drawer's own ``underMouse()``
        fallback (see ``hover_enabled``) already keeps it highlighted.
        """
        row = _ClickableRow(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Popover,
            layout_spacing=4,
            layout_margin=0,
            hover_enabled=True,
            on_click=self._on_create_clicked,
        )
        self._style_row(row)

        label = AYLabel("Create new view…", icon="add")
        label.setContentsMargins(6, 0, 0, 0)
        row.add_widget(label, stretch=1)
        return row

    def _on_binding_error(self, stage: str, exc: BaseException) -> None:
        """Forward a :class:`ViewBindings` error via :attr:`binding_error`."""
        self.binding_error.emit(stage, str(exc) or exc.__class__.__name__)

    def _connect_modified_state_sources(self) -> None:
        """Wire widget signals that mark the view as dirty."""
        self._bindings.filter_bar.filters_changed.connect(self._mark_modified)
        self._bindings.table_view.column_state_changed.connect(self._mark_modified)
        self._bindings.table_view.header().sortIndicatorChanged.connect(
            self._mark_modified
        )

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
        """Re-resolve the working view and drop the cached view list.

        Restoring the user's last state only needs the working view,
        which has its own endpoint. The dropdown is not on screen yet, so
        listing the rest - and each one's settings - waits until the menu
        is opened; see :meth:`_ensure_views_listed`.
        """
        self._views = []
        self._views_loaded = False

        working = self._ensure_working_view_exists()
        if (
            working is not None
            and self._current_view is None
            and not self._suppress_auto_apply
        ):
            self._apply_view(working, emit=True)
            return

    def _ensure_views_listed(self) -> None:
        """Fetch the view list on first use, then keep it until refresh."""
        if self._views_loaded:
            return
        try:
            self._views = list(self._manager.list_views(self._view_type))
        except Exception:
            log.exception("Failed to list views for %r", self._view_type)
            self._views = []
        self._views_loaded = True

    def current_view(self) -> View | None:
        """Return the currently active view, or ``None``."""
        return self._current_view

    def notify_view_modified(self, *_args) -> None:
        """Mark the view as modified after a UI settings change.

        Consumer code may connect custom widgets here when they affect
        :meth:`ViewBindings.capture` but are not part of the built-in
        table/filter stack.
        """
        self._mark_modified()

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
        editable = View.from_payload(view.to_payload())
        editable.settings = self._bindings.capture()
        usernames_and_groups = self._get_usernames_and_groups()
        editor = AYViewEditor(
            editable,
            current_user=self._current_user,
            allow_studio_scope=self._allow_studio_scope,
            current_project=self._current_project_name(),
            usernames_and_groups=usernames_and_groups,
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
        usernames_and_groups = self._get_usernames_and_groups()
        editor = AYViewEditor(
            new_view,
            current_user=self._current_user,
            allow_studio_scope=self._allow_studio_scope,
            current_project=self._current_project_name(),
            usernames_and_groups=usernames_and_groups,
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
            working = self._manager.get_working_view(self._view_type)
            if working:
                self._current_view = working
        try:
            self._manager.delete_view(view.id)
        except Exception:
            log.exception("Failed to delete view %r", view.id)
            return
        self.view_deleted.emit(view.id)
        self._apply_view(self._current_view, emit=True)

    def _on_reset_clicked(self) -> None:
        """Reset the current view to the default view for the current scope."""
        ctrl = self._default_view_control

        if ctrl.project_default_view:
            ctrl.load_project_default_view()
            return

        if ctrl.studio_default_view:
            ctrl.load_studio_default_view()
            return

        if ctrl.make_default_view_settings:
            ctrl.make_default_view_settings()
            return

        self.emit_default_view_message(
            "No default view configured.",
            False,
        )

    def _on_manager_changed(self, view_type: str) -> None:
        """Refresh when the manager signals a change for our type."""
        if view_type == self._view_type:
            self.refresh()

    def _on_project_changed(self, project_name: str) -> None:
        """Reset state and refresh when the manager switches project.
        clear active view belongs to the old project so the new
        project's working view can be auto-applied.
        """
        self._current_view = None
        self._clear_modified()
        self.refresh()
        self._update_enabled_for_project()

    def _update_enabled_for_project(self) -> None:
        """Enable the Views button only while a project is active.

        With no project there is nothing sensible for a view to apply
        to, so opening the dropdown wouldn't do anything useful — keep
        it disabled instead. Called after :meth:`refresh`, since that
        may apply a working view and set its own "View: ..." tooltip;
        this must have the final say when there's no project.
        """
        has_project = bool(self._current_project_name())
        self.setEnabled(has_project)
        if not has_project:
            self.setToolTip("Views (select a project first)")

    def _get_usernames_and_groups(self) -> dict[str, list]:
        """Fetch active project users and return unique usernames."""
        project_name = getattr(self._manager, "project_name", "")
        if not project_name:
            return {"users": [], "groups": []}
        users = []
        groups = []
        try:
            users = ayon_api.get_users(project_name=project_name) or []
        except Exception:  # noqa: BLE001
            log.exception("Failed to fetch users for project %r",
                          project_name)

        try:
            group_data = ayon_api.get(f"/accessGroups/{project_name}").data
            groups = [group.get('name') for group in group_data]
        except Exception:
            log.exception("Failed to fetch project groups")

        users_data: list[dict[str, str]] = []
        seen: set[str] = set()
        for user in users:
            if not isinstance(user, dict):
                continue
            if not bool(user.get("active", False)):
                continue
            name = str(user.get("name") or "").strip()
            if not name or name in seen or name == self._current_user:
                continue

            full_name = user.get("ownAttrib", {}).get("fullName", "") or name

            seen.add(name)
            users_data.append({"name": name, "fullName": full_name})
        return {"users": users_data, "groups": groups}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _close_menu(self) -> None:
        """Close the dropdown popup if currently open."""
        try:
            self._dropdown.close()
        except Exception:
            pass

    def refresh_dropdown_size(self) -> None:
        """Resize the dropdown popup to fit its current content.

        Call after any change to the dropdown's contents (a full
        rebuild, or swapping a single row/pill's children in place):
        rebuilding a widget's children leaves stale cached size hints
        on its ancestors, so a plain ``adjustSize()`` alone can settle
        on a size that no longer fits — e.g. clipping the label text on
        a default-view pill after it switches between its "unset" and
        "active" (wider) look. Invalidating the layout chain first
        forces every ancestor to recompute before the popup resizes.
        """
        layout = self._dropdown_layout
        if layout is not None:
            layout.invalidate()
            layout.activate()
        self._dropdown.updateGeometry()
        self._dropdown.adjustSize()

    def emit_default_view_message(self, message: str, success: bool) -> None:
        """Emit default-view feedback for host UIs.

        Hosts can map this to the same toast presentation used by loader
        action results.
        """
        self.default_view_message.emit(message, success)

    def _current_project_name(self) -> str:
        """Return the manager's current project name when available."""
        project_name = getattr(self._manager, "project_name", "")
        return str(project_name or "")

    def _ensure_working_view_exists(self) -> View | None:
        """Return the current working view, creating one when missing."""
        if self._ensuring_working_view or self._current_view is not None:
            return None

        try:
            existing = self._manager.get_working_view(self._view_type)
        except Exception:
            log.exception(
                "Failed to resolve working view for %r", self._view_type
            )
            existing = None
        if existing is not None:
            return existing

        project_name = getattr(self._manager, "project_name", None)
        if project_name is not None and not str(project_name or ""):
            return None

        working_view = View(
            label="Working",
            settings=self._bindings.capture(),
            working=True,
            visibility=Visibility.PRIVATE,
            view_type=self._view_type,
            owner=self._current_user,
            scope=Scope.PROJECT
        )

        self._ensuring_working_view = True
        try:
            with self._suspend_auto_apply():
                self._manager.set_working_view(working_view)
        except Exception:
            log.exception(
                "Failed to create initial working view for %r",
                self._view_type,
            )
            return None
        finally:
            self._ensuring_working_view = False

        refreshed_working = self._manager.get_working_view(self._view_type)
        if refreshed_working is not None:
            return refreshed_working
        return working_view

    def _mark_modified(self, *_args) -> None:
        """Set the dirty flag on the first UI change after a view is applied.
            and cleared by applying, saving, or resetting a view.
        """
        if self._applying_view:
            # Our own writes bouncing back off the widgets.
            return

        self._working_view_timer.start()

        if self._view_modified:
            return

        self._view_modified = True

        if self._current_view and not self._current_view.working:
            self.set_variant(AYButton.Variants.Filled)

        if self._current_view:
            view_name = self._current_view.label or self._current_view.id
            self.view_modified.emit(view_name, True)

    def _apply_view(self, view: View, emit: bool) -> None:
        """Apply *view* to the bindings and clear the dirty flag.

        Default views are applied onto the working-view context, so edits
        continue against the working view.
        """
        is_default_view = (
            not view.working
            and view.label == DEFAULT_VIEW_LABEL
        )

        target_view = view
        if is_default_view:
            try:
                working_view = self._manager.get_working_view(self._view_type)
            except Exception:
                log.exception(
                    "Failed to resolve working view for %r", self._view_type
                )
                return
            target_view = working_view
            self._close_menu()

        # A view picked from the dropdown carries only listing metadata;
        # this is where its settings are actually needed.
        view = self._manager.load_view(view)
        if target_view is not None and target_view.id == view.id:
            target_view = view
        self._current_view = target_view

        self._applying_view = True
        try:
            self._bindings.apply(view.settings)
        except Exception:
            log.exception("Failed to apply view %r", view.id)
            return
        finally:
            self._applying_view = False
            # Nothing was modified, so drop any save this apply queued.
            self._working_view_timer.stop()

        self.setToolTip(f"View: {self._current_view.label}")
        self._clear_modified()

        if emit:
            self.view_applied.emit(view)

    def _on_view_save_clicked(self, view: View) -> None:
        self._close_menu()
        view.settings = self._bindings.capture()
        with self._suspend_auto_apply():
            saved = self._save_view(view)
        if saved is not None:
            self._apply_view(saved, emit=True)

    def _clear_modified(self) -> None:
        """Clear the dirty flag and restore the default button variant."""
        if not self._view_modified:
            return
        self._view_modified = False
        self.set_variant(AYButton.Variants.Surface)
        if self._current_view:
            view_name = self._current_view.label or self._current_view.id
            self.view_modified.emit(view_name, False)

    def _save_view(self, view: View) -> View | None:
        """
        This called when new view is created or existing view is updated.
        Persist *view* and return the manager's response."""
        try:
            saved = self._manager.save_view(view)
        except Exception:
            log.exception("Failed to save view %r", view.label)
            return None
        self.view_saved.emit(saved)
        return saved

    def _on_working_view_clicked(self, _checked: bool = False) -> None:
        try:
            working_view = self._manager.get_working_view(self._view_type)
        except Exception:
            log.exception(
                "Failed to resolve working view for %r", self._view_type
            )
            return

        if not working_view:
            return

        self._apply_view(working_view, emit=True)

        # Change views icon state to normal
        self.set_variant(AYButton.Variants.Surface)
        self._close_menu()

    def hideEvent(self, event) -> None:
        """Flush a pending working-view save before going away.

        The debounce would otherwise drop the last few hundred
        milliseconds of edits when the window closes.
        """
        if self._working_view_timer.isActive():
            self._working_view_timer.stop()
            self._update_working_view()
        super().hideEvent(event)

    def _update_working_view(self) -> None:
        """Persist the live widget state onto the working view."""
        # The applied view is normally the working view already, so going
        # back to the server for it would just re-read what we hold.
        working_view = self._current_view
        if working_view is None or not working_view.working:
            try:
                working_view = self._manager.get_working_view(self._view_type)
            except Exception:
                log.exception(
                    "Failed to resolve working view for %r", self._view_type
                )
                return
        if working_view is None:
            return
        working_view.settings = self._bindings.capture()
        with self._suspend_auto_apply():
            self._manager.set_working_view(working_view)

    def get_default_views(self):
        """Return the current default views from the default view control."""
        return (
            self._default_view_control.studio_default_view,
            self._default_view_control.project_default_view,
        )

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
            visibility=Visibility.PUBLIC,
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
        selector.view_modified.connect(
            lambda name, modified: print(
                f"[demo]  view state for {name!r}: "
                f"{'modified' if modified else 'clean'}"
            )
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
