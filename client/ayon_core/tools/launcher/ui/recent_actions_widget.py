from collections import namedtuple

from qtpy import QtWidgets, QtCore

from ayon_core.lib import Logger
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.utils.delegates import pretty_timestamp
from ayon_core.tools.utils.lib import RefreshThread
from ayon_core.ui.components import AYButton, AYLabel, AYMenu
from ayon_core.ui.components.dropdown import AYDropdownPopup
from ayon_core.ui.components.layouts import AYVBoxLayout, AYHBoxLayout
from ayon_core.ui.components.scroll_area import AYScrollArea

# Material Symbols has a single star glyph, filled and outlined are the
# same codepoint drawn with a different value of the font's FILL axis. The
# color makes the difference obvious even where that axis is unavailable.
_FAVORITE_COLOR = "#E9B949"
# Actions are not required to define an icon. A neutral one keeps the
# rows aligned and still reads as something that can be run.
_DEFAULT_ICON = MaterialSymbolsIcon("bolt")
_REMOVE_ICON = MaterialSymbolsIcon("delete")
# Entries recorded before the type icons were kept, or of a type without one.
_DEFAULT_FOLDER_ICON = "folder"
_DEFAULT_TASK_ICON = "task_alt"
_WORKFILE_ICON = "description"
_BREADCRUMB_ICON_SIZE = 14

log = Logger.get_logger("RecentActionsWidget")


def _get_icon(icon_def):
    """Build a QIcon from a stored icon definition.

    Icon definitions are stored with the history, so they may have been
    written by a version that described icons differently. A stale
    definition must never take the launcher down with it.

    Args:
        icon_def (Optional[dict[str, str]]): Stored icon definition.

    Returns:
        QtGui.QIcon: Icon to draw. Entries without an icon, and entries
            whose icon cannot be built, fall back to a default one.

    """
    icon = None
    if icon_def:
        try:
            # 'default=None' instead of the blank icon that would be
            # returned otherwise, so that a definition which cannot be
            # resolved is told apart from one that simply is not there.
            icon = get_qt_icon(icon_def, default=None)
        except Exception:
            log.warning(
                "Failed to create icon from %s", icon_def, exc_info=True
            )
    if icon is None:
        icon = get_qt_icon(_DEFAULT_ICON)
    return icon


_SEPARATOR = " \u203a "


def _build_full_context(action_item) -> str:
    """Build the complete context: project › folder path › task › workfile.

    The item already carries the resolved context, pieces that do not exist
    anymore are simply missing and get skipped.

    Args:
        action_item (RecentActionItem): Recent action item.

    Returns:
        str: Full context the action was triggered in.

    """
    parts = [
        action_item.project_name,
        action_item.folder_path,
        action_item.task_name,
        action_item.workfile_name,
    ]
    return _SEPARATOR.join([part for part in parts if part])


_Segment = namedtuple("_Segment", ("text", "icon", "color"))


def _build_breadcrumb(action_item):
    """Build the short context shown in a row: code > folder > task > file.

    The project is reduced to its code (falling back to its full name for
    an entry recorded before the code was kept) and the folder to its name,
    always shown - not just when it differs from the project being
    browsed, which used to make the row's context shift shape depending on
    what else was open. The whole context stays available through
    :func:`_build_full_context`, used for the tooltips.

    Args:
        action_item (RecentActionItem): Recent action item.

    Returns:
        list[_Segment]: Text, type icon and icon color of each part.

    """
    folder_path = (action_item.folder_path or "").rstrip("/")
    folder_name = folder_path.rsplit("/", 1)[-1]
    default_color = get_default_entity_icon_color()
    segments = []
    project_text = action_item.project_code or action_item.project_name
    if project_text:
        segments.append(_Segment(project_text, None, None))
    if folder_name:
        segments.append(_Segment(
            folder_name, action_item.folder_icon or _DEFAULT_FOLDER_ICON,
            default_color,
        ))
    if action_item.task_name:
        segments.append(_Segment(
            action_item.task_name,
            action_item.task_icon or _DEFAULT_TASK_ICON,
            action_item.task_color or default_color,
        ))
    if action_item.workfile_name:
        # Just an icon: enough to show a workfile was part of the context
        # too, without spelling out its (often long) filename here as
        # well - that stays one hover away, in the full context tooltip.
        segments.append(_Segment("", _WORKFILE_ICON, default_color))
    return segments


