"""Thumbnail utilities and lazy-loading widgets for the reviews panel."""

from __future__ import annotations

import tempfile
from typing import TYPE_CHECKING, Callable

import ayon_api
from ayon_ui_qt.components.entity_thumbnail import AYEntityThumbnail
from ayon_ui_qt.components.task_queue import AsyncTask, get_task_queue
from ayon_ui_qt.image_cache import ImageCache
from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger, log_timing

if TYPE_CHECKING:
    from ._review_model import VisibilityAwarePaginatedTableModel

log = Logger.get_logger(__name__)


def _review_card_mapper(row_data: dict) -> dict:
    """Map a version row dict to the fields expected by AYEntityCard."""
    key: str = (
        f"{row_data.get('project_name', '')}/"
        f"{row_data.get('id', '')}/"
        f"{row_data.get('thumbnailId', '')}"
    )
    status_data = row_data.get("status")
    return {
        "header": row_data.get("folderName", ""),
        "title": row_data.get("productName", ""),
        "title_icon": row_data.get("productType__icon", ""),
        "title_color": row_data.get("productType__color", ""),
        "status": (
            {
                "name": "",
                "color": row_data.get("status__color", ""),
                "icon": row_data.get("status__icon", ""),
            }
            if status_data
            else None
        ),
        "version": row_data.get("version", "")
        + ("★" if row_data.get("heroVersionId") else ""),
        "image_src": key,
        "placeholder_icon": row_data.get("productType__icon", "image"),
    }


def _thumbnail_loader(key: str) -> str:
    """Fetch a version thumbnail from AYON and persist it to a temp file.

    Args:
        key: Cache key in the form
          ``"<project_name>/<version_id>/<thumbnail_id>"``.

    Returns:
        Absolute path to the saved image file, or empty string when the
        version has no thumbnail.
    """
    with log_timing(f"Fetching thumbnail for key {key}"):
        if not key:
            log.debug("  |_ No thumbnail key provided; skipping fetch")
            return ""

        ic = ImageCache.get_instance()

        def _fetch() -> str:
            log.debug("  |_ Cache miss; fetching from ayon API: %r", key)
            project_name, version_id, thumbnail_id = key.split("/", 2)
            content = ayon_api.get_version_thumbnail(
                project_name, version_id, thumbnail_id
            )
            if not content.is_valid:
                return ""
            ext = (
                ".jpg"
                if content.content_type and "jpeg" in content.content_type
                else ".png"
            )
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as fh:
                fh.write(content.content)
                return fh.name

        try:
            return ic.get(key, _fetch)
        except Exception:
            log.debug(
                "Failed to fetch thumbnail for key %r",
                key,
                exc_info=True,
            )
            return ""


def _make_card_async_fetcher(
    model: VisibilityAwarePaginatedTableModel,
) -> Callable[[str, Callable[[str], None]], None]:
    """Return an async thumbnail fetcher for use with ``AYEntityCard``.

    The returned callable matches the ``async_file_cacher`` signature
    expected by
    :class:`ayon_ui_qt.components.entity_thumbnail.AYEntityThumbnail`:
    ``(key: str, on_loaded: Callable[[str], None]) -> None``.

    On each call it enqueues an :class:`AsyncTask` on the shared task
    queue at priority 2.  If the key is already in ``ImageCache`` it
    calls ``on_loaded`` synchronously with the cached path.

    Args:
        model: The paginated table model; provides the current request
            context ID via :attr:`request_id`.

    Returns:
        A non-blocking fetcher callable suitable for
        ``AYEntityCard(async_file_cacher=...)``.
    """

    def _fetcher(key: str, on_loaded: Callable[[str], None]) -> None:
        parts = key.split("/", 2) if key else []
        if len(parts) != 3 or not all(parts):
            return

        ic = ImageCache.get_instance()
        if ic.has(key):
            cached = ic.get_path(key)
            if cached:
                on_loaded(cached)
            return

        get_task_queue().enqueue(
            AsyncTask(
                name=f"card_thumb_{key}",
                function=lambda k=key: _thumbnail_loader(k),
                callback=on_loaded,
                priority=2,
                context_id=model.request_id,
                cancellable=True,
            )
        )

    return _fetcher


