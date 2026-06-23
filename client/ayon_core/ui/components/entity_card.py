"""AYEntityCard — a card widget representing an AYON entity (task, version,
product, etc.).

Mirrors the EntityCard component from https://components.ayon.dev.

Layout
------
  ┌─── header row ─────────────────────────────────────────────┐
  │  [project]  [path/breadcrumb]          [entity name bold]  │
  └────────────────────────────────────────────────────────────┘
  ┌─── card body (thumbnail + overlay) ────────────────────────┐
  │  [background image or icon placeholder]                    │
  │                                                            │
  │  ┄ overlay top row ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄    │
  │  [title chip (icon + text)]              [play chip]       │
  │                                                            │
  │  ┄ overlay bottom row ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄    │
  │  [users] [priority] [versions]            [status icon]    │
  └────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from qtpy import QtCore, QtGui
from qtpy.QtCore import QMimeData, QPoint, QRectF, QSize, Qt, Signal  # type: ignore
from qtpy.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QDrag,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from qtpy.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ayon_core.ui.components.entity_thumbnail import AYEntityThumbnail
from ayon_core.ui.components.label import AYLabel


from ..image_cache import ImageCache
from ..style_types import get_ayon_style, get_ayon_style_data
from ..variants import QFrameVariants
from .container import AYContainer
from .entity_path import AYEntityPath
from .user_image import AYUserImage

IMG_RATIO = 200.0 / 112.5  # 16:9
CARD_RATIO = 200.0 / (112.5 + 24)  # thumbnail + header


# ---------------------------------------------------------------------------
# Card body — draws thumbnail + state borders
# ---------------------------------------------------------------------------


class _CardBody(AYEntityThumbnail):
    """The main thumbnail area of the card.

    Paints the background image (or a placeholder icon), overlays state
    borders (active / hover / dragging / error) and a dim skeleton when
    is_loading is True.
    """

    def __init__(
        self,
        width: int = 200,
        async_file_cacher: (
            Callable[[str, Callable[[str], None]], None] | None
        ) = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            variant=AYEntityThumbnail.Variants.Entity_Card,
            size=(width, width / IMG_RATIO),
            fade_duration=250,
            placeholder_icon="image",
            placeholder_scale=0.20,
            async_file_cacher=async_file_cacher,
            parent=parent,
        )

        self._pixmap: QPixmap | None = None
        self._image_src: str | Path = ""
        self._image_icon: str = "image"
        self._is_active: bool = False
        self._is_hover: bool = False
        self._is_dragging: bool = False
        self._is_loading: bool = False
        self._is_error: bool = False

    # ------------------------------------------------------------------
    # Public data setters
    # ------------------------------------------------------------------

    def set_image_icon(self, icon: str) -> None:
        self._image_icon = icon or "image"
        self.update()

    def set_is_active(self, v: bool) -> None:
        self._is_active = v
        self.update()

    def set_is_hover(self, v: bool) -> None:
        self._is_hover = v
        self.update()

    def set_is_dragging(self, v: bool) -> None:
        self._is_dragging = v
        self.update()

    def set_is_loading(self, v: bool) -> None:
        self._is_loading = v
        self.update()

    def set_is_error(self, v: bool) -> None:
        self._is_error = v
        self.update()


# ---------------------------------------------------------------------------
# Overlay (transparent widget floating on top of _CardBody)
# ---------------------------------------------------------------------------


class _CardOverlay(QWidget):
    """Transparent overlay carrying the top-row and bottom-row chip strips."""

    def __init__(
        self, parent: QWidget | None = None, size: QSize | None = None
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )
        self.set_width(size)
        self.setMouseTracking(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(3, 3, 3, 3)
        outer.setSpacing(0)

        # --- top row ---
        self._top_row = QWidget(self)
        self._top_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        top_lyt = QHBoxLayout(self._top_row)
        top_lyt.setContentsMargins(0, 0, 0, 0)
        top_lyt.setSpacing(4)

        self._title_chip = AYLabel(
            "",
            icon_size=16,
            rel_text_size=-1,
            variant=AYLabel.Variants.Entity_Label,
        )
        self._title_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_chip.hide()

        self._playable_chip = AYLabel(
            "",
            icon="play_circle",
            icon_size=16,
            variant=AYLabel.Variants.Entity_Label,
        )
        self._playable_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._playable_chip.hide()

        top_lyt.addWidget(self._title_chip)
        top_lyt.addStretch(1)
        top_lyt.addWidget(self._playable_chip)

        outer.addWidget(self._top_row)
        outer.addStretch(1)

        # --- bottom row ---
        self._bottom_row = QWidget(self)
        self._bottom_row.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        bot_lyt = QHBoxLayout(self._bottom_row)
        bot_lyt.setContentsMargins(0, 0, 0, 0)
        bot_lyt.setSpacing(4)

        self._users_chip = AYUserImage(
            self, variant=AYUserImage.Variants.Entity_Card
        )
        self._users_chip.hide()
        self._priority_chip = AYLabel(
            self, icon_size=16, variant=AYLabel.Variants.Entity_Label
        )
        self._priority_chip.hide()
        self._version_chip = AYLabel(
            self, icon_size=16, variant=AYLabel.Variants.Entity_Label
        )
        self._version_chip.hide()
        self._status_chip = AYLabel(
            self,
            icon_size=16,
            variant=AYLabel.Variants.Entity_Label_Filled,
        )
        self._status_chip.hide()

        bot_lyt.addWidget(self._users_chip)
        bot_lyt.addWidget(self._priority_chip)
        bot_lyt.addWidget(self._version_chip)
        bot_lyt.addStretch(1)
        bot_lyt.addWidget(self._status_chip)

        outer.addWidget(self._bottom_row)

    # ------------------------------------------------------------------
    # Public update methods
    # ------------------------------------------------------------------

    def set_width(self, size: QSize | None) -> None:
        if size:
            self.setFixedSize(size)

    def set_title(
        self,
        title: str,
        icon: str,
        color: str,
        on_click: QtCore.SignalInstance | None = None,
    ) -> None:
        self._title_chip.setText(title)
        self._title_chip.set_icon(icon)
        self._title_chip.setVisible(bool(title or icon))

    def set_playable(self, is_playable: bool) -> None:
        self._playable_chip.setVisible(is_playable)

    def set_users(self, users: list[dict[str, Any]] | None) -> None:
        if not users:
            self._users_chip.hide()
            return

        self._users_chip.update_params(
            users[0].get("name", "?"),
            users[0].get("full_name", "?"),
        )

    def set_priority(
        self, priority: dict[str, Any] | None, hide: bool = False
    ) -> None:
        if hide or not priority:
            self._priority_chip.hide()
            return

        icon = priority.get("icon", "")
        color = priority.get("color", "")
        if icon:
            self._priority_chip.set_icon(icon=icon, color=color)
        self._priority_chip.setVisible(bool(icon))

    def set_version(self, version: str | None) -> None:
        if not version:
            self._version_chip.hide()
            return

        self._version_chip.setText(version)
        self._version_chip.show()

    def set_status(self, status: dict[str, Any] | None) -> None:
        if not status:
            self._status_chip.hide()
            return

        icon = status.get("icon", "")
        color = status.get("color", "")
        name = status.get("name", "")
        short_name = status.get("short_name", "")

        self._status_chip.setText(short_name or name)
        self._status_chip.set_icon(icon=icon, color=color)

        self._status_chip.show()

    def set_loading(self, is_loading: bool) -> None:
        self._top_row.setVisible(not is_loading)
        self._bottom_row.setVisible(not is_loading)


# ---------------------------------------------------------------------------
# Header widget
# ---------------------------------------------------------------------------


class _CardHeader(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyle(get_ayon_style())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedHeight(24)

        lyt = QHBoxLayout(self)
        lyt.setContentsMargins(5, 0, 5, 0)
        lyt.setSpacing(4)

        self._path_widget = AYEntityPath(parent=self, simple=True)
        self._path_widget.hide()

        self._header_lbl = AYLabel("", bold=True, rel_text_size=-1)
        self._header_lbl.hide()

        lyt.addWidget(self._path_widget, 1)
        lyt.addWidget(self._header_lbl)
        lyt.addStretch(0)
        self.hide()

    def update_content(
        self,
        project: str,
        path: str | list[str],
        header: str,
        show_path: bool,
    ) -> None:
        path_str = "/".join(path) if isinstance(path, list) else (path or "")
        if path_str:
            self._path_widget.entity_path = path_str
            self._path_widget.setVisible(True)
        else:
            self._path_widget.setVisible(show_path)

        if header:
            self._header_lbl.setText(header)
            self._header_lbl.show()
        else:
            self._header_lbl.hide()

        self.setVisible(bool(path_str or header or show_path))


# ---------------------------------------------------------------------------
# Main: AYEntityCard
# ---------------------------------------------------------------------------


class AYEntityCard(AYContainer):
    """A card widget representing an AYON entity (task, version, product…).

    Signals
    -------
    activated
        Emitted when the card is clicked (or keyboard-activated).
    title_clicked
        Emitted when the title chip inside the card is clicked.
    """

    activated = Signal()
    title_clicked = Signal()

    def __init__(
        self,
        *,
        width: int = 200,
        header: str = "",
        path: str | list[str] = "",
        project: str = "",
        show_path: bool = False,
        title: str = "",
        title_icon: str = "",
        title_color: str = "",
        is_playable: bool = False,
        users: list[dict[str, Any]] | None = None,
        status: dict[str, Any] | None = None,
        priority: dict[str, Any] | None = None,
        hide_priority: bool = False,
        version: str = "",
        image_src: str | Path = "",
        image_icon: str = "image",
        is_active: bool = False,
        is_loading: bool = False,
        is_error: bool = False,
        is_hover: bool = False,
        is_dragging: bool = False,
        is_draggable: bool = False,
        placeholder_icon: str = "image",
        async_file_cacher: (
            Callable[[str, Callable[[str], None]], None] | None
        ) = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=QFrameVariants.Entity_Card,
            layout_margin=0,
            layout_spacing=0,
        )
        self.set_width(width)

        self.setStyle(get_ayon_style())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)

        # ---- state ----
        self._header = header
        self._path = path
        self._project = project
        self._show_path = show_path
        self._title = title
        self._title_icon = title_icon
        self._title_color = title_color
        self._is_playable = is_playable
        self._users = users
        self._status = status
        self._priority = priority
        self._hide_priority = hide_priority
        self._version = version
        self._image_src = image_src
        self._image_icon = image_icon
        self._is_active = is_active
        self._is_loading = is_loading
        self._is_error = is_error
        self._is_hover = is_hover
        self._is_dragging = is_dragging
        self._is_draggable = is_draggable
        self._async_file_cacher: (
            Callable[[str, Callable[[str], None]], None] | None
        ) = async_file_cacher
        self._drag_start_pos: QPoint | None = None

        # ---- build UI ----
        self._header_widget = _CardHeader(self)
        self.add_widget(self._header_widget)

        _body_sd = get_ayon_style_data("QFrame", self._variant_str)
        _body_sd.set_context(self)
        border_width = _body_sd["border-width"]
        self._card_body = _CardBody(
            parent=self,
            width=width - (border_width * 2),
            async_file_cacher=async_file_cacher,
        )
        self._card_body.set_placeholder_icon(placeholder_icon)
        body_size = self._card_body.size()
        self._overlay = _CardOverlay(
            parent=self,
            size=body_size,
        )

        # Lay body & overlay in a stacked layout so overlay is on top
        stacked = QStackedLayout()
        stacked.setStackingMode(QStackedLayout.StackingMode.StackAll)
        stacked.addWidget(self._card_body)
        stacked.addWidget(self._overlay)
        stacked.setCurrentWidget(self._overlay)

        # Wrap the stacked layout in a widget to keep it centered.
        self._body_wrapper = QWidget(self)
        self._body_wrapper.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        self._body_wrapper.setFixedSize(body_size)
        self._body_wrapper.setLayout(stacked)
        self.add_widget(self._body_wrapper)
        self._layout.setAlignment(
            self._body_wrapper, Qt.AlignmentFlag.AlignHCenter
        )

        # ---- init content ----
        self._rebuild_header()
        self._rebuild_thumbnail()
        self._rebuild_overlay()
        self._apply_body_state()

        # ---- drag ----
        if is_draggable:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

    def set_width(self, w: int) -> None:
        """Set the card width and adjust height to maintain a 1.52:1 aspect
        ratio (default thumbnail ratio from front-end)."""
        self.setFixedSize(w, int(w / CARD_RATIO))

    def resize_to_width(self, w: int) -> None:
        """Resize the card and all internal sub-widgets to a new width."""
        _body_sd = get_ayon_style_data("QFrame", self._variant_str)
        _body_sd.set_context(self)
        border_width = _body_sd["border-width"]
        body_w = w - (border_width * 2)
        body_h = int(body_w / IMG_RATIO)
        body_size = QSize(body_w, body_h)

        self._card_body.set_size((body_w, body_h))
        self._overlay.set_width(body_size)
        self._body_wrapper.setFixedSize(body_size)
        self.set_width(w)

    # ------------------------------------------------------------------
    # Rebuild helpers
    # ------------------------------------------------------------------

    def _rebuild_header(self) -> None:
        self._header_widget.update_content(
            self._project, self._path, self._header, self._show_path
        )

    def _rebuild_thumbnail(self) -> None:
        self._card_body.set_thumbnail(self._image_src)
        self._card_body.set_image_icon(self._image_icon)

    def _rebuild_overlay(self) -> None:
        self._overlay.set_title(
            self._title,
            self._title_icon,
            self._title_color,
            on_click=self.title_clicked,
        )
        self._overlay.set_playable(self._is_playable)
        self._overlay.set_users(self._users)
        self._overlay.set_priority(self._priority, hide=self._hide_priority)
        self._overlay.set_version(self._version)
        self._overlay.set_status(self._status)
        self._overlay.set_loading(self._is_loading)

    def _apply_body_state(self) -> None:
        self._card_body.set_is_active(self._is_active)
        self._card_body.set_is_hover(self._is_hover)
        self._card_body.set_is_dragging(self._is_dragging)
        self._card_body.set_is_loading(self._is_loading)
        self._card_body.set_is_error(self._is_error)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def header(self) -> str:
        return self._header

    @header.setter
    def header(self, value: str) -> None:
        self._header = value
        self._rebuild_header()

    @property
    def path(self) -> str | list[str]:
        return self._path

    @path.setter
    def path(self, value: str | list[str]) -> None:
        self._path = value
        self._rebuild_header()

    @property
    def project(self) -> str:
        return self._project

    @project.setter
    def project(self, value: str) -> None:
        self._project = value
        self._rebuild_header()

    @property
    def show_path(self) -> bool:
        return self._show_path

    @show_path.setter
    def show_path(self, value: bool) -> None:
        self._show_path = value
        self._rebuild_header()

    @property
    def title(self) -> str:
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        self._title = value
        self._rebuild_overlay()

    @property
    def title_icon(self) -> str:
        return self._title_icon

    @title_icon.setter
    def title_icon(self, value: str) -> None:
        self._title_icon = value
        self._rebuild_overlay()

    @property
    def title_color(self) -> str:
        return self._title_color

    @title_color.setter
    def title_color(self, value: str) -> None:
        self._title_color = value
        self._rebuild_overlay()

    @property
    def is_playable(self) -> bool:
        return self._is_playable

    @is_playable.setter
    def is_playable(self, value: bool) -> None:
        self._is_playable = value
        self._rebuild_overlay()

    @property
    def users(self) -> list[dict[str, Any]] | None:
        return self._users

    @users.setter
    def users(self, value: list[dict[str, Any]] | None) -> None:
        self._users = value
        self._rebuild_overlay()

    @property
    def status(self) -> dict[str, Any] | None:
        return self._status

    @status.setter
    def status(self, value: dict[str, Any] | None) -> None:
        self._status = value
        self._rebuild_overlay()

    @property
    def priority(self) -> dict[str, Any] | None:
        return self._priority

    @priority.setter
    def priority(self, value: dict[str, Any] | None) -> None:
        self._priority = value
        self._rebuild_overlay()

    @property
    def hide_priority(self) -> bool:
        return self._hide_priority

    @hide_priority.setter
    def hide_priority(self, value: bool) -> None:
        self._hide_priority = value
        self._rebuild_overlay()

    @property
    def version(self) -> str | None:
        return self._version

    @version.setter
    def version(self, value: str | None) -> None:
        self._version = value
        self._rebuild_overlay()

    @property
    def image_src(self) -> str | Path:
        return self._image_src

    @image_src.setter
    def image_src(self, value: str | Path) -> None:
        self._image_src = value
        self._rebuild_thumbnail()

    @property
    def image_icon(self) -> str:
        return self._image_icon

    @image_icon.setter
    def image_icon(self, value: str) -> None:
        self._image_icon = value
        self._rebuild_thumbnail()

    @property
    def is_active(self) -> bool:
        return self._is_active

    @is_active.setter
    def is_active(self, value: bool) -> None:
        self._is_active = value
        self._apply_body_state()

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @is_loading.setter
    def is_loading(self, value: bool) -> None:
        self._is_loading = value
        self._apply_body_state()
        self._rebuild_overlay()

    @property
    def is_error(self) -> bool:
        return self._is_error

    @is_error.setter
    def is_error(self, value: bool) -> None:
        self._is_error = value
        self._apply_body_state()

    @property
    def is_hover(self) -> bool:
        return self._is_hover

    @is_hover.setter
    def is_hover(self, value: bool) -> None:
        self._is_hover = value
        self._apply_body_state()

    @property
    def is_dragging(self) -> bool:
        return self._is_dragging

    @is_dragging.setter
    def is_dragging(self, value: bool) -> None:
        self._is_dragging = value
        self._apply_body_state()

    @property
    def is_draggable(self) -> bool:
        return self._is_draggable

    @is_draggable.setter
    def is_draggable(self, value: bool) -> None:
        self._is_draggable = value
        if value:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        else:
            self.unsetCursor()

    @property
    def placeholder_icon(self) -> str:
        return self._card_body._placeholder_icon_name

    @placeholder_icon.setter
    def placeholder_icon(self, value: str) -> None:
        self._card_body.set_placeholder_icon(value)
        self._rebuild_thumbnail()

    @property
    def async_file_cacher(
        self,
    ) -> Callable[[str, Callable[[str], None]], None] | None:
        """Non-blocking thumbnail fetcher used by the card body.

        When set, the card body's :class:`AYEntityThumbnail` will call
        this callable with ``(key, on_loaded)`` whenever a thumbnail
        cache miss is detected.  The callable should schedule the
        download on a background thread and call ``on_loaded(file_path)``
        on the Qt main thread when complete.

        Setting this property also updates the underlying
        :class:`_CardBody` so that any subsequent :meth:`set_thumbnail`
        calls benefit from the new fetcher immediately.
        """
        return self._async_file_cacher

    @async_file_cacher.setter
    def async_file_cacher(
        self,
        value: Callable[[str, Callable[[str], None]], None] | None,
    ) -> None:
        self._async_file_cacher = value
        # Forward to the card body so it can self-fetch on cache miss.
        self._card_body._async_file_cacher = value
        # Trigger a fetch only when the current image is not yet available.
        if value and self._image_src:
            ic = ImageCache.get_instance()
            already_cached = ic.has(str(self._image_src))
            on_disk = Path(self._image_src).exists()
            if not already_cached and not on_disk:
                self._card_body.set_thumbnail(self._image_src)

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        super().paintEvent(arg__1)
        if not self._is_active:
            return
        style_all = get_ayon_style_data("QFrame", self._variant_str)
        style_all.set_context(self)
        border_width = int(style_all.get("border-width", 2))
        border_radius = float(style_all.get("border-radius", 10))
        border_color = QColor(
            style_all.get("active", {}).get("border-color", "#8fceff")
        )
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(border_color, border_width)
        p.setPen(pen)
        p.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        half = border_width / 2.0
        draw_rect = QRectF(self.rect()).adjusted(half, half, -half, -half)
        p.drawRoundedRect(draw_rect, border_radius, border_radius)

    # ------------------------------------------------------------------
    # Mouse / drag events
    # ------------------------------------------------------------------

    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        if self._is_draggable:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        if self._is_draggable:
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
        super().leaveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._is_draggable
            and self._drag_start_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = (event.pos() - self._drag_start_pos).manhattanLength()
            if delta >= QApplication.startDragDistance():
                self._start_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._drag_start_pos is not None
        ):
            self.activated.emit()
            self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(self._header)
        drag.setMimeData(mime)
        # Create a semi-transparent drag thumbnail from the card body
        pxm = self._card_body.grab()
        semi = QPixmap(pxm.size())
        semi.fill(Qt.GlobalColor.transparent)
        painter = QPainter(semi)
        painter.setOpacity(0.75)
        painter.drawPixmap(0, 0, pxm)
        painter.end()
        drag.setPixmap(semi)
        drag.setHotSpot(self._card_body.rect().center())
        self.is_dragging = True
        drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction)
        self.is_dragging = False


# ---------------------------------------------------------------------------
# __main__ — manual visual test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from ..tester import Style, test

    _USERS = [
        {"name": "jd", "full_name": "John Doe"},
        {"name": "ab", "full_name": "Alice Brown"},
        {"name": "cm", "full_name": "Charlie Moss"},
    ]
    _STATUS = {
        "name": "In Progress",
        "icon": "play_circle",
        "color": "#3498db",
        "short_name": "PRG",
    }
    _PRIORITY = {
        "label": "Medium",
        "color": "rgb(52, 152, 219)",
        "icon": "check_indeterminate_small",
        "value": "medium",
    }

    def _build():
        w = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=32,
            layout_spacing=16,
        )

        card1 = AYEntityCard(
            header="ep103sq002",
            path=["sequences", "ep103", "shots"],
            project="com",
            title="Lighting",
            title_icon="lightbulb",
            title_color="#ffd700",
            is_playable=True,
            users=_USERS,
            status=_STATUS,
            priority=_PRIORITY,
        )
        w.add_widget(card1)

        card2 = AYEntityCard(
            header="Loading…",
            title="Animation",
            title_icon="run_circle",
            is_loading=True,
        )
        w.add_widget(card2)

        card3 = AYEntityCard(
            header="No image",
            title="Compositing",
            title_icon="layers",
            users=_USERS[:1],
            status=_STATUS,
            version="v003",
        )
        w.add_widget(card3)

        card4 = AYEntityCard(
            header="Active",
            title="Rigging",
            title_icon="account_tree",
            status=_STATUS,
            priority=_PRIORITY,
            is_active=True,
            is_draggable=True,
        )
        w.add_widget(card4)

        return w

    test(_build, style=Style.AYONStyleOverCSS)