class _BreadcrumbSegmentLabel(AYLabel):
    """An 'AYLabel' with a couple of extra px of reserved width.

    'AYLabel.sizeHint()' measures text with 'QFontMetrics.boundingRect()',
    while 'elidedText()' (used to actually elide it) measures the wider
    'horizontalAdvance()' - close enough that it rarely mattered when a
    breadcrumb was one label getting far more room than its own sizeHint,
    but each segment here is sized to exactly its sizeHint, so that couple
    of px is now the difference between showing a short segment in full
    and having it chopped down to barely more than an ellipsis.
    """

    _WIDTH_MARGIN = 3

    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        return QtCore.QSize(hint.width() + self._WIDTH_MARGIN, hint.height())


class _BreadcrumbWidget(QtWidgets.QWidget):
    """Short context of an entry, each part with the icon of its type.

    Every part elides on its own, so a long name gives way instead of
    pushing the row's buttons out of view.
    """

    def __init__(self, segments, parent=None):
        super().__init__(parent)
        layout = AYHBoxLayout(self, margin=0, spacing=4)
        for index, segment in enumerate(segments):
            if index:
                layout.addWidget(AYLabel(
                    _SEPARATOR.strip(), dim=True, parent=self
                ))
            label = _BreadcrumbSegmentLabel(
                # PySide resolves 'QLabel("")' to the wrong constructor
                # overload, colliding with the 'parent' kwarg below - an
                # icon-only segment (the workfile marker) has no text
                # positional to pass in the first place, so it is skipped
                # rather than passed as an empty string.
                *([segment.text] if segment.text else []),
                dim=True,
                elide_mode=QtCore.Qt.ElideMiddle,
                icon=segment.icon or "",
                icon_color=segment.color or "",
                icon_size=_BREADCRUMB_ICON_SIZE,
                icon_text_spacing=4,
                parent=self,
            )
            # 'flexible' (Ignored) is not used here: it drops the label's
            # own full-text width from the layout's growth calculation
            # entirely, so with several segments plus the trailing stretch
            # below, every segment would get squeezed to its bare minimum
            # first and hand all the real room to the stretch instead.
            # 'Preferred' keeps that full width as what the segment tries
            # to reach - and only shrinks it, sparing the fixed-size
            # favorite/go-to buttons, once the row is actually too tight.
            label.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Preferred,
            )
            # The floor it can still shrink to, so a segment never
            # disappears completely. Only an icon actually shown (not the
            # project code) reserves its own width - reserving one
            # unconditionally puffed up icon-less, already-short segments
            # (like the project code) with dead space they never used.
            label.setMinimumWidth(
                (_BREADCRUMB_ICON_SIZE if segment.icon else 0)
                + (24 if segment.text else 0)
            )
            layout.addWidget(label)
        layout.addStretch(1)


