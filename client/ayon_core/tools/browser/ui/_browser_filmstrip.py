"""Hover-scrub filmstrip previews for thumbnails (prototype).

A filmstrip is a single image with a fixed number of frames sampled evenly
from the video reviewable of an entity, laid out in a grid left to right,
top to bottom. While the cursor is over a thumbnail the frame matching the
horizontal cursor position is shown, so moving the cursor "plays" the video.

Requires AYON server 1.17.3 or newer, older servers don't have the
filmstrip endpoints and nothing is requested from them. Filmstrips are
converted with ffmpeg, nothing is requested either when it is not found.
Set ``AYON_BROWSER_DISABLE_FILMSTRIPS=1`` to turn filmstrips off.

The server creates a missing filmstrip on the first request, which can take
a while. Filmstrips are loaded by their own small worker pool so this does
not hold up the other loading of the Browser, a filmstrip is requested at
most once at a time, and requests the cursor already left are dropped
before they are sent.
"""

from __future__ import annotations

import io
import math
import platform
import subprocess
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Tuple

import ayon_api
from ayon_core.ui.components.entity_card import AYEntityCard
from ayon_core.ui.components.entity_thumbnail import AYEntityThumbnail
from ayon_core.ui.components.task_queue import AsyncTask, AsyncTaskQueue
from ayon_core.ui.image_cache import ImageCache
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import (
    CREATE_NO_WINDOW,
    Logger,
    ToolNotFoundError,
    env_value_to_bool,
    get_ffmpeg_tool_args,
)
from ayon_core.tools.browser.server_capabilities import (
    server_supports_filmstrips,
)

log = Logger.get_logger(__name__)

# Wait before loading, so moving the cursor over the table rows or cards
# does not load the filmstrip of every thumbnail it passes.
HOVER_INTENT_DELAY_MS = 250
# Entity filmstrips can change (a new reviewable) without the url changing.
DEFAULT_MAX_AGE = 300
# Failed requests (e.g. server overloaded with filmstrips to create) are
# retried later.
FAILED_MAX_AGE = 60
# The server may still be creating the filmstrip, retry sooner.
BUSY_MAX_AGE = 10
# Creating a filmstrip on the server can take a while. The server finishes
# it also when the request times out, it is requested again after
# 'BUSY_MAX_AGE'. ayon_api retries a request that timed out, but reports
# the timeout even when a retry succeeds.
REQUEST_TIMEOUT = 20
# Max filmstrip requests at the same time. The server creates only a few
# filmstrips at a time anyway (``AYON_FILMSTRIP_CONCURRENCY``).
FILMSTRIP_WORKERS = 2
# Every decoded filmstrip is ~10 MB in memory.
MAX_MEMORY_FILMSTRIPS = 8
PROGRESS_COLOR = "#8fceff"
PROGRESS_HEIGHT = 2

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
    """Cache the answer for *key*, also when there is no filmstrip.

    Only the most recently used filmstrips are kept. Answers without a
    filmstrip are kept until they expire.
    """
    now = time.time()
    _memory_cache[key] = _CacheEntry(data, now + max_age)
    _memory_cache.move_to_end(key)
    filmstrips = 0
    for cache_key, entry in reversed(list(_memory_cache.items())):
        if entry.expires_at < now:
            del _memory_cache[cache_key]
        elif entry.data is not None:
            filmstrips += 1
            if filmstrips > MAX_MEMORY_FILMSTRIPS:
                del _memory_cache[cache_key]


class _FilmstripChangedError(Exception):
    """The filmstrip image of the requested version is gone."""


def _download_filmstrip_image(url: str) -> io.BytesIO:
    """Download a filmstrip image and convert it to JPEG.

    The server stores filmstrips as AVIF, which Qt reads only with an
    extra image format plugin, so it is converted with ffmpeg. ffmpeg
    seeks back in AVIF input, which a pipe can't do, so it reads the pipe
    through its 'cache' protocol. That keeps the data in a temp file of
    its own, removed when ffmpeg exits.

    Returns:
        The JPEG image.
    """
    con = ayon_api.get_server_api_connection()
    if url.startswith("/"):
        url = con.get_base_url().rstrip("/") + url
    response = con.raw_get(url, timeout=REQUEST_TIMEOUT)
    # The filmstrip was re-created since its info was requested
    if response.status_code == 404:
        raise _FilmstripChangedError(url)
    response.raise_for_status()

    kwargs = {}
    if platform.system().lower() == "windows":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    process = subprocess.run(
        get_ffmpeg_tool_args(
            "ffmpeg",
            "-nostdin",
            "-loglevel", "error",
            "-i", "cache:pipe:0",
            "-q:v", "2",
            "-f", "mjpeg",
            "pipe:1",
        ),
        input=response.content,
        capture_output=True,
        check=True,
        # On Windows ffmpeg keeps the cache file in '\tmp' of the drive,
        #   or in the working directory when there is none
        cwd=tempfile.gettempdir(),
        **kwargs,
    )
    image = io.BytesIO(process.stdout)
    # ImageCache takes the file extension from the name
    image.name = "filmstrip.jpg"
    return image


