from __future__ import annotations

from qtpy import QtWidgets

import ui_preview_setup  # noqa: F401

from ayon_core.ui.components.gallery_dialog import GalleryDialog
from ayon_core.ui.preview_utils import (
    Style,
    preview_widget,
    get_test_data_dir,
)


class _FakeDialog(QtWidgets.QDialog):
    def __init__(self, orig_close):
        super().__init__()
        self._orig_close = orig_close

    def closeEvent(self, event):
        self._orig_close(event)
        app = QtWidgets.QApplication.instance()
        app.exit(0)


def build_gallery_dialog_preview_widget():
    rsrc_dir = get_test_data_dir()
    images = []

    # Add any available test images
    for img_file in rsrc_dir.glob("*.jpg"):
        images.append((str(img_file), img_file.name))
    for img_file in rsrc_dir.glob("*.png"):
        images.append((str(img_file), img_file.name))

    dialog = GalleryDialog(images, current_index=0)
    # Because 'GallerDialog' is marked as tool it's closing does not trigger
    #   application close. So a fake dialog close event is used to trigger
    #   application exit when the dialog is closed.
    fake_dialog = _FakeDialog(dialog.closeEvent)
    dialog.closeEvent = fake_dialog.closeEvent
    return dialog


if __name__ == "__main__":
    preview_widget(
        build_gallery_dialog_preview_widget,
        style=Style.AYONStyleOverCSS
    )