class _RecentActionRow(QtWidgets.QWidget):
    """Single row: icon, label/breadcrumb, timestamp, favorite and replay."""

    navigate_requested = QtCore.Signal(str)
    replay_requested = QtCore.Signal(str)
    favorite_toggled = QtCore.Signal(str, bool)
    context_menu_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(
        self,
        action_item,
        breadcrumb,
        timestamp_label,
        parent=None,
        full_context=None,
    ):
        super().__init__(parent)
        self._record_id = action_item.record_id
        self.setCursor(QtCore.Qt.PointingHandCursor)
        # The row is clickable, so it gets a hover state from the stylesheet
        # like a button does - which needs the widget to paint its own
        # background.
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)

        label = action_item.label
        # The label shows the short form, hovering gives the whole thing.
        full_context = full_context or _SEPARATOR.join(
            [segment.text for segment in breadcrumb if segment.text]
        )
        if full_context:
            tooltip = f"Run: {label}\n{full_context}"
            self.setToolTip(tooltip)

        icon_label = QtWidgets.QLabel(self)
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(QtCore.Qt.AlignCenter | QtCore.Qt.AlignVCenter)
        icon_label.setPixmap(_get_icon(action_item.icon).pixmap(28, 28))

        text_label = AYLabel(label, bold=True, parent=self)
        text_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)

        breadcrumb_widget = _BreadcrumbWidget(breadcrumb, self)
        breadcrumb_widget.setObjectName("RecentActionBreadcrumb")
        breadcrumb_widget.setVisible(bool(breadcrumb))

        timestamp_widget = AYLabel(
            timestamp_label, dim=True, rel_text_size=-1, parent=self,
        )
        timestamp_widget.setAlignment(
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter
        )
        timestamp_widget.setObjectName("RecentActionTimestamp")
        # Only shown while hovering the row, it is also in the tooltip.
        timestamp_widget.setVisible(False)
        self._timestamp_widget = timestamp_widget
        self._has_timestamp = bool(timestamp_label)

        favorite = action_item.favorite
        favorite_btn = AYButton(
            variant=AYButton.Variants.Surface,
            icon="star", icon_size=18,
            icon_fill=favorite,
            icon_color=_FAVORITE_COLOR if favorite else None,
            checkable=True,
            tooltip=(
                "Unpin from the top of the list"
                if favorite
                else "Pin to the top of the list"
            ),
            parent=self,
        )
        favorite_btn.setChecked(favorite)
        favorite_btn.setCursor(QtCore.Qt.PointingHandCursor)
        favorite_btn.setObjectName("RecentFavoriteBtn")

        go_to_btn = AYButton(
            variant=AYButton.Variants.Surface,
            icon="my_location", icon_size=18,
            tooltip=f"Go to: {full_context}",
            parent=self,
        )
        go_to_btn.setCursor(QtCore.Qt.PointingHandCursor)

        top_row = AYHBoxLayout(margin=0, spacing=8)
        top_row.addWidget(text_label, 1)
        top_row.addWidget(timestamp_widget, 0, QtCore.Qt.AlignVCenter)

        text_col = AYVBoxLayout(margin=0, spacing=1)
        text_col.addLayout(top_row)
        text_col.addWidget(breadcrumb_widget)

        row_layout = AYHBoxLayout(self, margin=4, spacing=4)
        row_layout.addWidget(icon_label, 0, QtCore.Qt.AlignVCenter)
        row_layout.addLayout(text_col, 1)
        row_layout.addWidget(go_to_btn, 0)
        row_layout.addWidget(favorite_btn, 0)

        self._favorite_btn = favorite_btn
        self._play_btn = go_to_btn
        favorite_btn.clicked.connect(self._on_favorite_clicked)
        go_to_btn.clicked.connect(self._on_go_to_clicked)
        self.setObjectName("RecentActionRow")

    def enterEvent(self, event):
        super().enterEvent(event)
        self._timestamp_widget.setVisible(self._has_timestamp)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._timestamp_widget.setVisible(False)

    def _on_go_to_clicked(self):
        self.navigate_requested.emit(self._record_id)

    def _on_favorite_clicked(self):
        self.favorite_toggled.emit(
            self._record_id, self._favorite_btn.isChecked()
        )

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            child = self.childAt(event.pos())
            if not isinstance(child, QtWidgets.QPushButton):
                self.replay_requested.emit(self._record_id)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.RightButton:
            # A right click, not 'contextMenuEvent' - the popup this row
            # lives in is a 'Qt::Popup' window, and Windows does not
            # reliably synthesize a native context-menu message for a
            # child of one, so 'contextMenuEvent' never fires here. Mouse
            # button events are still delivered normally, so the same
            # right click is caught here instead.
            self.context_menu_requested.emit(
                self._record_id, event.globalPos()
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)


