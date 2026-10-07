"""Deferred entity thumbnails for item views.

Thumbnails are painted on the far right of an item by a delegate. Paths to
thumbnail files are received from a controller in a background thread, which
is also where the images are loaded and scaled, so the main thread only
paints prepared pixmaps.

The controller must implement 'get_thumbnail_paths' (see 'ThumbnailsModel'
in 'ayon_core.tools.common_models'), without it thumbnails are not shown.
"""
from __future__ import annotations

import time
import weakref
from typing import Any, Optional

from qtpy import QtWidgets, QtGui, QtCore, shiboken

from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.components.tree_view import TreeViewItemDelegate

# Entity ids requested from controller in one background task
_CHUNK_SIZE = 8


def _load_thumbnails(
    controller: Any,
    project_name: str,
    entity_type: str,
    entity_ids: set[str],
    loaded_paths: set[str],
    size: QtCore.QSize,
) -> tuple[dict[str, Optional[str]], dict[str, QtGui.QImage]]:
    """Receive thumbnail paths and load their images.

    Is called in a background thread, that is why 'QImage' is used instead
    of 'QPixmap' which can be used only in the main thread.

    Args:
        controller: Controller with 'get_thumbnail_paths' method.
        project_name: Project name.
        entity_type: Entity type, e.g. 'folder' or 'task'.
        entity_ids: Entity ids to receive thumbnails for.
        loaded_paths: Paths that are already loaded and can be skipped.
        size: Size of the output images in device pixels.

    Returns:
        Thumbnail path by entity id and loaded image by thumbnail path.
    """
    path_by_entity_id = controller.get_thumbnail_paths(
        project_name, entity_type, entity_ids
    )
    images_by_path = {}
    for path in set(path_by_entity_id.values()):
        if not path or path in loaded_paths:
            continue
        image = QtGui.QImage(path)
        if image.isNull():
            continue
        # Fill the whole area and crop what overflows
        image = image.scaled(
            size,
            QtCore.Qt.KeepAspectRatioByExpanding,
            QtCore.Qt.SmoothTransformation,
        )
        images_by_path[path] = image.copy(
            (image.width() - size.width()) // 2,
            (image.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )
    return path_by_entity_id, images_by_path


class EntityThumbnailsLoader(QtCore.QObject):
    """Load entity thumbnails in background threads.

    Thumbnails are loaded only on request using 'load', nothing is loaded
    upfront. Loaded pixmaps are kept in memory until the project changes.

    Args:
        controller: Controller of a tool. Thumbnails are available only
            if the controller has 'get_thumbnail_paths' method.
        entity_type: Entity type passed to the controller.
        thumbnail_size: Size of thumbnails in device independent pixels.
        parent: Parent object.
    """
    thumbnails_changed = QtCore.Signal(list)

    def __init__(
        self,
        controller: Any,
        entity_type: str,
        thumbnail_size: QtCore.QSize,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._entity_type = entity_type
        self._thumbnail_size = thumbnail_size
        self._project_name: Optional[str] = None
        # Used to cancel tasks and to ignore results of previous project
        self._context_id = ""
        self._context_counter = 0

        self._path_by_entity_id: dict[str, Optional[str]] = {}
        self._pixmap_by_path: dict[str, QtGui.QPixmap] = {}
        # Entity ids that have up-to-date path
        self._valid_ids: set[str] = set()
        self._loading_ids: set[str] = set()

    def is_available(self) -> bool:
        """Controller is able to provide thumbnails."""
        return hasattr(self._controller, "get_thumbnail_paths")

    def get_thumbnail_size(self) -> QtCore.QSize:
        return self._thumbnail_size

    def set_project_name(self, project_name: Optional[str]) -> None:
        """Change project, forget everything about the previous one."""
        if project_name == self._project_name:
            return
        self._project_name = project_name
        self._clear_tasks()
        self._path_by_entity_id = {}
        self._pixmap_by_path = {}
        self._valid_ids = set()
        self._loading_ids = set()

    def set_outdated(self) -> None:
        """Entities could change, validate thumbnails on next request.

        Already loaded thumbnails are still available, and are replaced
        only if the entity received a different thumbnail.
        """
        self._valid_ids = set()

    def needs_load(self, entity_id: str) -> bool:
        return (
            entity_id not in self._valid_ids
            and entity_id not in self._loading_ids
        )

    def get_pixmap(self, entity_id: str) -> Optional[QtGui.QPixmap]:
        """Loaded thumbnail of an entity.

        Returns:
            Thumbnail pixmap, or None if the entity does not have
                a thumbnail or it is not loaded yet.
        """
        path = self._path_by_entity_id.get(entity_id)
        if not path:
            return None
        return self._pixmap_by_path.get(path)

    def load(self, entity_ids: set[str], device_pixel_ratio: float) -> None:
        """Load thumbnails of entities in background threads.

        Signal 'thumbnails_changed' is emitted when thumbnails of entities
        become available or change.

        Args:
            entity_ids: Entity ids to load thumbnails for.
            device_pixel_ratio: Pixel ratio of the screen thumbnails are
                painted on.
        """
        if not self._project_name or not self.is_available():
            return
        entity_ids = {
            entity_id
            for entity_id in entity_ids
            if self.needs_load(entity_id)
        }
        if not entity_ids:
            return

        if not self._context_id:
            self._context_counter += 1
            self._context_id = (
                f"entity_thumbnails_{id(self)}_{self._context_counter}"
            )
        self._loading_ids |= entity_ids

        size = self._thumbnail_size * device_pixel_ratio
        loaded_paths = set(self._pixmap_by_path)
        task_queue = get_task_queue()
        remaining_ids = list(entity_ids)
        while remaining_ids:
            chunk_ids = set(remaining_ids[:_CHUNK_SIZE])
            remaining_ids = remaining_ids[_CHUNK_SIZE:]
            task_queue.enqueue(AsyncTask(
                name=f"entity_thumbnails_{self._entity_type}",
                function=_LoadCallable(
                    self._controller,
                    self._project_name,
                    self._entity_type,
                    chunk_ids,
                    loaded_paths,
                    size,
                ),
                callback=_LoadedCallback(
                    self, self._context_id, chunk_ids, device_pixel_ratio
                ),
                priority=10,
                context_id=self._context_id,
            ))

    def _clear_tasks(self) -> None:
        context_id, self._context_id = self._context_id, ""
        if context_id:
            get_task_queue().clear_context_tasks(context_id)

    def _on_loaded(
        self,
        context_id: str,
        entity_ids: set[str],
        device_pixel_ratio: float,
        result: Optional[
            tuple[dict[str, Optional[str]], dict[str, QtGui.QImage]]
        ],
    ) -> None:
        # Result of a previous project
        if context_id != self._context_id:
            return

        self._loading_ids -= entity_ids
        # Do not try again until next refresh, even if the load failed
        self._valid_ids |= entity_ids
        if result is None:
            return

        path_by_entity_id, images_by_path = result
        for path, image in images_by_path.items():
            pixmap = QtGui.QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(device_pixel_ratio)
            self._pixmap_by_path[path] = pixmap

        changed_ids = []
        for entity_id in entity_ids:
            path = path_by_entity_id.get(entity_id)
            if path not in self._pixmap_by_path:
                path = None
            if self._path_by_entity_id.get(entity_id) != path:
                changed_ids.append(entity_id)
            self._path_by_entity_id[entity_id] = path

        if changed_ids:
            self.thumbnails_changed.emit(changed_ids)


class _LoadCallable:
    """Function of a task that does not keep reference to the loader."""

    def __init__(self, *args) -> None:
        self._args = args

    def __call__(
        self
    ) -> tuple[dict[str, Optional[str]], dict[str, QtGui.QImage]]:
        return _load_thumbnails(*self._args)


class _LoadedCallback:
    """Task callback which ignores the result if the loader was deleted."""

    def __init__(self, loader: EntityThumbnailsLoader, *args) -> None:
        self._loader_ref = weakref.ref(loader)
        self._args = args

    def __call__(self, result) -> None:
        loader = self._loader_ref()
        if loader is not None and shiboken.isValid(loader):
            loader._on_loaded(*self._args, result)


class EntityThumbnailsPainter(QtCore.QObject):
    """Paint entity thumbnails on the far right of view items.

    Helper for item delegates. A thumbnail is requested the first time its
    item is painted, so only thumbnails of items the user really sees are
    loaded. Loaded thumbnails fade in.

    Args:
        view: View where the thumbnails are painted.
        controller: Controller of a tool, see 'EntityThumbnailsLoader'.
        entity_type: Entity type of the view items.
        entity_id_role: Item data role with an entity id.
        thumbnail_height: Height of thumbnails in pixels.
    """
    fade_duration = 400  # In milliseconds
    aspect_ratio = 16 / 9
    # Space around the thumbnail
    margin = 4
    radius = 2
    # Thumbnail is hidden if less width would be left for icon and label
    min_label_width = 90
    # Wait for more items to be painted, e.g. when scrolling
    _request_delay = 50

    def __init__(
        self,
        view: QtWidgets.QAbstractItemView,
        controller: Any,
        entity_type: str,
        entity_id_role: int,
        thumbnail_height: int = 20,
    ) -> None:
        super().__init__(view)
        loader = EntityThumbnailsLoader(
            controller,
            entity_type,
            QtCore.QSize(
                round(thumbnail_height * self.aspect_ratio), thumbnail_height
            ),
            parent=self,
        )

        request_timer = QtCore.QTimer(self)
        request_timer.setSingleShot(True)
        request_timer.setInterval(self._request_delay)

        fade_timer = QtCore.QTimer(self)
        fade_timer.setInterval(16)

        loader.thumbnails_changed.connect(self._on_thumbnails_changed)
        request_timer.timeout.connect(self._on_request_timer)
        fade_timer.timeout.connect(self._on_fade_timer)

        self._view = view
        self._loader = loader
        self._entity_id_role = entity_id_role
        self._enabled = loader.is_available()
        self._request_timer = request_timer
        self._fade_timer = fade_timer
        self._fade_curve = QtCore.QEasingCurve(QtCore.QEasingCurve.InOutQuad)
        self._requested: dict[str, QtCore.QPersistentModelIndex] = {}
        self._fade_start_by_id: dict[str, float] = {}

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Show or hide thumbnails.

        Thumbnails cannot be enabled if the controller does not support
        them.
        """
        enabled = enabled and self._loader.is_available()
        if enabled == self._enabled:
            return
        self._enabled = enabled
        self._requested = {}
        self._view.viewport().update()

    def set_project_name(self, project_name: Optional[str]) -> None:
        """Set project of entities in the view.

        Should be called on each refresh of the view, so changed thumbnails
        are updated.
        """
        self._requested = {}
        self._loader.set_project_name(project_name)
        self._loader.set_outdated()
        self._view.viewport().update()

    def get_reserved_width(
        self, item_rect: QtCore.QRect, index: QtCore.QModelIndex
    ) -> int:
        """Width of the item that should be kept free for the thumbnail.

        Args:
            item_rect: Rectangle of the item.
            index: Index of the item.

        Returns:
            Width in pixels, 0 if the thumbnail is not painted.
        """
        if not self._enabled:
            return 0
        entity_id = index.data(self._entity_id_role)
        if not entity_id or self._loader.get_pixmap(entity_id) is None:
            return 0
        rect = self._get_thumbnail_rect(item_rect)
        if rect.isEmpty():
            return 0
        return rect.width() + self.margin

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        """Paint the thumbnail of an item, request it if is not loaded.

        Args:
            painter: Painter of the item.
            option: Style option of the item.
            index: Index of the item.
        """
        if not self._enabled:
            return
        entity_id = index.data(self._entity_id_role)
        if not entity_id:
            return

        if self._loader.needs_load(entity_id):
            self._requested[entity_id] = QtCore.QPersistentModelIndex(index)
            if not self._request_timer.isActive():
                self._request_timer.start()

        pixmap = self._loader.get_pixmap(entity_id)
        if pixmap is None:
            return

        rect = self._get_thumbnail_rect(option.rect)
        if rect.isEmpty():
            return

        opacity = self._get_opacity(entity_id)
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), self.radius, self.radius)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        painter.setClipPath(path, QtCore.Qt.IntersectClip)
        painter.setOpacity(painter.opacity() * opacity)
        painter.drawPixmap(rect, pixmap)
        painter.restore()

    def _get_thumbnail_rect(self, item_rect: QtCore.QRect) -> QtCore.QRect:
        size = QtCore.QSize(self._loader.get_thumbnail_size())
        # Keep at least 1px above and below the thumbnail
        max_height = item_rect.height() - 2
        if size.height() > max_height:
            size = QtCore.QSize(
                round(max_height * self.aspect_ratio), max_height
            )
        rect = QtCore.QRect(QtCore.QPoint(0, 0), size)
        rect.moveCenter(item_rect.center())
        rect.moveRight(item_rect.right() - self.margin)
        # Label is more important than the thumbnail in narrow items
        if rect.left() - item_rect.left() < self.min_label_width:
            return QtCore.QRect()
        return rect

    def _get_opacity(self, entity_id: str) -> float:
        fade_start = self._fade_start_by_id.get(entity_id)
        if fade_start is None:
            return 1.0
        progress = (
            (time.monotonic() - fade_start) * 1000 / self.fade_duration
        )
        if progress >= 1.0:
            return 1.0
        return self._fade_curve.valueForProgress(max(progress, 0.0))

    def _on_request_timer(self) -> None:
        requested, self._requested = self._requested, {}
        # Items could be scrolled away, collapsed or removed in the meantime
        viewport_rect = self._view.viewport().rect()
        entity_ids = set()
        for entity_id, index in requested.items():
            if not index.isValid():
                continue
            # Explicit conversion, not all Qt bindings do it implicitly
            rect = self._view.visualRect(
                index.model().index(
                    index.row(), index.column(), index.parent()
                )
            )
            if rect.isValid() and rect.intersects(viewport_rect):
                entity_ids.add(entity_id)

        if entity_ids:
            self._loader.load(entity_ids, self._view.devicePixelRatioF())

    def _on_thumbnails_changed(self, entity_ids: list[str]) -> None:
        fade_start = time.monotonic()
        for entity_id in entity_ids:
            if self._loader.get_pixmap(entity_id) is not None:
                self._fade_start_by_id[entity_id] = fade_start
        if self._fade_start_by_id and not self._fade_timer.isActive():
            self._fade_timer.start()
        self._view.viewport().update()

    def _on_fade_timer(self) -> None:
        fade_end = time.monotonic() - (self.fade_duration / 1000)
        for entity_id, fade_start in tuple(self._fade_start_by_id.items()):
            if fade_start <= fade_end:
                self._fade_start_by_id.pop(entity_id)
        if not self._fade_start_by_id:
            self._fade_timer.stop()
        self._view.viewport().update()


class EntityThumbnailDelegate(TreeViewItemDelegate):
    """Delegate for 'AYTreeView' painting entity thumbnails on the right.

    Args:
        thumbnails_painter: Painter of the thumbnails.
        **kwargs: Arguments of 'TreeViewItemDelegate'.
    """

    def __init__(
        self,
        thumbnails_painter: EntityThumbnailsPainter,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._thumbnails_painter = thumbnails_painter

    def _get_reserved_right_width(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> int:
        return self._thumbnails_painter.get_reserved_width(
            option.rect, index
        )

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        self._thumbnails_painter.paint(painter, option, index)
