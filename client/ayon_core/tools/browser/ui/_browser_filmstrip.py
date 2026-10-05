"""Hover-scrub filmstrip previews for thumbnails (prototype).

A filmstrip is a single image with a fixed number of frames sampled evenly
from the video reviewable of an entity, laid out in a grid left to right,
top to bottom. While the cursor is over a thumbnail the frame matching the
horizontal cursor position is shown, so moving the cursor "plays" the video.

Requires a server with the filmstrip endpoints (ynput/ayon-backend#1148).
"""

from __future__ import annotations

import functools
import math
import os
import tempfile
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable, Optional, Tuple

import ayon_api
from ayon_core.ui.components.entity_card import AYEntityCard
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.image_cache import ImageCache
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger, get_ffmpeg_tool_args, run_subprocess

log = Logger.get_logger(__name__)

# Wait before loading, so sweeping the cursor over a table does not load
# the filmstrip of every row.
HOVER_INTENT_DELAY_MS = 120
# Entity filmstrips can change (a new reviewable) without the url changing.
DEFAULT_MAX_AGE = 300
# Failed requests (e.g. server without the endpoints) are retried later.
FAILED_MAX_AGE = 60
# Every decoded filmstrip is ~10 MB in memory.
MAX_MEMORY_ENTRIES = 8
PROGRESS_COLOR = "#8fceff"
PROGRESS_HEIGHT = 2
# Size of the click popup relative to the size of the filmstrip frames
POPUP_SCALE = 1

# (project_name, entity_type, entity_id)
_SourceKey = Tuple[str, str, str]


@dataclass
class FilmstripData:
    """Decoded filmstrip of an entity.

    Attributes:
        file_id: The video file (reviewable) the frames were taken from.
        image: Decoded filmstrip image with all frames.
        frames: Number of frames in the image.
        columns: Number of frames per row.
    """

    file_id: str
    image: QtGui.QImage
    frames: int
    columns: int

    def frame_rect(self, index: int) -> QtCore.QRectF:
        """Return the rect of frame *index* within the image."""
        rows = math.ceil(self.frames / self.columns)
        width = self.image.width() / self.columns
        height = self.image.height() / rows
        return QtCore.QRectF(
            (index % self.columns) * width,
            (index // self.columns) * height,
            width,
            height,
        )


@dataclass
class _CacheEntry:
    data: FilmstripData | None
    expires_at: float


# Insertion order is used as LRU order. Only accessed from the main thread.
_memory_cache: OrderedDict[_SourceKey, _CacheEntry] = OrderedDict()


def _peek_filmstrip(key: _SourceKey) -> _CacheEntry | None:
    """Return the cache entry of *key* when it is still valid."""
    entry = _memory_cache.get(key)
    if entry is None:
        return None
    if entry.expires_at < time.time():
        _memory_cache.pop(key, None)
        return None
    _memory_cache.move_to_end(key)
    return entry


def _store_filmstrip(
    key: _SourceKey, data: FilmstripData | None, max_age: float
) -> None:
    _memory_cache[key] = _CacheEntry(data, time.time() + max_age)
    _memory_cache.move_to_end(key)
    while len(_memory_cache) > MAX_MEMORY_ENTRIES:
        _memory_cache.popitem(last=False)


@functools.lru_cache(maxsize=None)
def _qt_supports_avif() -> bool:
    # Image format plugins do not change within a session
    formats = QtGui.QImageReader.supportedImageFormats()
    return any(fmt.data().lower() == b"avif" for fmt in formats)


def _download_filmstrip_image(url: str) -> str:
    """Download a filmstrip image to a temp file readable by Qt.

    The server stores filmstrips as AVIF, which Qt can read only with an
    extra image format plugin, so it is converted with ffmpeg if needed.

    Returns:
        Path to the temp file.
    """
    con = ayon_api.get_server_api_connection()
    if url.startswith("/"):
        url = con.get_base_url().rstrip("/") + url
    response = con.raw_get(url)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".avif", delete=False) as fh:
        fh.write(response.content)
        avif_path = fh.name
    if _qt_supports_avif():
        return avif_path

    jpg_path = os.path.splitext(avif_path)[0] + ".jpg"
    try:
        run_subprocess(
            get_ffmpeg_tool_args(
                "ffmpeg",
                "-y",
                "-loglevel", "error",
                "-i", avif_path,
                "-q:v", "2",
                jpg_path,
            )
        )
    finally:
        os.remove(avif_path)
    return jpg_path


