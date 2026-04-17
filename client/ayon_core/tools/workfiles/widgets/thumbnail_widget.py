"""Workfile thumbnail UI (capture, paste, browse, clear)."""

from __future__ import annotations

import os
import uuid

from qtpy import QtCore, QtWidgets

from ayon_core.style import get_objected_colors
from ayon_core.lib.transcoding import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS

from ayon_core.tools.utils import paint_image_with_color, PixmapButton
from ayon_core.tools.publisher.widgets.thumbnail_widget import (
    ThumbnailPainterWidget,
    export_thumbnail,
)
from ayon_core.tools.publisher.widgets.screenshot_widget import capture_to_file
from ayon_core.tools.publisher.widgets.icons import get_image


class WorkfileThumbnailWidget(QtWidgets.QWidget):
    """Thumbnail UI for workfiles (screenshot, paste, browse, clear).

    Uses get_temp_dir_path() and optional message_callback. Emits
    thumbnail_created(path) and thumbnail_cleared.
    """

    thumbnail_created = QtCore.Signal(str)
    thumbnail_cleared = QtCore.Signal()

    def __init__(
        self,
        get_temp_dir_path,
        parent=None,
        message_callback=None,
        window_to_minimize=None,
        dialog_to_hide=None,
        post_capture_focus_widget=None,
    ):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._get_temp_dir_path = get_temp_dir_path
        self._message_callback = message_callback or (lambda _: None)
        self._window_to_minimize = window_to_minimize
        self._dialog_to_hide = dialog_to_hide
        self._post_capture_focus_widget = post_capture_focus_widget

        self._thumbnail_painter = ThumbnailPainterWidget(self)
        icon_color = get_objected_colors("bg-view-selection").get_qcolor()
        icon_color.setAlpha(255)

        buttons_widget = QtWidgets.QWidget(self)
        buttons_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        clear_image = get_image("clear_thumbnail")
        clear_pix = paint_image_with_color(clear_image, icon_color)
        self._clear_button = PixmapButton(clear_pix, buttons_widget)
        self._clear_button.setObjectName("ThumbnailPixmapHoverButton")
        self._clear_button.setToolTip("Clear thumbnail")

        take_screenshot_image = get_image("take_screenshot")
        take_screenshot_pix = paint_image_with_color(
            take_screenshot_image, icon_color
        )
        self._take_screenshot_btn = PixmapButton(
            take_screenshot_pix, buttons_widget
        )
        self._take_screenshot_btn.setObjectName("ThumbnailPixmapHoverButton")
        self._take_screenshot_btn.setToolTip("Take screenshot")

        paste_image = get_image("paste")
        paste_pix = paint_image_with_color(paste_image, icon_color)
        self._paste_btn = PixmapButton(paste_pix, buttons_widget)
        self._paste_btn.setObjectName("ThumbnailPixmapHoverButton")
        self._paste_btn.setToolTip("Paste from clipboard")

        browse_image = get_image("browse")
        browse_pix = paint_image_with_color(browse_image, icon_color)
        self._browse_btn = PixmapButton(browse_pix, buttons_widget)
        self._browse_btn.setObjectName("ThumbnailPixmapHoverButton")
        self._browse_btn.setToolTip("Browse...")

        buttons_layout = QtWidgets.QHBoxLayout(buttons_widget)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self._take_screenshot_btn, 0)
        buttons_layout.addWidget(self._paste_btn, 0)
        buttons_layout.addWidget(self._browse_btn, 0)
        buttons_layout.addWidget(self._clear_button, 0)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._thumbnail_painter)

        self._buttons_widget = buttons_widget
        self._clear_button.clicked.connect(self._on_clear_clicked)
        self._take_screenshot_btn.clicked.connect(self._on_take_screenshot)
        self._paste_btn.clicked.connect(self._on_paste_from_clipboard)
        self._browse_btn.clicked.connect(self._on_browse_clicked)

        self._review_extensions = set(IMAGE_EXTENSIONS) | set(VIDEO_EXTENSIONS)
        self._current_thumbnail_path = None
        self._clear_button.setEnabled(False)
        self.setMinimumSize(180, 120)

    def _get_output_dir(self):
        dirpath = self._get_temp_dir_path()
        if dirpath and not os.path.exists(dirpath):
            os.makedirs(dirpath)
        return dirpath or os.path.expanduser("~")

    def _get_filepath_from_event(self, event):
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            return None
        for url in mime_data.urls():
            filepath = url.toLocalFile()
            if os.path.exists(filepath):
                ext = os.path.splitext(filepath)[-1].lower()
                if ext in self._review_extensions:
                    return filepath
        return None

    def dragEnterEvent(self, event):
        if self._get_filepath_from_event(event):
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()

    def dragLeaveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        filepath = self._get_filepath_from_event(event)
        if not filepath:
            return
        output_dir = self._get_output_dir()
        output = export_thumbnail(filepath, output_dir)
        if output:
            self.set_current_thumbnails([output])
            self.thumbnail_created.emit(output)
        else:
            self._message_callback("Couldn't convert the source for thumbnail")

    def set_current_thumbnails(self, thumbnail_paths=None):
        self._thumbnail_painter.set_current_thumbnails(thumbnail_paths)
        if thumbnail_paths and len(thumbnail_paths) == 1:
            self._current_thumbnail_path = thumbnail_paths[0]
        else:
            self._current_thumbnail_path = None
        self._clear_button.setEnabled(
            thumbnail_paths is not None and len(thumbnail_paths) > 0
        )
        self._update_buttons_position()

    def set_thumbnail_path(self, path):
        """Load thumbnail from path (e.g. host capture shortcut)."""
        if path and os.path.isfile(path):
            self.set_current_thumbnails([path])
        else:
            self.set_current_thumbnails(None)

    def get_thumbnail_path(self):
        """Return current thumbnail path if set, else None."""
        return self._current_thumbnail_path

    def _update_buttons_position(self):
        size = self.size()
        my_width = size.width()
        my_height = size.height()
        buttons_sh = self._buttons_widget.sizeHint()
        buttons_height = buttons_sh.height()
        buttons_width = buttons_sh.width()
        pos_x = my_width - (buttons_width + 3)
        pos_y = my_height - (buttons_height + 3)
        if pos_x < 0:
            pos_x = 0
            buttons_width = my_width
        if pos_y < 0:
            pos_y = 0
            buttons_height = my_height
        self._buttons_widget.setGeometry(
            pos_x, pos_y, buttons_width, buttons_height
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_buttons_position()

    def showEvent(self, event):
        super().showEvent(event)
        self._update_buttons_position()

    def _on_clear_clicked(self):
        self._current_thumbnail_path = None
        self.set_current_thumbnails(None)
        self.thumbnail_cleared.emit()
        self._clear_button.setEnabled(False)

    def _schedule_screenshot_capture_focus(self, main_window, dialog):
        """Restore window stacking and focus after screenshot capture."""

        focus_widget = self._post_capture_focus_widget

        def _restore():
            if main_window is not None:
                main_window.raise_()
            if dialog is not None:
                dialog.raise_()
                dialog.activateWindow()
            if focus_widget is not None:
                focus_widget.setFocus(QtCore.Qt.OtherFocusReason)

        QtCore.QTimer.singleShot(0, _restore)

    def _on_take_screenshot(self):
        dialog = self._dialog_to_hide
        main_window = self._window_to_minimize
        dialog_prev_opacity = None
        main_prev_opacity = None
        masked_dialog = False
        masked_main = False
        app = QtWidgets.QApplication.instance()

        # Opacity instead of hide() keeps exec() modals valid on Qt/Windows.
        if dialog is not None and dialog.isVisible():
            dialog_prev_opacity = dialog.windowOpacity()
            dialog.setWindowOpacity(0.0)
            masked_dialog = True
        if main_window is not None and main_window.isVisible():
            main_prev_opacity = main_window.windowOpacity()
            main_window.setWindowOpacity(0.0)
            masked_main = True
        if app is not None:
            app.processEvents()
            app.processEvents()

        capture_owner = dialog if masked_dialog else None

        try:
            output_dir = self._get_output_dir()
            output_path = os.path.join(output_dir, uuid.uuid4().hex + ".png")
            if capture_to_file(output_path, owner=capture_owner):
                self.set_current_thumbnails([output_path])
                self.thumbnail_created.emit(output_path)
        finally:
            if masked_main and main_window is not None:
                main_window.setWindowOpacity(main_prev_opacity)
            if masked_dialog and dialog is not None:
                dialog.setWindowOpacity(dialog_prev_opacity)
            if app is not None:
                app.processEvents()
            if masked_main or masked_dialog:
                self._schedule_screenshot_capture_focus(main_window, dialog)

    def _on_paste_from_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        pixmap = clipboard.pixmap()
        if pixmap.isNull():
            return
        output_dir = self._get_output_dir()
        output_path = os.path.join(output_dir, uuid.uuid4().hex + ".png")
        if pixmap.save(output_path):
            self.set_current_thumbnails([output_path])
            self.thumbnail_created.emit(output_path)

    def _on_browse_clicked(self):
        ext_filter = "Source (*{0})".format(
            " *".join(self._review_extensions)
        )
        filepath, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Choose thumbnail", os.path.expanduser("~"), ext_filter
        )
        if not filepath:
            return
        ext = os.path.splitext(filepath)[-1].lower()
        if ext not in self._review_extensions:
            return
        output_dir = self._get_output_dir()
        output = export_thumbnail(filepath, output_dir)
        if output:
            self.set_current_thumbnails([output])
            self.thumbnail_created.emit(output)
        else:
            self._message_callback("Couldn't convert the source for thumbnail")
