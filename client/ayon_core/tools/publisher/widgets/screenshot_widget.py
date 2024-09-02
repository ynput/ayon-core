import os
import tempfile
import uuid

from qtpy import QtCore, QtGui, QtWidgets


class ScreenMarqueeDialog(QtWidgets.QDialog):
    mouse_moved = QtCore.Signal()
    mouse_pressed = QtCore.Signal(QtCore.QPoint, str)
    mouse_released = QtCore.Signal(QtCore.QPoint)
    close_requested = QtCore.Signal()

    def __init__(self, screen: QtCore.QObject, screen_id: str):
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.CustomizeWindowHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCursor(QtCore.Qt.CrossCursor)
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
        # Convert click and current mouse positions to local space.
        mouse_pos = self._convert_pos(self.mapFromGlobal(QtGui.QCursor.pos()))

        rect = event.rect()
        fill_path = QtGui.QPainterPath()
        fill_path.addRect(rect)

        capture_rect = None
        if self._click_pos is not None:
            click_pos = self.mapFromGlobal(self._click_pos)
            capture_rect = QtCore.QRect(click_pos, mouse_pos)

            # Clear the capture area
            sub_path = QtGui.QPainterPath()
            sub_path.addRect(capture_rect)
            fill_path = fill_path.subtracted(sub_path)

        painter = QtGui.QPainter(self)
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )

        # Draw background. Aside from aesthetics, this makes the full
        # tool region accept mouse events.
        painter.setBrush(QtGui.QColor(0, 0, 0, self._opacity))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPath(fill_path)

        # Draw cropping markers at current mouse position
        pen_color = QtGui.QColor(255, 255, 255, self._opacity)
        pen = QtGui.QPen(pen_color, 1, QtCore.Qt.DotLine)
        painter.setPen(pen)
        painter.drawLine(
            rect.left(), mouse_pos.y(),
            rect.right(), mouse_pos.y()
        )
        painter.drawLine(
            mouse_pos.x(), rect.top(),
            mouse_pos.x(), rect.bottom()
        )

        # Draw rectangle around selection area
        if capture_rect is not None:
            pen_color = QtGui.QColor(92, 173, 214)
            pen = QtGui.QPen(pen_color, 2)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            l_x = capture_rect.left()
            r_x = capture_rect.right()
            if l_x > r_x:
                l_x, r_x = r_x, l_x
            t_y = capture_rect.top()
            b_y = capture_rect.bottom()
            if t_y > b_y:
                t_y, b_y = b_y, t_y

            # -1 to draw 1px over the border
            r_x -= 1
            b_y -= 1
            sel_rect = QtCore.QRect(
                QtCore.QPoint(l_x, t_y),
                QtCore.QPoint(r_x, b_y)
            )
            painter.drawRect(sel_rect)

        painter.end()

    def mousePressEvent(self, event):
        """Mouse click event"""

        if event.button() == QtCore.Qt.LeftButton:
            # Begin click drag operation
            self._click_pos = event.globalPos()
            self.mouse_pressed.emit(self._click_pos, self._screen_id)

    def mouseReleaseEvent(self, event):
        """Mouse release event"""
        if event.button() == QtCore.Qt.LeftButton:
            # End click drag operation and commit the current capture rect
            self._click_pos = None
            self.mouse_released.emit(event.globalPos())

    def mouseMoveEvent(self, event):
        """Mouse move event"""
        self.mouse_moved.emit()

    def keyPressEvent(self, event):
        """Mouse press event"""
        if event.key() == QtCore.Qt.Key_Escape:
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
        # On macOs it is required to set screen explicitly
        if hasattr(self, "setScreen"):
            self.setScreen(self._screen)
        self.setGeometry(self._screen.geometry())