def _fetch_filmstrip(key: _SourceKey) -> tuple[FilmstripData | None, float]:
    """Fetch and decode the filmstrip of an entity. Runs in a worker thread.

    Returns:
        The filmstrip, or ``None`` when the entity has no video reviewable,
        and how long (seconds) the answer may be cached.
    """
    project_name, entity_type, entity_id = key
    con = ayon_api.get_server_api_connection()
    response = con.raw_get(
        f"projects/{project_name}/{entity_type}s/{entity_id}/filmstrip"
    )
    # 204 = the entity has no video reviewable
    if response.status_code == 204:
        return None, DEFAULT_MAX_AGE
    response.raise_for_status()
    info = response.data
    url = info["url"]

    tmp_paths: list[str] = []

    def _download() -> str:
        tmp_paths.append(_download_filmstrip_image(url))
        return tmp_paths[-1]

    # The url only changes when the filmstrip is re-created
    try:
        path = ImageCache.get_instance().get(f"filmstrip:{url}", _download)
    finally:
        # ImageCache made its own copy
        for tmp_path in tmp_paths:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    image = QtGui.QImage(path)
    if image.isNull():
        raise ValueError(f"Failed to read filmstrip image: {path}")
    data = FilmstripData(
        file_id=info.get("fileId", ""),
        image=image,
        frames=int(info["frames"]),
        columns=int(info["columns"]),
    )
    return data, DEFAULT_MAX_AGE


def _load_filmstrip(key: _SourceKey) -> tuple[FilmstripData | None, float]:
    try:
        return _fetch_filmstrip(key)
    except Exception:
        log.debug("Failed to load filmstrip for %r", key, exc_info=True)
        return None, FAILED_MAX_AGE


def _paint_frame(
    painter: QtGui.QPainter,
    area: QtCore.QRectF,
    data: FilmstripData,
    position: float,
    fit: str,
    background: QtGui.QColor | None,
) -> None:
    """Paint the frame at *position* (0-1) and a progress bar into *area*.

    Args:
        painter: Painter of the widget.
        area: Rect to paint into.
        data: Filmstrip with the frames.
        position: Relative position (0-1) in the video.
        fit: ``"contain"`` or ``"cover"``.
        background: Fill behind the frame.
    """
    index = min(int(position * data.frames), data.frames - 1)
    source = data.frame_rect(index)
    if area.isEmpty() or source.isEmpty():
        return

    scales = (
        area.width() / source.width(),
        area.height() / source.height(),
    )
    scale = max(scales) if fit == "cover" else min(scales)
    target = QtCore.QRectF(
        0, 0, source.width() * scale, source.height() * scale
    )
    target.moveCenter(area.center())

    painter.setRenderHint(
        QtGui.QPainter.RenderHint.SmoothPixmapTransform, True
    )
    painter.setClipRect(area)
    if background is not None:
        painter.fillRect(area, background)
    painter.drawImage(target, data.image, source)
    # the shown frame is the middle of the index-th part of the video
    progress = (index + 0.5) / data.frames
    painter.fillRect(
        QtCore.QRectF(
            area.left(),
            area.bottom() - PROGRESS_HEIGHT,
            area.width() * progress,
            PROGRESS_HEIGHT,
        ),
        QtGui.QColor(PROGRESS_COLOR),
    )


