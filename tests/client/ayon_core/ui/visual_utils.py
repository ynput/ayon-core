"""Shared helpers for visual regression tests."""

from __future__ import annotations

import glob
import io
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image
from qtpy.QtGui import QImage
from qtpy.QtWidgets import QWidget


def capture_widget(widget: QWidget) -> bytes:
    """Render widget to PNG bytes suitable for image_regression.check().

    Uses widget.grab() which works under offscreen rendering without needing
    a visible window handle.
    """
    pixmap = widget.grab()
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    ptr = image.bits()
    # PySide6 bits() returns a memoryview; convert to bytes.
    if hasattr(ptr, "tobytes"):
        data = ptr.tobytes()
    else:
        ptr.setsize(height * width * 4)
        data = bytes(ptr)
    arr = np.frombuffer(data, dtype=np.uint8).reshape((height, width, 4))
    pil_image = Image.fromarray(arr)
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


def accept_image_result(
    card: QWidget,
    test_img_path: str,
    ref_path: str,
    accept_btn: QWidget,
    callback: Callable,
) -> None:
    """Copy obtained image to reference path, enabling quick acceptance."""
    print(f"Accepting new result: {test_img_path} to {ref_path}")
    shutil.copy(test_img_path, ref_path)
    accept_btn.setEnabled(False)
    card.setProperty("accepted", True)
    callback()


def _make_image_card(
    test_name: str,
    test_img_path: str,
    ref_img_path: str,
    on_accepted: Callable,
):
    """Build one comparison card for show_images()."""
    from ayon_core.ui.components.buttons import AYButton
    from ayon_core.ui.components.check_box import AYCheckBox
    from ayon_core.ui.components.container import AYContainer
    from ayon_core.ui.components.label import AYLabel
    from qtpy.QtCore import Qt
    from qtpy.QtGui import QPixmap
    from qtpy.QtWidgets import QLabel, QStackedWidget

    card = AYContainer(
        variant=AYContainer.Variants.Low_Framed_Thin,
        layout=AYContainer.Layout.VBox,
        layout_margin=10,
        layout_spacing=10,
    )

    header = AYContainer(
        variant=AYContainer.Variants.Low,
        layout=AYContainer.Layout.HBox,
        layout_margin=0,
        layout_spacing=10,
    )
    title = AYLabel(test_name)
    title.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    show_ref_cb = AYCheckBox("Show reference")
    accept_btn = AYButton("Accept test", variant=AYButton.Variants.Danger)
    header.add_widget(title, stretch=1)
    header.add_widget(show_ref_cb)
    header.add_widget(accept_btn)
    card.add_widget(header)

    stack = QStackedWidget()
    for img_path in (test_img_path, ref_img_path):
        lbl = QLabel()
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            lbl.setText(f"[missing: {os.path.basename(img_path)}]")
        else:
            lbl.setPixmap(pixmap)
        stack.addWidget(lbl)
    card.add_widget(stack)

    is_same = test_img_path == ref_img_path
    show_ref_cb.setChecked(is_same)
    show_ref_cb.setEnabled(not is_same)
    accept_btn.setEnabled(not is_same)
    card.setProperty("accepted", is_same)

    if is_same:
        accept_btn.setToolTip("Test and reference images are the same.")
    else:
        show_ref_cb.checkStateChanged.connect(
            lambda state, s=stack: s.setCurrentIndex(
                1 if state == Qt.CheckState.Checked else 0
            )
        )
        dest_ref = str(
            Path(__file__).parent
            / "test_visual"
            / os.path.basename(ref_img_path)
        )
        accept_btn.clicked.connect(
            lambda _,
            c=card,
            p=test_img_path,
            r=dest_ref,
            w=accept_btn,
            cb=on_accepted: accept_image_result(c, p, r, w, cb)
        )

    return card


def show_images(*images: tuple[str, str, str]) -> None:
    """Show failed test images in a simple window for debugging.

    This is intended to be called from a subprocess after the test run, with
    paths to the obtained and reference images. It creates a simple Qt
    application that allows the user to view the obtained and reference images
    and optionally copy the obtained image to the reference location to accept
    the new result.

    Args:
        images: A list of tuples containing the test name, obtained image path,
            and reference image path.

    """
    from ayon_core.ui.components.check_box import AYCheckBox
    from ayon_core.ui.components.container import AYContainer
    from ayon_core.ui.components.line_edit import AYLineEdit
    from ayon_core.ui.components.scroll_area import AYScrollArea
    from ayon_core.ui.style import get_ayon_style
    from qtpy.QtCore import QSize
    from qtpy.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    app.setStyle(get_ayon_style())

    window = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        layout_margin=10,
        layout_spacing=10,
    )
    window.setWindowTitle("Image Comparison")
    window_lyt = window._layout

    search_lyt = AYContainer(
        layout=AYContainer.Layout.HBox,
        layout_margin=0,
        layout_spacing=10,
    )
    search_field = AYLineEdit(
        placeholder="Search images…", variant=AYLineEdit.Variants.Search_Field
    )
    search_field.setFixedHeight(search_field.sizeHint().height())
    search_lyt.add_widget(search_field)
    hide_accepted_cb = AYCheckBox("Hide accepted")
    search_lyt.add_widget(hide_accepted_cb)
    window_lyt.addWidget(search_lyt)

    scroll = AYScrollArea()
    scroll.setWidgetResizable(True)
    window_lyt.addWidget(scroll)

    root = AYContainer(
        variant=AYContainer.Variants.Low,
        layout=AYContainer.Layout.VBox,
        layout_margin=0,
        layout_spacing=10,
    )

    cards: list[tuple[str, QWidget]] = []

    def _apply_filters() -> None:
        print("Applying filters...")
        query = search_field.text().strip().lower()
        hide_accepted = hide_accepted_cb.isChecked()
        for card_name, card in cards:
            matches_query = not query or query in card_name.lower()
            matches_accept = not hide_accepted or not card.property("accepted")
            card.setVisible(matches_query and matches_accept)

    regressions = 0

    for name, *rest in sorted(images, key=lambda x: os.path.basename(x[0])):
        card = _make_image_card(name, *rest, on_accepted=_apply_filters)
        root.add_widget(card)
        cards.append((name, card))
        regressions += int(card.property("accepted") is False)

    if regressions > 0:
        window.setWindowTitle(f"Image Comparison - {regressions} regressions")

    root._layout.addStretch(1)
    scroll.setWidget(root)

    search_field.textChanged.connect(lambda _: _apply_filters())
    hide_accepted_cb.toggled.connect(lambda _: _apply_filters())
    _apply_filters()

    window.show()
    window.resize(root.sizeHint() + QSize(40, 40))
    app.exec()


if __name__ == "__main__":
    if sys.argv[1:]:
        if sys.argv[1] == "--show-refs" and len(sys.argv) == 2:
            # show all reference images in the refs directory for manual
            # inspection
            ref_dir = os.path.join(os.getcwd(), "tests", "test_visual")
            ref_images = glob.glob(os.path.join(ref_dir, "*.png"))
            images = [(os.path.basename(img), img, img) for img in ref_images]
            show_images(*images)
        else:
            show_images(*json.loads(sys.argv[1]))
    else:
        imgs = [
            (
                "checkbox initial",
                "./tests/foo/CheckBoxTest_00_initial.obtained.png",
                "./tests/foo/CheckBoxTest_00_initial.png",
            ),
        ]
        show_images(*imgs)