def _fetch_filmstrip(key: _SourceKey) -> tuple[FilmstripData | None, float]:
    """Fetch and decode the filmstrip of an entity. Runs in a worker thread.

    Returns:
        The filmstrip, or ``None`` when the entity has no video reviewable,
        and how long (seconds) the answer may be cached.
    """
    project_name, entity_type, entity_id = key
    con = ayon_api.get_server_api_connection()
    response = con.raw_get(
        f"projects/{project_name}/{entity_type}s/{entity_id}/filmstrip",
        timeout=REQUEST_TIMEOUT,
    )
    # 204 = the entity has no video reviewable, or no filmstrip can be
    #   created for it
    if response.status_code == 204:
        return None, DEFAULT_MAX_AGE
    # No answer, e.g. timed out while the filmstrip is being created
    if response.orig_response is None:
        log.debug("Filmstrip request of %r failed: %s", key, response.detail)
        return None, BUSY_MAX_AGE
    response.raise_for_status()
    info = response.data
    url = info["url"]
    # The url only changes when the filmstrip is re-created
    path = ImageCache.get_instance().get(
        f"filmstrip:{url}", lambda: _download_filmstrip_image(url)
    )
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


# Whether ffmpeg was found, 'None' until looked up
_ffmpeg_found: bool | None = None
_ffmpeg_lock = threading.Lock()


def _find_ffmpeg() -> bool:
    """Return whether ffmpeg is available to convert filmstrips.

    Looked up once, by the first filmstrip request. Runs in a worker
    thread: the lookup runs ffmpeg, and the ayon-third-party addon may
    even download it.
    """
    global _ffmpeg_found
    with _ffmpeg_lock:
        if _ffmpeg_found is None:
            try:
                get_ffmpeg_tool_args("ffmpeg")
                _ffmpeg_found = True
            except ToolNotFoundError:
                log.warning(
                    "Video thumbnails are not scrubbed on hover,"
                    " ffmpeg was not found."
                )
                _ffmpeg_found = False
    return _ffmpeg_found


def filmstrips_enabled() -> bool:
    """Return whether filmstrips are loaded from the server.

    Not on servers without the filmstrip endpoints, nor when turned off with
    ``AYON_BROWSER_DISABLE_FILMSTRIPS=1``, nor once ffmpeg was not found.
    """
    if env_value_to_bool("AYON_BROWSER_DISABLE_FILMSTRIPS"):
        return False
    if _ffmpeg_found is False:
        return False
    return server_supports_filmstrips()


def _load_filmstrip(key: _SourceKey) -> tuple[FilmstripData | None, float]:
    try:
        if not _find_ffmpeg():
            return None, DEFAULT_MAX_AGE
        return _fetch_filmstrip(key)
    except _FilmstripChangedError:
        log.debug("Filmstrip of %r changed while loading", key)
        return None, BUSY_MAX_AGE
    except Exception:
        log.debug("Failed to load filmstrip for %r", key, exc_info=True)
        return None, FAILED_MAX_AGE


# Returned by a request nobody waits for anymore, instead of loading
_SKIPPED = object()


@dataclass
class _Request:
    """Pending filmstrip request.

    Attributes:
        waiters: Number of overlays waiting for the filmstrip. Read by the
            worker thread to skip requests nobody waits for anymore.
    """

    waiters: int = 0


class _FilmstripLoader(QtCore.QObject):
    """Loads filmstrips in its own worker pool, once per filmstrip.

    The results are stored in the memory cache, and :attr:`loaded` is
    emitted with the key. Use :func:`_get_loader` to get the instance.
    """

    loaded = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._requests: dict[_SourceKey, _Request] = {}
        self._queue = AsyncTaskQueue(num_workers=FILMSTRIP_WORKERS)
        self._queue.start()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._queue.stop)

    def request(self, key: _SourceKey) -> None:
        """Load the filmstrip of *key*, unless it is being loaded already.

        Every call must be followed by :meth:`release` or by :attr:`loaded`
        emitted for *key*.
        """
        request = self._requests.get(key)
        if request is None:
            request = _Request()
            self._requests[key] = request
            self._enqueue(key, request)
        request.waiters += 1

    def release(self, key: _SourceKey) -> None:
        """Stop waiting for the filmstrip of *key*.

        A request nobody waits for is skipped when its turn comes. A request
        that already started still finishes and caches the filmstrip.
        """
        request = self._requests.get(key)
        if request is not None and request.waiters > 0:
            request.waiters -= 1

    def _enqueue(self, key: _SourceKey, request: _Request) -> None:
        def _run():
            if request.waiters == 0:
                return _SKIPPED
            return _load_filmstrip(key)

        def _on_done(result) -> None:
            if self._requests.get(key) is not request:
                return
            if result is _SKIPPED:
                # Requested again after it was skipped
                if request.waiters > 0:
                    self._enqueue(key, request)
                else:
                    del self._requests[key]
                return
            del self._requests[key]
            # 'None' when the task itself failed
            data, max_age = result or (None, FAILED_MAX_AGE)
            _store_filmstrip(key, data, max_age)
            self.loaded.emit(key)

        self._queue.enqueue(
            AsyncTask(
                name=f"filmstrip_{'/'.join(key)}",
                function=_run,
                callback=_on_done,
                cancellable=False,
            )
        )