class LazyThumbnailWidget(AYEntityThumbnail):
    """Thumbnail widget that defers loading until the first paint event.

    Persistent-editor widgets only receive ``paintEvent`` when they are
    within the viewport's visible area.  By deferring the async thumbnail
    fetch to the first paint, we avoid issuing network requests for
    off-screen rows.

    Args:
        key: ImageCache key in the form
            ``"<project>/<version_id>/<thumbnail_id>"``.
        context_id: Model request-ID used to scope the task-queue
            entry so stale tasks can be cancelled on model reset.
        size: ``(width, height)`` dimensions for the thumbnail.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        key: str,
        context_id: str,
        size: tuple[int, int] = (66, 32),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(size=size, parent=parent, fade_duration=500)
        self._thumb_key: str = key
        self._context_id: str = context_id
        self._load_requested: bool = False

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        """Load the thumbnail on the first paint, using the cache when hot.

        On the first paint event:

        1. Check ``ImageCache`` — if the image is already cached, call
           :meth:`set_thumbnail` synchronously and skip the async enqueue.
        2. Otherwise, enqueue an async fetch at priority 2.

        Args:
            event: The paint event forwarded to the parent class.
        """
        if not self._load_requested:
            self._load_requested = True
            ic = ImageCache.get_instance()
            cached_path = (
                ic.get_path(self._thumb_key) if self._thumb_key else None
            )
            if cached_path:
                with log_timing(
                    "Thumbnail sync-load for key %r" % self._thumb_key
                ):
                    self.set_thumbnail(cached_path)
            else:
                w = self

                def _on_thumb_loaded(_w, _fpath) -> None:
                    if not shiboken.isValid(_w):
                        return
                    _w.set_thumbnail(_fpath)

                get_task_queue().enqueue(
                    AsyncTask(
                        name=f"thumbnail_loader_{self._thumb_key}",
                        function=lambda: _thumbnail_loader(self._thumb_key),
                        callback=lambda fpath: _on_thumb_loaded(w, fpath),
                        priority=2,
                        context_id=self._context_id,
                    )
                )
        super().paintEvent(event)


class PlaceholderThumbnail(QtWidgets.QWidget):
    """Lightweight placeholder that creates the real thumbnail lazily.

    The widget returned by a ``widget_factory`` is instantiated by Qt as
    soon as ``openPersistentEditor`` is called, whether or not the row is
    visible.  This class acts as a near-zero-cost stand-in: construction
    costs a single ``QWidget`` allocation plus ``setFixedSize``.  The
    real :class:`LazyThumbnailWidget` is only created on the first
    ``paintEvent``, i.e. when the row actually scrolls into view.

    Args:
        make_real: Callable with no arguments that returns the real
            :class:`LazyThumbnailWidget` when invoked.
        alignment: Alignment flag for the widget.
        parent: Optional parent widget (viewport).
    """

    def __init__(
        self,
        make_real: Callable | None,
        alignment: QtCore.Qt.AlignmentFlag = (
            QtCore.Qt.AlignmentFlag.AlignLeft
        ),
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        self._make_real: Callable | None = make_real
        self._real: QtWidgets.QWidget | None = None
        self._lyt = None
        self._alignment = alignment

    def _create_layout(self) -> None:
        self._lyt = QtWidgets.QHBoxLayout()
        self._lyt.setContentsMargins(0, 0, 0, 0)
        self._lyt.setAlignment(self._alignment)
        self.setLayout(self._lyt)

    def paintEvent(  # type: ignore[override]
        self, event: QtGui.QPaintEvent
    ) -> None:
        """Materialise the real thumbnail widget on the first paint.

        Because ``paintEvent`` is only called when the widget is within
        the visible viewport, the real widget (and its expensive
        constructor) is never created for off-screen rows.

        Args:
            event: The paint event forwarded to the real widget.
        """
        if self._make_real and self._real is None:
            self._real = self._make_real()
            if self._real:
                self._create_layout()
                assert self._lyt is not None
                self._lyt.addWidget(self._real, stretch=1)
        super().paintEvent(event)
