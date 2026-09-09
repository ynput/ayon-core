"""AYToolTip: a styled tooltip popup used by all AYON widgets.

Qt renders every native tooltip through a single, reused ``QLabel`` that
lives outside the widget hierarchy and always falls back to
``QApplication.style()`` - a widget calling ``setStyle(get_ayon_style())``
on itself never reaches it, so native tooltips can't be themed that way.

Rather than fight that singleton, AYON widgets swallow the native
``QEvent.ToolTip`` event (see ``AYONStyle.eventFilter``) and show this
widget instead - a real widget we build and own, styled the same way as
any other AYON component: an :class:`AYContainer` (background/border via
the ``"tooltip"`` ``QFrame`` variant) holding an :class:`AYLabel`
(``"tooltip"`` ``QLabel`` variant) for the text.

Because we swallow the native event, we also lose Qt's own tracking of
whether the cursor is still over the same "tip area" - the mechanism
that lets a real ``QToolTip`` update instantly as the cursor slides from
one table cell to the next without ever leaving the viewport. ``track()``
below reimplements that piece: once shown for an *owner* widget, this
widget watches that owner's mouse-move events itself and re-resolves the
text, exactly as :class:`QToolTip` would.

Mouse-move events on a viewport can fire far more often than the hovered
cell actually changes, and *resolver* may walk a proxy-model chain to get
there - running it inline on every single one of those events is what
made cell-to-cell hovering feel laggy. Rather than resolve synchronously
in ``eventFilter`` (Qt event handlers should stay cheap - the pattern
most tooltip implementations, e.g. the ``pyqttooltip`` package, also
follow by driving their show/hide/update logic off ``QTimer`` instead of
raw per-event work), a short ``QTimer`` throttles those calls to once per
``_THROTTLE_MS``: the first move after an idle period resolves right
away (so it still feels instant), further moves within the window just
record the latest position, and - if any arrived - one trailing resolve
runs when the window elapses.
"""

from __future__ import annotations

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt
from qtpy.shiboken import isValid

from .container import AYContainer
from .label import AYLabel

_CURSOR_OFFSET = QtCore.QPoint(8, 24)
_AUTO_HIDE_MS = 8000
_THROTTLE_MS = 100


class AYToolTip(AYContainer):
    """Shared, styled tooltip popup.

    A single instance is owned by :class:`~ayon_core.ui.style.AYONStyle`
    and reused for every AYON widget, mirroring how Qt reuses its own
    internal tooltip label.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Tooltip,
            layout_margin=8,
        )
        self.setWindowFlags(
            Qt.WindowType.ToolTip
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.BypassGraphicsProxyWidget
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._label = AYLabel(variant=AYLabel.Variants.Tooltip)
        self.add_widget(self._label)

        self._text = ""
        self._owner: QtCore.QObject | None = None
        self._pending_global_pos: QtCore.QPoint | None = None
        self._hide_timer = QtCore.QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide_tooltip)
        self._throttle_timer = QtCore.QTimer(self)
        self._throttle_timer.setSingleShot(True)
        self._throttle_timer.setInterval(_THROTTLE_MS)
        self._throttle_timer.timeout.connect(self._on_throttle_timeout)

    def track(
        self,
        owner: QtCore.QWidget,
        global_pos: QtCore.QPoint,
    ) -> None:
        """Show *text* for *owner* and keep it in sync while visible.

        Installs an event filter on *owner* so this widget notices, on its
        own, when the cursor has moved to a spot whose tooltip text
        differs - e.g. a different cell in the same table - and refreshes
        (or hides) itself accordingly. *resolver* maps a position (in
        *owner*'s coordinates) to the tooltip text that applies there;
        only the caller knows how to do that (index lookups, etc.), so it
        is supplied rather than reimplemented here.
        """
        self._detach()
        self._owner = owner
        text = self._resolve_tooltip_text(global_pos)

        owner.installEventFilter(self)
        if not text:
            return
        self.show_text(text, global_pos)

    def _detach(self) -> None:
        self._throttle_timer.stop()
        self._pending_global_pos = None
        if self._owner is not None and isValid(self._owner):
            self._owner.removeEventFilter(self)
        self._owner = None

    def _resolve_tooltip_text(
        self, global_pos: QtCore.QPoint
    ) -> str:
        """Return the tooltip text Qt would have shown for *obj*/*pos*.

        Item views (tables/trees) don't set ``toolTip()`` on themselves -
        each cell's tooltip comes from the model's ``ToolTipRole``,
        resolved internally by the view from the cursor position. *obj*
        here is the view's *viewport*, since that's what receives
        position-based events, so look the index up the same way Qt does.
        """
        obj = self._owner
        if not isinstance(obj, QtWidgets.QWidget) or not isValid(obj):
            return ""

        view = obj.parentWidget()
        if (
            isinstance(view, QtWidgets.QAbstractItemView)
            and view.viewport() is obj
        ):
            pos = obj.mapFromGlobal(global_pos)
            index = view.indexAt(pos)
            if index.isValid():
                text = index.data(QtCore.Qt.ItemDataRole.ToolTipRole)
                return str(text) if text else ""
            return ""

        return obj.toolTip()

    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        """Record cursor moves and throttle how often they get resolved."""
        if watched is self._owner and event.type() == (
            QtCore.QEvent.Type.MouseMove
        ):
            self._pending_global_pos = event.globalPos()
            if not self._throttle_timer.isActive():
                self._resolve_pending()
                self._throttle_timer.start()
        return super().eventFilter(watched, event)

    def _on_throttle_timeout(self) -> None:
        """Run one trailing resolve if moves kept arriving during cooldown."""
        if self._pending_global_pos is not None:
            self._resolve_pending()
            self._throttle_timer.start()

    def _resolve_pending(self) -> None:
        if self._owner is None or self._pending_global_pos is None:
            return
        global_pos = self._pending_global_pos
        self._pending_global_pos = None
        text = self._resolve_tooltip_text(global_pos)
        if text != self._text:
            if text:
                self.show_text(text, global_pos)
            else:
                self.hide_tooltip()

    def show_text(self, text: str, global_pos: QtCore.QPoint) -> None:
        """Show *text* near *global_pos*, clamped to the current screen."""
        self._text = text
        self._label.setText(text)

        # AYLabel.sizeHint() measures a single line only (it uses Qt's
        # boundingRect(QString) convenience overload, which forces
        # TextSingleLine) - explicit multi-line tooltips like the filter
        # bar's "Version: Latest\nand ..." need line breaks honored, so
        # size the label ourselves with the rect-based overload instead
        # of trusting adjustSize() to get it right.
        metrics = QtGui.QFontMetrics(self._label.font())
        lines = text.split("\n")
        text_width = max(metrics.horizontalAdvance(line) for line in lines)
        text_height = metrics.height() * len(lines)
        self._label.setFixedSize(text_width, text_height)
        self.adjustSize()

        target = global_pos + _CURSOR_OFFSET
        screen = (
            QtWidgets.QApplication.screenAt(global_pos)
            or QtWidgets.QApplication.primaryScreen()
        )
        if screen is not None:
            screen_rect = screen.availableGeometry()
            if target.x() + self.width() > screen_rect.right():
                target.setX(screen_rect.right() - self.width())
            if target.y() + self.height() > screen_rect.bottom():
                target.setY(global_pos.y() - self.height() - 8)

        self.move(target)
        self.show()
        self.raise_()
        self._hide_timer.start(_AUTO_HIDE_MS)

    def hide_tooltip(self) -> None:
        self._detach()
        self._hide_timer.stop()
        self.hide()
