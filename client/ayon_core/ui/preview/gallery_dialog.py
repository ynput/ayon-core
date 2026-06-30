from __future__ import annotations

from ayon_core.ui.components.gallery_dialog import GalleryDialog
from ayon_core.ui.preview.utils import (
    Style,
    preview_widget,
    get_test_data_dir,
)


def build_gallery_dialog_preview_widget():
    rsrc_dir = get_test_data_dir()
    images = []

    # Add any available test images
    for img_file in rsrc_dir.glob("*.jpg"):
        images.append((str(img_file), img_file.name))
    for img_file in rsrc_dir.glob("*.png"):
        images.append((str(img_file), img_file.name))

    if not images:
        # Create dummy entries for testing
        images = [
            ("test1.png", "Test Image 1"),
            ("test2.png", "Test Image 2"),
        ]

    dialog = GalleryDialog(images, current_index=0)
    return dialog


if __name__ == "__main__":
    preview_widget(
        build_gallery_dialog_preview_widget,
        style=Style.AYONStyleOverCSS
    )