class RecentActionsPopup(AYDropdownPopup):
    """Popup listing recent actions, anchored below the trigger button."""

    def __init__(self, controller, parent=None):
        super().__init__(
            parent, variant=AYDropdownPopup.Variants.Low_Framed_Thin
        )
        self.setObjectName("RecentActionsPopup")
        self._controller = controller
        self._rows = []
        self._refresh_thread = None
        self._refresh_again = False
        self._anchor_widget = None

        scroll_area = AYScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        rows_container = QtWidgets.QWidget(scroll_area)
        rows_container.setObjectName("RecentActionsContainer")
        self._rows_layout = AYVBoxLayout(rows_container, margin=4, spacing=2)

        self._empty_label = AYLabel(
            "Loading recent actions...", dim=True, parent=rows_container
        )
        self._empty_label.setAlignment(QtCore.Qt.AlignCenter)
        self._empty_label.setContentsMargins(12, 8, 12, 8)
        self._rows_layout.addWidget(self._empty_label)
        self._rows_layout.addStretch(1)

        scroll_area.setWidget(rows_container)
        self._scroll_area = scroll_area
        self._rows_container = rows_container

        main_layout = AYVBoxLayout(self, margin=0, spacing=0)
        main_layout.addWidget(scroll_area, 1)

        controller.register_event_callback(
            "recent_action.unavailable", self._on_recent_action_unavailable
        )

    def refresh(self):
        """Show what is loaded and reload the history in the background.

        Rendering never waits for the server - previously loaded items are
        shown straight away and replaced once the worker thread delivers
        fresh ones.
        """
        self._rebuild_rows(self._controller.get_recent_action_items())
        self._start_refresh_thread()

    def _start_refresh_thread(self):
        if self._refresh_thread is not None:
            return

        refresh_thread = RefreshThread(
            "recent_actions",
            self._controller.refresh_recent_action_items,
        )
        refresh_thread.refresh_finished.connect(self._on_refresh_finished)
        self._refresh_thread = refresh_thread
        refresh_thread.start()

    def _on_refresh_finished(self):
        # 'RefreshThread' logs its own traceback, a failed refresh simply
        # leaves the previously prepared items on screen.
        self._refresh_thread = None
        self._rebuild_rows(self._controller.get_recent_action_items())

        if self.isVisible() and self._anchor_widget is not None:
            self._place(self._anchor_widget)

        if self._refresh_again:
            self._refresh_again = False
            self._start_refresh_thread()

    def show_near(self, widget):
        self._anchor_widget = widget
        self.refresh()
        self._place(widget)
        self.show()

    def _place(self, widget):
        """Size the popup to its rows and right-align it below 'widget'.

        Long context paths elide, so rows never need more than a fixed
        width. Height follows the rows up to the screen height, beyond
        which the scroll area takes over.
        """
        screen = widget.screen().availableGeometry()
        width = max(320, int(widget.window().width() / 1.5))
        # 'QScrollArea.sizeHint()' is capped and ignores its content, so
        # measure the rows instead.
        height = min(
            self._rows_container.sizeHint().height(), screen.height()
        )
        self.setFixedSize(width, height)

        pos = widget.mapToGlobal(
            QtCore.QPoint(widget.width() - width, widget.height() + 2)
        )
        self.move(
            max(screen.left(), min(pos.x(), screen.right() + 1 - width)),
            max(screen.top(), min(pos.y(), screen.bottom() + 1 - height)),
        )

    def _rebuild_rows(self, items):
        for row in self._rows:
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        self._rows = []
        while self._rows_layout.count() > 1:
            item = self._rows_layout.takeAt(1)
            if item and item.widget():
                item.widget().deleteLater()

        if items:
            self._empty_label.setVisible(False)
        else:
            self._empty_label.setText(
                "No recent actions..."
                if self._controller.are_recent_action_items_loaded()
                else "Loading recent actions..."
            )
            self._empty_label.setVisible(True)
        previous_favorite = None
        for action_item in items:
            # Favorites are listed first, split off from the rest.
            if previous_favorite and not action_item.favorite:
                self._add_row_widget(self._build_separator())
            previous_favorite = action_item.favorite

            row = _RecentActionRow(
                action_item,
                _build_breadcrumb(action_item),
                pretty_timestamp(action_item.timestamp) or "",
                self._rows_container,
                full_context=_build_full_context(action_item),
            )
            row.navigate_requested.connect(self._on_navigate)
            row.replay_requested.connect(self._on_replay)
            row.favorite_toggled.connect(self._on_favorite_toggled)
            row.context_menu_requested.connect(self._on_context_menu)
            self._add_row_widget(row)
            self._rows.append(row)
        self._rows_layout.addStretch(1)

    def _add_row_widget(self, widget):
        """Add a widget to the list and let it count towards its size.

        A widget added while the popup is still hidden stays hidden until
        the popup is shown, and the layout skips hidden widgets when asked
        how much room it needs - which would leave the popup sized for
        nothing at all on the first open.
        """
        self._rows_layout.addWidget(widget)
        widget.show()

    def _build_separator(self):
        """Rule between the pinned entries and the rest.

        A plain frame rather than an 'AYFrame', so that the launcher
        stylesheet is what decides how the rule looks.
        """
        separator = QtWidgets.QFrame(self._rows_container)
        separator.setObjectName("RecentActionsFavoriteSeparator")
        separator.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        separator.setFixedHeight(9)
        return separator

    def hideEvent(self, event):
        super().hideEvent(event)
        self._anchor_widget = None

    def _on_navigate(self, record_id):
        self._controller.apply_recent_action_context(record_id)
        self.hide()

    def _on_replay(self, record_id):
        self._controller.trigger_recent_action(record_id)
        self.hide()

    def _on_favorite_toggled(self, record_id, favorite):
        self._controller.set_recent_action_favorite(record_id, favorite)
        # The entry moves to the other side of the separator.
        self._reload_rows()

    def _on_context_menu(self, record_id, global_pos):
        """Show the menu for a row, owned by the popup rather than the row.

        Built parented to 'self' (the popup) and shown via '.popup()'
        rather than the blocking '.exec_()' - a right click reaches here
        directly from the row's own 'mouseReleaseEvent' (a direct signal
        connection), so blocking here would nest a whole event loop
        inside that handler; a refresh finishing in it can rebuild the
        row list and delete the very row still on the call stack once
        that loop returns. Parenting 'AYMenu' inside an already-open
        popup used to crash the tool - or leave its hover silently dead -
        both since fixed at the source (AYONStyle's own window-flag and
        style-hint handling), so there is no longer any reason to keep it
        unparented here. 'WA_DeleteOnClose' cleans it up once it closes,
        a fresh one is built on every right click.
        """
        menu = AYMenu(self)
        menu.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
        remove_action = menu.addAction(
            get_qt_icon(_REMOVE_ICON), "Remove from history"
        )
        remove_action.triggered.connect(
            lambda: self._on_remove(record_id)
        )
        menu.popup(global_pos)

    def _on_remove(self, record_id):
        self._controller.remove_recent_action(record_id)
        self._reload_rows()

    def _reload_rows(self):
        """Show the history as it is now and resize for what is left."""
        self._rebuild_rows(self._controller.get_recent_action_items())
        if self.isVisible() and self._anchor_widget is not None:
            self._place(self._anchor_widget)

    def _on_recent_action_unavailable(self, event):
        # The entry was dropped from the history, take it off screen too.
        if self.isVisible():
            self._reload_rows()


class RecentActionsButton(AYButton):
    """Icon-only button that shows/hides the recent-actions popup."""

    def __init__(self, controller, parent=None):
        super().__init__(
            icon="bookmark",
            variant=AYButton.Variants.Surface,
            tooltip="Recent Actions",
            parent=parent,
        )
        self.setObjectName("RecentActionsButton")
        self._popup = RecentActionsPopup(controller, self)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self):
        if self._popup.isVisible():
            self._popup.hide()
        else:
            self._popup.show_near(self)