class FilmstripOverlay(QtWidgets.QWidget):
    """Hover-scrub preview shown on top of a thumbnail widget.

    The overlay covers its *host* widget and is only visible while a frame
    is shown. It tracks the cursor over the host by itself. Hosts that do
    not receive mouse events (e.g. table cell widgets transparent for mouse
    events) can be driven with :meth:`scrub` and :meth:`stop` instead.

    Args:
        host: Thumbnail widget to show the frames on.
        fit: ``"contain"`` or ``"cover"``, should match how the static
            thumbnail underneath is fitted.
        inset: Pixels kept free at the host edges, e.g. for its border.
        background: Fill behind the frame, e.g. to hide the static
            thumbnail when the aspect ratios differ.
        source_getter: Called when the cursor enters to update the source
            (see :meth:`set_source`), for hosts reused for other entities.
            Returns ``(project_name, entity_type, entity_id)`` or ``None``.
    """

    def __init__(
        self,
        host: QtWidgets.QWidget,
        fit: str = "contain",
        inset: int = 0,
        background: QtGui.QColor | None = None,
        source_getter: Callable[[], Optional[_SourceKey]] | None = None,
    ) -> None:
        super().__init__(host)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._fit = fit
        self._inset = inset
        self._background = background
        self._source_getter = source_getter
        self._source: _SourceKey | None = None
        self._data: FilmstripData | None = None
        self._position: float = 0.0
        self._hovering: bool = False
        self._popup_requested: bool = False

        self._intent_timer = QtCore.QTimer(self)
        self._intent_timer.setSingleShot(True)
        self._intent_timer.setInterval(HOVER_INTENT_DELAY_MS)
        self._intent_timer.timeout.connect(self._request_load)

        self.hide()
        self.setGeometry(host.rect())
        host.setMouseTracking(True)
        host.installEventFilter(self)

    def track(self, widget: QtWidgets.QWidget) -> None:
        """Also track the cursor over *widget*, which covers the host.

        Args:
            widget: Widget on top of the host receiving its mouse events.
        """
        widget.setMouseTracking(True)
        widget.installEventFilter(self)

    def set_source(
        self,
        project_name: str = "",
        entity_type: str = "version",
        entity_id: str = "",
    ) -> None:
        """Set the entity to preview, nothing is previewed without one.

        Args:
            project_name: Project name.
            entity_type: ``"version"``, ``"task"`` or ``"folder"``.
            entity_id: Entity id.
        """
        source = None
        if project_name and entity_id:
            source = (project_name, entity_type, entity_id)
        if source == self._source:
            return
        was_hovering = self._hovering
        self.stop()
        self._source = source
        # The thumbnail changed under a stationary cursor
        if was_hovering and source:
            self.scrub(self._position)

    def scrub(self, position: float) -> None:
        """Show the frame at the relative *position* (0-1) of the video."""
        if not self._hovering and self._source_getter is not None:
            self.set_source(*(self._source_getter() or ()))
        if self._source is None:
            return
        self._position = min(max(position, 0.0), 1.0)
        if not self._hovering:
            self._hovering = True
            entry = _peek_filmstrip(self._source)
            if entry is not None:
                self._data = entry.data
            else:
                self._intent_timer.start()
        if self._data is not None:
            self.setGeometry(self.parentWidget().rect())
            self.show()
            self.raise_()
            self.update()

    def stop(self) -> None:
        """Hide the preview and restore the static thumbnail."""
        self._hovering = False
        self._popup_requested = False
        self._intent_timer.stop()
        self._data = None
        self.hide()

    def show_popup(self) -> None:
        """Show the filmstrip at full size in a popup over the host.

        Does nothing when the entity has no filmstrip. A filmstrip that is
        not loaded yet is shown once loaded, unless the cursor left.
        """
        if self._source is None:
            return
        entry = _peek_filmstrip(self._source)
        if entry is None:
            self._popup_requested = True
            self._intent_timer.stop()
            self._request_load()
        elif entry.data is not None:
            self._open_popup(entry.data)

    def _open_popup(self, data: FilmstripData) -> None:
        self._popup_requested = False
        host = self.parentWidget()
        popup = FilmstripPopup(data, self._position, parent=host.window())
        popup.show_over(host)

    def _request_load(self) -> None:
        source = self._source
        if source is None:
            return
        if not self._hovering and not self._popup_requested:
            return
        overlay = self

        def _on_loaded(result) -> None:
            if not shiboken.isValid(overlay):
                return
            # Task was cancelled or failed
            if result is None:
                return
            data, max_age = result
            _store_filmstrip(source, data, max_age)
            if overlay._source != source:
                return
            if overlay._popup_requested and data is not None:
                overlay._open_popup(data)
            elif overlay._hovering:
                overlay._data = data
                overlay.scrub(overlay._position)

        get_task_queue().enqueue(
            AsyncTask(
                name=f"filmstrip_{'/'.join(source)}",
                function=lambda: _load_filmstrip(source),
                callback=_on_loaded,
                priority=1,
            )
        )

    def eventFilter(  # type: ignore[override]
        self, obj: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        event_type = event.type()
        if event_type == QtCore.QEvent.Type.MouseMove:
            width = obj.width()
            if width:
                self.scrub(event.pos().x() / width)
        elif event_type in (
            QtCore.QEvent.Type.Leave,
            QtCore.QEvent.Type.Hide,
        ):
            self.stop()
        elif (
            event_type == QtCore.QEvent.Type.Resize
            and obj is self.parentWidget()
        ):
            self.setGeometry(obj.rect())
        return False

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        if self._data is None:
            return
        inset = self._inset
        area = QtCore.QRectF(self.rect()).adjusted(
            inset, inset, -inset, -inset
        )
        painter = QtGui.QPainter(self)
        _paint_frame(
            painter,
            area,
            self._data,
            self._position,
            self._fit,
            self._background,
        )
        painter.end()


class FilmstripPopup(QtWidgets.QWidget):
    """Borderless full-size filmstrip preview, scrubbed with the cursor.

    Closes on a click outside of it or with the escape key.

    Args:
        data: Filmstrip to show.
        position: Relative position (0-1) of the frame shown first.
        parent: Parent widget.
    """

    def __init__(
        self,
        data: FilmstripData,
        position: float = 0.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            QtCore.Qt.WindowType.Popup
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self._data = data
        self._position = position
        self._pressed: bool = False

    def show_over(self, widget: QtWidgets.QWidget) -> None:
        """Show the popup centered over *widget*, kept within its screen."""
        center = widget.mapToGlobal(widget.rect().center())
        screen = (
            QtWidgets.QApplication.screenAt(center)
            or QtWidgets.QApplication.primaryScreen()
        )
        available = screen.availableGeometry()
        frame_size = self._data.frame_rect(0).size().toSize()
        size = frame_size * POPUP_SCALE
        if (
            size.width() > available.width()
            or size.height() > available.height()
        ):
            size = frame_size.scaled(
                available.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            )
        rect = QtCore.QRect(QtCore.QPoint(0, 0), size)
        rect.moveCenter(center)
        rect.moveLeft(
            max(
                available.left(),
                min(rect.left(), available.right() - rect.width() + 1),
            )
        )
        rect.moveTop(
            max(
                available.top(),
                min(rect.top(), available.bottom() - rect.height() + 1),
            )
        )
        self.setGeometry(rect)
        self.show()

    def mouseMoveEvent(  # type: ignore[override]
        self, event: QtGui.QMouseEvent
    ) -> None:
        # The popup grabs the mouse, the cursor may be outside of it
        position = event.pos().x() / max(self.width(), 1)
        self._position = min(max(position, 0.0), 1.0)
        self.update()

    def mousePressEvent(  # type: ignore[override]
        self, event: QtGui.QMouseEvent
    ) -> None:
        # A click on the popup closes it too, Qt handles clicks outside
        if self.rect().contains(event.pos()):
            self._pressed = True
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(  # type: ignore[override]
        self, event: QtGui.QMouseEvent
    ) -> None:
        if self._pressed and self.rect().contains(event.pos()):
            self.close()
            return
        self._pressed = False
        super().mouseReleaseEvent(event)

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        painter = QtGui.QPainter(self)
        _paint_frame(
            painter,
            QtCore.QRectF(self.rect()),
            self._data,
            self._position,
            "contain",
            QtGui.QColor("#000000"),
        )
        painter.end()


def add_card_filmstrip(card: AYEntityCard) -> None:
    """Add a hover-scrub preview to the thumbnail of a version card.

    Does nothing when the card already has one.

    Args:
        card: Card with ``"<project_name>/<version_id>/<thumbnail_id>"``
            as image source.
    """
    # TODO: 'AYEntityCard' should expose its thumbnail and overlay widgets
    body = card._card_body
    if body.findChild(FilmstripOverlay) is not None:
        return

    def _get_source() -> Optional[_SourceKey]:
        parts = str(card.image_src).split("/", 2)
        if len(parts) != 3 or not parts[0] or not parts[1]:
            return None
        return parts[0], "version", parts[1]

    filmstrip = FilmstripOverlay(
        body, fit="cover", inset=1, source_getter=_get_source
    )
    # The chips overlay covers the thumbnail and receives its mouse events
    filmstrip.track(card._overlay)
