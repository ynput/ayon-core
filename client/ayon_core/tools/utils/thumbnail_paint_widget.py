import os
import subprocess
import sys
import tempfile

from qtpy import QtCore, QtGui, QtWidgets

try:
    from qtpy import QtMultimedia, QtMultimediaWidgets
    HAS_QTMULTIMEDIA = True
except ImportError:
    HAS_QTMULTIMEDIA = False

from ayon_core.style import get_objected_colors

from .images import get_image
from .lib import paint_image_with_color


class ThumbnailPainterWidget(QtWidgets.QWidget):
    """Widget for painting of thumbnails.

    The widget use is to paint thumbnail or multiple thumbnails in a defined
    area. Is not meant to show them in a grid but in overlay.

    It is expected that there is a logic that will provide thumbnails to
    paint and set them using 'set_current_thumbnails' or
    'set_current_thumbnail_paths'.
    """

    # Signal emitted when thumbnail is double-clicked
    thumbnail_double_clicked = QtCore.Signal(str)  # Emits the thumbnail path

    width_ratio = 3.0
    height_ratio = 2.0
    border_width = 1
    max_thumbnails = 3
    offset_sep = 4
    checker_boxes_count = 20

    def __init__(self, parent):
        super(ThumbnailPainterWidget, self).__init__(parent)

        border_color = get_objected_colors("bg-buttons").get_qcolor()
        thumbnail_bg_color = get_objected_colors("bg-view").get_qcolor()

        default_image = get_image("thumbnail.png")
        default_pix = paint_image_with_color(default_image, border_color)

        # Video player components
        self._media_player = None
        self._video_widget = None
        self._play_overlay_visible = True
        self._is_video_content = False
        self._current_video_path = None
        self._is_playing = False

        self._border_color = border_color
        self._thumbnail_bg_color = thumbnail_bg_color
        self._default_pix = default_pix

        self._cached_pix = None
        self._current_pixes = None
        self._has_pixes = False
        self._current_thumbnail_paths = None

        self._bg_color = QtCore.Qt.transparent
        self._use_checker = True
        self._checker_color_1 = QtGui.QColor(89, 89, 89)
        self._checker_color_2 = QtGui.QColor(188, 187, 187)

        # Enable mouse tracking and set focus policy to receive mouse events
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.ClickFocus)
        # Ensure the widget can receive mouse events
        self.setAttribute(QtCore.Qt.WA_MouseTracking, True)
        self.setAttribute(QtCore.Qt.WA_AcceptTouchEvents, False)

        self._setup_video_player()

    def _setup_video_player(self):
        """Setup video player components."""
        if not HAS_QTMULTIMEDIA:
            return

        try:
            # Qt6 API
            self._media_player = QtMultimedia.QMediaPlayer(self)
            self._video_widget = QtMultimediaWidgets.QVideoWidget(self)
            self._video_widget.hide()
            self._media_player.setVideoOutput(self._video_widget)

            # Loop video playback - Qt6 uses different signal
            self._media_player.mediaStatusChanged.connect(
                self._on_media_status_changed
            )
        except (AttributeError, TypeError):
            # Qt5 fallback
            try:
                self._media_player = QtMultimedia.QMediaPlayer(
                    self, QtMultimedia.QMediaPlayer.VideoSurface
                )
                self._video_widget = QtMultimediaWidgets.QVideoWidget(self)
                self._video_widget.hide()
                self._media_player.setVideoOutput(self._video_widget)

                # Loop video playback
                self._media_player.mediaStatusChanged.connect(
                    self._on_media_status_changed
                )
            except Exception as e:
                print(f"Failed to setup video player: {e}")
                self._media_player = None
                self._video_widget = None

    def _on_media_status_changed(self, status):
        """Handle media status changes for looping."""
        if not self._media_player:
            return

        # Qt6 uses QMediaPlayer.MediaStatus enum
        try:
            end_of_media = QtMultimedia.QMediaPlayer.MediaStatus.EndOfMedia
        except AttributeError:
            # Qt5 uses QMediaPlayer.EndOfMedia
            end_of_media = QtMultimedia.QMediaPlayer.EndOfMedia

        if status == end_of_media:
            self._media_player.setPosition(0)
            self._media_player.play()

    def _is_video_file(self, filepath):
        """Check if file is a video file (h264_*, mp4, mov, etc.)."""
        if not filepath:
            return False
        basename = os.path.basename(filepath).lower()
        # Check for h264_* naming convention
        if 'h264_' in basename or 'h264' in basename:
            return True
        # Check for common video extensions
        video_exts = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v')
        return any(filepath.lower().endswith(ext) for ext in video_exts)

    def _extract_first_frame(self, video_path):
        """Extract first frame from video for preview."""
        try:
            from ayon_core.lib import get_ffmpeg_tool_args, run_subprocess

            # Create temp file for frame
            temp_fd, frame_path = tempfile.mkstemp(
                suffix='.jpg', prefix='video_preview_'
            )
            os.close(temp_fd)

            # Extract first frame with ffmpeg
            cmd = get_ffmpeg_tool_args(
                "ffmpeg",
                "-i", video_path,
                "-vframes", "1",
                "-y",
                frame_path
            )

            run_subprocess(cmd)

            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                pix = QtGui.QPixmap(frame_path)
                # Cleanup temp file
                try:
                    os.remove(frame_path)
                except Exception:
                    pass
                return pix

        except Exception as e:
            print(f"Failed to extract first frame: {e}")

        return None

    def set_background_color(self, color):
        self._bg_color = color
        self.repaint()

    def set_use_checkboard(self, use_checker):
        if self._use_checker is use_checker:
            return
        self._use_checker = use_checker
        self.repaint()

    def set_checker_colors(self, color_1, color_2):
        self._checker_color_1 = color_1
        self._checker_color_2 = color_2
        self.repaint()

    def set_border_color(self, color):
        """Change border color.

        Args:
            color (QtGui.QColor): Color to set.
        """

        self._border_color = color
        self._default_pix = None
        self.clear_cache()

    def set_thumbnail_bg_color(self, color):
        """Change background color.

        Args:
            color (QtGui.QColor): Color to set.
        """

        self._thumbnail_bg_color = color
        self.clear_cache()

    @property
    def has_pixes(self):
        """Has set thumbnails.

        Returns:
            bool: True if widget has thumbnails to paint.
        """

        return self._has_pixes

    def clear_cache(self):
        """Clear cache of resized thumbnails and repaint widget."""

        self._cached_pix = None
        self.repaint()

    def set_current_thumbnails(self, pixmaps=None):
        """Set current thumbnails.

        Args:
            pixmaps (Optional[List[QtGui.QPixmap]]): List of pixmaps.
        """

        self._current_pixes = pixmaps or None
        self._has_pixes = self._current_pixes is not None
        self.clear_cache()

    def set_current_thumbnail_paths(self, thumbnail_paths=None):
        """Set current thumbnails with video detection.

        Set current thumbnails using paths to files. Detects video files
        and sets up video playback mode.

        Args:
            thumbnail_paths (Optional[List[str]]): List of paths to thumbnail
                sources.
        """
        self._current_thumbnail_paths = thumbnail_paths

        # Check if this is video content
        is_video = False
        video_path = None
        if thumbnail_paths and len(thumbnail_paths) > 0:
            first_path = thumbnail_paths[0]
            if self._is_video_file(first_path):
                is_video = True
                video_path = first_path

        self._is_video_content = is_video
        self._current_video_path = video_path

        if is_video and HAS_QTMULTIMEDIA:
            self._setup_video_display(video_path)
        else:
            self._setup_image_display(thumbnail_paths)

    def _setup_video_display(self, video_path):
        """Setup video display with first frame and play overlay."""
        if self._video_widget:
            self._video_widget.hide()
        self._is_playing = False
        self._play_overlay_visible = True

        # Extract first frame for preview
        first_frame_pix = self._extract_first_frame(video_path)
        if first_frame_pix:
            self._current_pixes = [first_frame_pix]
            self._has_pixes = True
        else:
            self._current_pixes = None
            self._has_pixes = False

        self.clear_cache()

    def _setup_image_display(self, thumbnail_paths):
        """Setup regular image display."""
        if self._video_widget:
            self._video_widget.hide()
        self._is_playing = False
        self._play_overlay_visible = False

        pixes = []
        if thumbnail_paths:
            for thumbnail_path in thumbnail_paths:
                pixes.append(QtGui.QPixmap(thumbnail_path))

        self.set_current_thumbnails(pixes)

    def paintEvent(self, event):
        if (
            self._is_playing
            and self._video_widget
            and self._video_widget.isVisible()
        ):
            # Video is playing, don't paint over it
            return

        if self._cached_pix is None:
            self._cache_pix()

        painter = QtGui.QPainter()
        painter.begin(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self._cached_pix)

        # Draw play overlay if video content and not playing
        if (
            self._is_video_content
            and self._play_overlay_visible
            and HAS_QTMULTIMEDIA
        ):
            self._draw_play_overlay(painter)

        painter.end()

    def _draw_play_overlay(self, painter):
        """Draw play button overlay."""
        rect = self.rect()

        # Semi-transparent background circle
        center_x = rect.width() // 2
        center_y = rect.height() // 2
        radius = min(rect.width(), rect.height()) // 8

        # Draw circle background
        painter.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 128)))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(
            QtCore.QPoint(center_x, center_y),
            radius,
            radius
        )

        # Draw play triangle
        triangle_size = radius // 2
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255, 230)))

        triangle = QtGui.QPolygon([
            QtCore.QPoint(
                center_x - triangle_size // 3,
                center_y - triangle_size
            ),
            QtCore.QPoint(
                center_x - triangle_size // 3,
                center_y + triangle_size
            ),
            QtCore.QPoint(
                center_x + triangle_size,
                center_y
            ),
        ])
        painter.drawPolygon(triangle)

    def resizeEvent(self, event):
        self._cached_pix = None
        if self._video_widget:
            self._video_widget.setGeometry(self.rect())
        super(ThumbnailPainterWidget, self).resizeEvent(event)

    def _get_default_pix(self):
        if self._default_pix is None:
            default_image = get_image("thumbnail")
            default_pix = paint_image_with_color(
                default_image, self._border_color
            )
            self._default_pix = default_pix
        return self._default_pix

    def _paint_tile(self, width, height):
        if not self._use_checker:
            tile_pix = QtGui.QPixmap(width, width)
            tile_pix.fill(self._bg_color)
            return tile_pix

        checker_size = int(float(width) / self.checker_boxes_count)
        if checker_size < 1:
            checker_size = 1

        checker_pix = QtGui.QPixmap(checker_size * 2, checker_size * 2)
        checker_pix.fill(QtCore.Qt.transparent)
        checker_painter = QtGui.QPainter()
        checker_painter.begin(checker_pix)
        checker_painter.setPen(QtCore.Qt.NoPen)
        checker_painter.setBrush(self._checker_color_1)
        checker_painter.drawRect(
            0, 0, checker_pix.width(), checker_pix.height()
        )
        checker_painter.setBrush(self._checker_color_2)
        checker_painter.drawRect(0, 0, checker_size, checker_size)
        checker_painter.drawRect(
            checker_size, checker_size, checker_size, checker_size
        )
        checker_painter.end()
        return checker_pix

    def _paint_default_pix(self, pix_width, pix_height):
        full_border_width = 2 * self.border_width
        width = pix_width - full_border_width
        height = pix_height - full_border_width
        if width > 100:
            width = int(width * 0.6)
            height = int(height * 0.6)

        scaled_pix = self._get_default_pix().scaled(
            width,
            height,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        pos_x = int((pix_width - scaled_pix.width()) / 2)
        pos_y = int((pix_height - scaled_pix.height()) / 2)
        new_pix = QtGui.QPixmap(pix_width, pix_height)
        new_pix.fill(QtCore.Qt.transparent)
        pix_painter = QtGui.QPainter()
        pix_painter.begin(new_pix)
        render_hints = (
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
        )

        pix_painter.setRenderHints(render_hints)
        pix_painter.drawPixmap(pos_x, pos_y, scaled_pix)
        pix_painter.end()
        return new_pix

    def _draw_thumbnails(self, thumbnails, pix_width, pix_height):
        full_border_width = 2 * self.border_width

        checker_pix = self._paint_tile(pix_width, pix_height)

        backgrounded_images = []
        for src_pix in thumbnails:
            scaled_pix = src_pix.scaled(
                pix_width - full_border_width,
                pix_height - full_border_width,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            pos_x = int((pix_width - scaled_pix.width()) / 2)
            pos_y = int((pix_height - scaled_pix.height()) / 2)

            new_pix = QtGui.QPixmap(pix_width, pix_height)
            new_pix.fill(QtCore.Qt.transparent)
            pix_painter = QtGui.QPainter()
            pix_painter.begin(new_pix)
            render_hints = (
                QtGui.QPainter.Antialiasing
                | QtGui.QPainter.SmoothPixmapTransform
            )
            pix_painter.setRenderHints(render_hints)

            tiled_rect = QtCore.QRectF(
                pos_x, pos_y, scaled_pix.width(), scaled_pix.height()
            )
            pix_painter.drawTiledPixmap(
                tiled_rect, checker_pix, QtCore.QPointF(0.0, 0.0)
            )
            pix_painter.drawPixmap(pos_x, pos_y, scaled_pix)
            pix_painter.end()
            backgrounded_images.append(new_pix)
        return backgrounded_images

    def _paint_dash_line(self, painter, rect):
        pen = QtGui.QPen()
        pen.setWidth(1)
        pen.setBrush(QtCore.Qt.darkGray)
        pen.setStyle(QtCore.Qt.DashLine)

        new_rect = rect.adjusted(1, 1, -1, -1)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.transparent)
        # painter.drawRect(rect)
        painter.drawRect(new_rect)

    def _cache_pix(self):
        rect = self.rect()
        rect_width = rect.width()
        rect_height = rect.height()

        pix_x_offset = 0
        pix_y_offset = 0
        expected_height = int(
            (rect_width / self.width_ratio) * self.height_ratio
        )
        if expected_height > rect_height:
            expected_height = rect_height
            expected_width = int(
                (rect_height / self.height_ratio) * self.width_ratio
            )
            pix_x_offset = (rect_width - expected_width) / 2
        else:
            expected_width = rect_width
            pix_y_offset = (rect_height - expected_height) / 2

        if self._current_pixes is None:
            used_default_pix = True
            pixes_to_draw = None
            pixes_len = 1
        else:
            used_default_pix = False
            pixes_to_draw = self._current_pixes
            if len(pixes_to_draw) > self.max_thumbnails:
                pixes_to_draw = pixes_to_draw[: -self.max_thumbnails]
            pixes_len = len(pixes_to_draw)

        width_offset, height_offset = self._get_pix_offset_size(
            expected_width, expected_height, pixes_len
        )
        pix_width = expected_width - width_offset
        pix_height = expected_height - height_offset

        if used_default_pix:
            thumbnail_images = [self._paint_default_pix(pix_width, pix_height)]
        else:
            thumbnail_images = self._draw_thumbnails(
                pixes_to_draw, pix_width, pix_height
            )

        if pixes_len == 1:
            width_offset_part = 0
            height_offset_part = 0
        else:
            width_offset_part = int(float(width_offset) / (pixes_len - 1))
            height_offset_part = int(float(height_offset) / (pixes_len - 1))
        full_width_offset = width_offset + pix_x_offset

        final_pix = QtGui.QPixmap(rect_width, rect_height)
        final_pix.fill(QtCore.Qt.transparent)

        bg_pen = QtGui.QPen()
        bg_pen.setWidth(self.border_width)
        bg_pen.setColor(self._border_color)

        final_painter = QtGui.QPainter()
        final_painter.begin(final_pix)
        render_hints = (
            QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform
        )

        final_painter.setRenderHints(render_hints)

        final_painter.setBrush(QtGui.QBrush(self._thumbnail_bg_color))
        final_painter.setPen(bg_pen)
        final_painter.drawRect(rect)

        for idx, pix in enumerate(thumbnail_images):
            x_offset = full_width_offset - (width_offset_part * idx)
            y_offset = (height_offset_part * idx) + pix_y_offset
            final_painter.drawPixmap(x_offset, y_offset, pix)

        # Draw drop enabled dashes
        if used_default_pix:
            self._paint_dash_line(final_painter, rect)

        final_painter.end()

        self._cached_pix = final_pix

    def _get_pix_offset_size(self, width, height, image_count):
        if image_count == 1:
            return 0, 0

        part_width = width / self.offset_sep
        part_height = height / self.offset_sep
        return part_width, part_height

    def mousePressEvent(self, event):
        """Handle single-click to toggle video playback."""
        if event.button() == QtCore.Qt.LeftButton:
            if (
                self._is_video_content
                and self._current_video_path
                and HAS_QTMULTIMEDIA
            ):
                self._toggle_video_playback()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Handle double-click to open file in default viewer."""
        if event.button() == QtCore.Qt.LeftButton:
            if self._current_thumbnail_paths:
                thumbnail_path = self._current_thumbnail_paths[0]
                if thumbnail_path and os.path.exists(thumbnail_path):
                    self.thumbnail_double_clicked.emit(thumbnail_path)
                    event.accept()
                    return

        # Always call the parent method
        super().mouseDoubleClickEvent(event)

    def _toggle_video_playback(self):
        """Toggle video playback on/off."""
        if not self._current_video_path or not self._media_player:
            return

        if self._is_playing:
            # Stop playback
            self._media_player.stop()
            if self._video_widget:
                self._video_widget.hide()
            self._is_playing = False
            self._play_overlay_visible = True
            self.repaint()
        else:
            # Start playback
            if self._video_widget:
                self._video_widget.setGeometry(self.rect())
                self._video_widget.show()
                self._video_widget.raise_()

            # Qt6 vs Qt5 API difference
            try:
                # Qt6 API - use setSource with QUrl
                self._media_player.setSource(
                    QtCore.QUrl.fromLocalFile(self._current_video_path)
                )
            except AttributeError:
                # Qt5 API - use setMedia with QMediaContent
                media_content = QtMultimedia.QMediaContent(
                    QtCore.QUrl.fromLocalFile(self._current_video_path)
                )
                self._media_player.setMedia(media_content)

            self._media_player.play()
            self._is_playing = True
            self._play_overlay_visible = False

    def _open_file_with_system_default(self, filepath):
        """Open file with system default executable (OS-agnostic).

        Args:
            filepath (str): Path to the file to open.
        """
        try:
            if sys.platform.startswith("darwin"):
                subprocess.call(("open", filepath))
            elif os.name == "nt":
                os.startfile(filepath)
            elif os.name == "posix":
                subprocess.call(("xdg-open", filepath))
        except Exception as e:
            # Log error but don't crash the application
            print(f"Failed to open file {filepath}: {e}")