class ScreenMarquee(QtCore.QObject):
    """Dialog to interactively define screen area.

    This allows to select a screen area through a marquee selection.

    You can use any of its classmethods for easily saving an image,
    capturing to QClipboard or returning a QPixmap, respectively
    `capture_to_file`, `capture_to_clipboard` and `capture_to_pixmap`.
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)

        screens_by_id = {}
        for screen in QtWidgets.QApplication.screens():
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
            return QtGui.QPixmap()
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
            # Activate so Escape event is not ignored.
            dialog.setWindowState(QtCore.Qt.WindowActive)

        app = QtWidgets.QApplication.instance()
        while not self._finished:
            app.processEvents()

        # Give time to cloe dialogs
        for _ in range(2):
            app.processEvents()

        if self._captured:
            self._pix = self.get_desktop_pixmap(
                self._start_pos, self._end_pos
            )

    @classmethod
    def get_desktop_pixmap(cls, pos_start, pos_end):
        """Performs a screen capture on the specified rectangle.

        Args:
            pos_start (QtCore.QPoint): Start of screen capture.
            pos_end (QtCore.QPoint): End of screen capture.

        Returns:
            QtGui.QPixmap: Captured pixmap image

        """
        # Unify start and end points
        # - start is top left
        # - end is bottom right
        if pos_start.y() > pos_end.y():
            pos_start, pos_end = pos_end, pos_start

        if pos_start.x() > pos_end.x():
            new_start = QtCore.QPoint(pos_end.x(), pos_start.y())
            new_end = QtCore.QPoint(pos_start.x(), pos_end.y())
            pos_start = new_start
            pos_end = new_end

        # Validate if the rectangle is valid
        rect = QtCore.QRect(pos_start, pos_end)
        if rect.width() < 1 or rect.height() < 1:
            return QtGui.QPixmap()

        screen = QtWidgets.QApplication.screenAt(pos_start)
        return screen.grabWindow(
            0,
            pos_start.x() - screen.geometry().x(),
            pos_start.y() - screen.geometry().y(),
            pos_end.x() - pos_start.x(),
            pos_end.y() - pos_start.y()
        )
        # Multiscreen capture that does not work
        # - does not handle pixel aspect ratio and positioning of screens

        # most_left = None
        # most_top = None
        # for screen in QtWidgets.QApplication.screens():
        #     screen_geo = screen.geometry()
        #     if most_left is None or most_left > screen_geo.x():
        #         most_left = screen_geo.x()
        #
        #     if most_top is None or most_top > screen_geo.y():
        #         most_top = screen_geo.y()
        #
        # most_left = most_left or 0
        # most_top = most_top or 0
        #
        # screen_pixes = []
        # for screen in QtWidgets.QApplication.screens():
        #     screen_geo = screen.geometry()
        #     if not screen_geo.intersects(rect):
        #         continue
        #
        #     pos_l_x = screen_geo.x()
        #     pos_l_y = screen_geo.y()
        #     pos_r_x = screen_geo.x() + screen_geo.width()
        #     pos_r_y = screen_geo.y() + screen_geo.height()
        #     if pos_start.x() > pos_l_x:
        #         pos_l_x = pos_start.x()
        #
        #     if pos_start.y() > pos_l_y:
        #         pos_l_y = pos_start.y()
        #
        #     if pos_end.x() < pos_r_x:
        #         pos_r_x = pos_end.x()
        #
        #     if pos_end.y() < pos_r_y:
        #         pos_r_y = pos_end.y()
        #
        #     capture_pos_x = pos_l_x - screen_geo.x()
        #     capture_pos_y = pos_l_y - screen_geo.y()
        #     capture_screen_width = pos_r_x - pos_l_x
        #     capture_screen_height = pos_r_y - pos_l_y
        #     screen_pix = screen.grabWindow(
        #         0,
        #         capture_pos_x, capture_pos_y,
        #         capture_screen_width, capture_screen_height
        #     )
        #     paste_point = QtCore.QPoint(
        #         (pos_l_x - screen_geo.x()) - rect.x(),
        #         (pos_l_y - screen_geo.y()) - rect.y()
        #     )
        #     screen_pixes.append((screen_pix, paste_point))
        #
        # output_pix = QtGui.QPixmap(rect.width(), rect.height())
        # output_pix.fill(QtCore.Qt.transparent)
        # pix_painter = QtGui.QPainter()
        # pix_painter.begin(output_pix)
        # render_hints = (
        #     QtGui.QPainter.Antialiasing
        #     | QtGui.QPainter.SmoothPixmapTransform
        # )
        # if hasattr(QtGui.QPainter, "HighQualityAntialiasing"):
        #     render_hints |= QtGui.QPainter.HighQualityAntialiasing
        # pix_painter.setRenderHints(render_hints)
        # for item in screen_pixes:
        #     (screen_pix, offset) = item
        #     pix_painter.drawPixmap(offset, screen_pix)
        #
        # pix_painter.end()
        #
        # return output_pix

    @classmethod
    def capture_to_pixmap(cls):
        """Take screenshot with marquee into pixmap.

        Note:
            The pixmap can be invalid (use 'isNull' to check).

        Returns:
            QtGui.QPixmap: Captured pixmap image.
        """
        tool = cls()
        tool.start_capture()
        return tool.get_captured_pixmap()

    @classmethod
    def capture_to_file(cls, filepath=None):
        """Take screenshot with marquee into file.

        Args:
            filepath (Optional[str]): Path where screenshot will be saved.

        Returns:
            Union[str, None]: Path to the saved screenshot, or None if user
                cancelled the operation.
        """

        pixmap = cls.capture_to_pixmap()
        if pixmap.isNull():
            return None

        if filepath is None:
            with tempfile.NamedTemporaryFile(
                prefix="screenshot_", suffix=".png", delete=False
            ) as tmpfile:
                filepath = tmpfile.name

        else:
            output_dir = os.path.dirname(filepath)
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)

        pixmap.save(filepath)
        return filepath

    @classmethod
    def capture_to_clipboard(cls):
        """Take screenshot with marquee into clipboard.

        Notes:
            Screenshot is not in clipboard if user cancelled the operation.

        Returns:
            bool: Screenshot was added to clipboard.
        """

        clipboard = QtWidgets.QApplication.clipboard()
        pixmap = cls.capture_to_pixmap()
        if pixmap.isNull():
            return False
        image = pixmap.toImage()
        clipboard.setImage(image, QtGui.QClipboard.Clipboard)
        return True


def capture_to_pixmap():
    """Take screenshot with marquee into pixmap.

    Note:
        The pixmap can be invalid (use 'isNull' to check).

    Returns:
        QtGui.QPixmap: Captured pixmap image.
    """

    return ScreenMarquee.capture_to_pixmap()


def capture_to_file(filepath=None):
    """Take screenshot with marquee into file.

    Args:
        filepath (Optional[str]): Path where screenshot will be saved.

    Returns:
        Union[str, None]: Path to the saved screenshot, or None if user
            cancelled the operation.
    """

    return ScreenMarquee.capture_to_file(filepath)


def capture_to_clipboard():
    """Take screenshot with marquee into clipboard.

    Notes:
        Screenshot is not in clipboard if user cancelled the operation.

    Returns:
        bool: Screenshot was added to clipboard.
    """

    return ScreenMarquee.capture_to_clipboard()
