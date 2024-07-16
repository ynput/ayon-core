import os

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import resources, style
from ayon_core.tools.utils import paint_image_with_color


class PixmapLabel(QtWidgets.QLabel):
    """Label resizing image to height of font."""
    def __init__(self, pixmap, parent):
        super(PixmapLabel, self).__init__(parent)
        self._empty_pixmap = QtGui.QPixmap(0, 0)
        self._source_pixmap = pixmap

    def set_source_pixmap(self, pixmap):
        """Change source image."""
        self._source_pixmap = pixmap
        self._set_resized_pix()

    def _get_pix_size(self):
        size = self.fontMetrics().height() * 3
        return size, size

    def _set_resized_pix(self):
        if self._source_pixmap is None:
            self.setPixmap(self._empty_pixmap)
            return
        width, height = self._get_pix_size()
        self.setPixmap(
            self._source_pixmap.scaled(
                width,
                height,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
        )

    def resizeEvent(self, event):
        self._set_resized_pix()
        super(PixmapLabel, self).resizeEvent(event)


class UpdateDialog(QtWidgets.QDialog):
    restart_requested = QtCore.Signal()
    ignore_requested = QtCore.Signal()

    _min_width = 400
    _min_height = 130

    def __init__(self, parent=None):
        super(UpdateDialog, self).__init__(parent)

        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setWindowTitle("AYON update")
        self.setWindowFlags(
            self.windowFlags()
            | QtCore.Qt.WindowStaysOnTopHint
        )

        self.setMinimumWidth(self._min_width)
        self.setMinimumHeight(self._min_height)

        top_widget = QtWidgets.QWidget(self)

        gift_pixmap = self._get_gift_pixmap()
        gift_icon_label = PixmapLabel(gift_pixmap, top_widget)

        label_widget = QtWidgets.QLabel(
            (
                "Your AYON needs to update."
                "<br/><br/>Please restart AYON launcher and all running"
                " applications as soon as possible."
            ),
            top_widget
        )
        label_widget.setWordWrap(True)

        top_layout = QtWidgets.QHBoxLayout(top_widget)
        top_layout.setSpacing(10)
        top_layout.addWidget(gift_icon_label, 0, QtCore.Qt.AlignCenter)
        top_layout.addWidget(label_widget, 1)

        ignore_btn = QtWidgets.QPushButton("Ignore", self)
        restart_btn = QtWidgets.QPushButton("Restart && Update", self)
        restart_btn.setObjectName("TrayRestartButton")

        btns_layout = QtWidgets.QHBoxLayout()
        btns_layout.addStretch(1)
        btns_layout.addWidget(ignore_btn, 0)
        btns_layout.addWidget(restart_btn, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(top_widget, 0)
        layout.addStretch(1)
        layout.addLayout(btns_layout, 0)

        ignore_btn.clicked.connect(self._on_ignore)
        restart_btn.clicked.connect(self._on_reset)

        self._label_widget = label_widget
        self._gift_icon_label = gift_icon_label
        self._ignore_btn = ignore_btn
        self._restart_btn = restart_btn

        self._restart_accepted = False
        self._current_is_higher = False

        self._close_silently = False

        self.setStyleSheet(style.load_stylesheet())

    def close_silently(self):
        self._close_silently = True
        self.close()

    def showEvent(self, event):
        super(UpdateDialog, self).showEvent(event)
        self._close_silently = False
        self._restart_accepted = False

    def closeEvent(self, event):
        super(UpdateDialog, self).closeEvent(event)
        if self._restart_accepted or self._current_is_higher:
            return

        if self._close_silently:
            return

        # Trigger ignore requested only if restart was not clicked and current
        #   version is lower
        self.ignore_requested.emit()

    def _on_ignore(self):
        self.reject()

    def _on_reset(self):
        self._restart_accepted = True
        self.restart_requested.emit()
        self.accept()

    def _get_gift_pixmap(self):
        image_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "images",
            "gifts.png"
        )
        src_image = QtGui.QImage(image_path)
        color_value = style.get_objected_colors("font")

        return paint_image_with_color(
            src_image,
            color_value.get_qcolor()
        )