_loader: _FilmstripLoader | None = None


def _get_loader() -> _FilmstripLoader:
    global _loader
    if _loader is None:
        _loader = _FilmstripLoader()
    return _loader


class FilmstripOverlay(QtWidgets.QWidget):
    """Hover-scrub preview shown on top of a thumbnail widget.

    The overlay covers its *host* thumbnail and is only visible while a
    frame is shown, clipped like the image of the host. It tracks the
    cursor over the host by itself. Hosts that do not receive mouse events
    (e.g. table cell widgets transparent for mouse events) can be driven
    with :meth:`scrub` and :meth:`stop` instead.

    Args:
        host: Thumbnail widget to show the frames on.
        fit: ``"contain"`` or ``"cover"``, should match how the static
            thumbnail underneath is fitted.
        background: Fill behind the frame, e.g. to hide the static
            thumbnail when the aspect ratios differ.
    """

    def __init__(
        self,
        host: AYEntityThumbnail,
        fit: str = "contain",
        background: QtGui.QColor | None = None,
    ) -> None:
        super().__init__(host)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._fit = fit
        self._background = background
        self._source: _SourceKey | None = None
        self._data: FilmstripData | None = None
        self._position: float = 0.0
        self._hovering: bool = False
        # Source requested from the loader and not loaded yet
        self._pending: _SourceKey | None = None
        self._loader_connected: bool = False

        self._intent_timer = QtCore.QTimer(self)
        self._intent_timer.setSingleShot(True)
        self._intent_timer.setInterval(HOVER_INTENT_DELAY_MS)
        self._intent_timer.timeout.connect(self._request_load)

        self.hide()
        self.setGeometry(host.rect())
        host.setMouseTracking(True)
        host.installEventFilter(self)

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
        if not filmstrips_enabled():
            return
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
        self._intent_timer.stop()
        self._data = None
        self.hide()
        if self._pending is not None:
            _get_loader().release(self._pending)
            self._pending = None

    def _request_load(self) -> None:
        source = self._source
        if source is None or self._pending == source:
            return
        if not self._hovering:
            return
        self._pending = source
        loader = _get_loader()
        if not self._loader_connected:
            loader.loaded.connect(self._on_loaded)
            self._loader_connected = True
        loader.request(source)

    def _on_loaded(self, key: _SourceKey) -> None:
        if key != self._pending:
            return
        self._pending = None
        if not self._hovering:
            return
        entry = _peek_filmstrip(key)
        self._data = entry.data if entry is not None else None
        self.scrub(self._position)

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
        data = self._data
        if data is None:
            return
        index = min(int(self._position * data.frames), data.frames - 1)
        source = data.frame_rect(index)
        clip = self.parentWidget().get_image_clip_path()
        area = clip.boundingRect()
        if area.isEmpty() or source.isEmpty():
            return

        scales = (
            area.width() / source.width(),
            area.height() / source.height(),
        )
        scale = max(scales) if self._fit == "cover" else min(scales)
        target = QtCore.QRectF(
            0, 0, source.width() * scale, source.height() * scale
        )
        target.moveCenter(area.center())

        painter = QtGui.QPainter(self)
        painter.setRenderHint(
            QtGui.QPainter.RenderHint.SmoothPixmapTransform, True
        )
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        painter.setClipPath(clip)
        if self._background is not None:
            painter.fillRect(area, self._background)
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
        painter.end()


def get_card_filmstrip(card: AYEntityCard) -> FilmstripOverlay | None:
    """Return the hover-scrub preview of the thumbnail of a version card.

    Created on first use. The preview is driven by the card view: the
    chips overlay of the card covers the thumbnail and gets its mouse
    events. The source follows the card, which can be updated to show
    another version.

    Args:
        card: Card with ``"<project_name>/<version_id>/<thumbnail_id>"``
            as image source.

    Returns:
        ``None`` when the card shows no version.
    """
    parts = str(card.image_src).split("/", 2)
    if len(parts) != 3 or not parts[0] or not parts[1]:
        return None
    # TODO: 'AYEntityCard' should expose its thumbnail widget
    body = card._card_body
    filmstrip = body.findChild(FilmstripOverlay)
    if filmstrip is None:
        filmstrip = FilmstripOverlay(body, fit="cover")
    filmstrip.set_source(parts[0], "version", parts[1])
    return filmstrip
