"""Screenshot capture widget and handler for text box component.

Based on AYON core screenshot widget with proper DPI handling.
"""

from __future__ import annotations

import logging
import os
import tempfile
import uuid

from qtpy.QtCore import QObject, QPoint, QRect, Qt, QTimer, Signal
from qtpy.QtGui import (
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QScreen,
)
from qtpy.QtWidgets import QApplication, QWidget


logger = logging.getLogger(__name__)


class ScreenMarqueeDialog(QWidget):
    """Dialog for single screen marquee selection."""

    mouse_moved = Signal()
    mouse_pressed = Signal(QPoint, str)
    mouse_released = Signal(QPoint)
    close_requested = Signal()

    def __init__(self, screen: QScreen, screen_id: str):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.CustomizeWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        screen.geometryChanged.connect(self._fit_screen_geometry)

        self._screen = screen
        self._opacity = 100
        self._click_pos = None
        self._screen_id = screen_id

    def set_click_pos(self, pos):
        self._click_pos = pos
        self.repaint()

    def convert_end_pos(self, pos):
        glob_pos = self.mapFromGlobal(pos)
        new_pos = self._convert_pos(glob_pos)
        return self.mapToGlobal(new_pos)

    def paintEvent(self, event):
        """Paint event"""
        mouse_pos = self._convert_pos(self.mapFromGlobal(QCursor.pos()))
        rect = event.rect()
        fill_path = QPainterPath()
        fill_path.addRect(rect)

        capture_rect = None
        if self._click_pos is not None:
            click_pos = self.mapFromGlobal(self._click_pos)
            capture_rect = QRect(click_pos, mouse_pos)

            # Clear the capture area
            sub_path = QPainterPath()
            sub_path.addRect(capture_rect)
            fill_path = fill_path.subtracted(sub_path)

        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        # Draw background
        painter.setBrush(QColor(0, 0, 0, self._opacity))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(fill_path)

        # Draw cropping markers at current mouse position
        pen_color = QColor(255, 255, 255, self._opacity)
        pen = QPen(pen_color, 1, Qt.PenStyle.DotLine)
        painter.setPen(pen)
        painter.drawLine(
            rect.left(), mouse_pos.y(), rect.right(), mouse_pos.y()
        )
        painter.drawLine(
            mouse_pos.x(), rect.top(), mouse_pos.x(), rect.bottom()
        )

        # Draw rectangle around selection area
        if capture_rect is not None:
            pen_color = QColor(92, 173, 214)
            pen = QPen(pen_color, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            l_x = capture_rect.left()
            r_x = capture_rect.right()
            if l_x > r_x:
                l_x, r_x = r_x, l_x
            t_y = capture_rect.top()
            b_y = capture_rect.bottom()
            if t_y > b_y:
                t_y, b_y = b_y, t_y

            r_x -= 1
            b_y -= 1
            sel_rect = QRect(QPoint(l_x, t_y), QPoint(r_x, b_y))
            painter.drawRect(sel_rect)

        painter.end()

    def mousePressEvent(self, event):
        """Mouse click event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_pos = event.globalPos()
            self.mouse_pressed.emit(self._click_pos, self._screen_id)

    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._click_pos = None
            self.mouse_released.emit(event.globalPos())

    def mouseMoveEvent(self, event):
        """Mouse move event"""
        self.mouse_moved.emit()

    def keyPressEvent(self, event):
        """Key press event"""
        if event.key() == Qt.Key.Key_Escape:
            self._click_pos = None
            event.accept()
            self.close_requested.emit()
            return
        return super().keyPressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_screen_geometry()

    def closeEvent(self, event):
        self._click_pos = None
        super().closeEvent(event)

    def _convert_pos(self, pos):
        geo = self.geometry()
        if pos.x() > geo.width():
            pos.setX(geo.width() - 1)
        elif pos.x() < 0:
            pos.setX(0)

        if pos.y() > geo.height():
            pos.setY(geo.height() - 1)
        elif pos.y() < 0:
            pos.setY(0)
        return pos

    def _fit_screen_geometry(self):
        if hasattr(self, "setScreen"):
            self.setScreen(self._screen)
        self.setGeometry(self._screen.geometry())


class ScreenMarquee(QObject):
    """Screen marquee selection tool."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        screens_by_id = {}
        for screen in QApplication.screens():
            screen_id = uuid.uuid4().hex
            screen_dialog = ScreenMarqueeDialog(screen, screen_id)
            screens_by_id[screen_id] = screen_dialog
            screen_dialog.mouse_moved.connect(self._on_mouse_move)
            screen_dialog.mouse_pressed.connect(self._on_mouse_press)
            screen_dialog.mouse_released.connect(self._on_mouse_release)
            screen_dialog.close_requested.connect(self._on_close_request)

        self._screens_by_id = screens_by_id
        self._finished = False
        self._captured = False
        self._start_pos = None
        self._end_pos = None
        self._start_screen_id = None
        self._pix = None

    def get_captured_pixmap(self):
        if self._pix is None:
            return QPixmap()
        return self._pix

    def _close_dialogs(self):
        for dialog in self._screens_by_id.values():
            dialog.close()

    def _on_close_request(self):
        self._close_dialogs()
        self._finished = True

    def _on_mouse_release(self, pos):
        start_screen_dialog = self._screens_by_id.get(self._start_screen_id)
        if start_screen_dialog is None:
            self._finished = True
            self._captured = False
            return

        end_pos = start_screen_dialog.convert_end_pos(pos)
        self._close_dialogs()
        self._end_pos = end_pos
        self._finished = True
        self._captured = True

    def _on_mouse_press(self, pos, screen_id):
        self._start_pos = pos
        self._start_screen_id = screen_id

    def _on_mouse_move(self):
        for dialog in self._screens_by_id.values():
            dialog.repaint()

    def start_capture(self):
        for dialog in self._screens_by_id.values():
            dialog.show()
            dialog.setWindowState(Qt.WindowState.WindowActive)

        app = QApplication.instance()
        if app is not None:
            while not self._finished:
                app.processEvents()

            # Give time to close dialogs
            for _ in range(2):
                app.processEvents()
        else:
            logger.error(
                "No QApplication instance found. "
                "Capture may not work properly."
            )
            self._finished = True

        if self._captured:
            self._pix = self.get_desktop_pixmap(self._start_pos, self._end_pos)

    @classmethod
    def get_desktop_pixmap(cls, pos_start, pos_end):
        """Capture screen area between two points."""
        # Unify start and end points
        if pos_start.y() > pos_end.y():
            pos_start, pos_end = pos_end, pos_start

        if pos_start.x() > pos_end.x():
            new_start = QPoint(pos_end.x(), pos_start.y())
            new_end = QPoint(pos_start.x(), pos_end.y())
            pos_start = new_start
            pos_end = new_end

        # Validate rectangle
        rect = QRect(pos_start, pos_end)
        if rect.width() < 1 or rect.height() < 1:
            return QPixmap()

        screen = QApplication.screenAt(pos_start)
        if screen is None:
            return QPixmap()

        return screen.grabWindow(
            0,
            pos_start.x() - screen.geometry().x(),
            pos_start.y() - screen.geometry().y(),
            pos_end.x() - pos_start.x(),
            pos_end.y() - pos_start.y(),
        )

    @classmethod
    def capture_to_pixmap(cls):
        """Take screenshot with marquee into pixmap."""
        tool = cls()
        tool.start_capture()
        return tool.get_captured_pixmap()


class ScreenshotHandler:
    """Handles screenshot capture for text box."""

    def __init__(self, parent_widget, screenshot_button):
        """Initialize screenshot handler.

        Args:
            parent_widget: Parent widget instance (typically AYTextBox)
            screenshot_button: Screenshot button widget
        """
        self._parent = parent_widget
        self.screenshot_btn = screenshot_button
        self._pending_screenshots = []
        # Create a dedicated temp directory for this handler
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="ayon_screenshots_"
        )

    def launch_capture(self):
        """Launch screenshot capture tool."""
        main_window = self._parent.window()
        if main_window:
            main_window.showMinimized()

        QTimer.singleShot(200, self._show_snipping_widget)

    def _show_snipping_widget(self):
        """Show snipping widget after window is minimized."""
        pixmap = ScreenMarquee.capture_to_pixmap()
        self._on_screenshot_captured(pixmap)

    def _on_screenshot_captured(self, pixmap):
        """Handle captured screenshot."""
        if pixmap and not pixmap.isNull():
            screenshot_num = len(self._pending_screenshots) + 1
            temp_path = os.path.join(
                self._temp_dir.name, f"ss{screenshot_num}.jpg"
            )
            if pixmap.save(temp_path, "JPEG"):
                self._pending_screenshots.append(temp_path)

                # Add to parent's unified attachment system
                if hasattr(self._parent, "add_attachment"):
                    self._parent.add_attachment(temp_path, "screenshot")

                logger.debug("Screenshot attached: %s", temp_path)

        self._restore_window()

    def _restore_window(self):
        """Restore parent window."""
        main_window = self._parent.window()
        if main_window:
            main_window.showNormal()
            main_window.activateWindow()

    def get_screenshot_paths(self):
        """Get list of pending screenshot paths.

        Returns:
            list: List of screenshot file paths
        """
        return self._pending_screenshots.copy()

    def clear_screenshots(self):
        """Clear all pending screenshots and their files."""
        self._pending_screenshots.clear()
        # Recreate the temp dir (deletes old files)
        self._temp_dir.cleanup()
        self._temp_dir = tempfile.TemporaryDirectory(
            prefix="ayon_screenshots_"
        )

    def cleanup(self):
        """Delete all screenshot files. Call when handler is
        no longer needed."""
        self._pending_screenshots.clear()
        self._temp_dir.cleanup()
