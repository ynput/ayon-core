from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.text_box import AYTextBox
from ayon_core.ui.preview.utils import Style, preview_widget


def build_text_box_preview_widget():
    w = AYContainer(layout=AYContainer.Layout.HBox, margin=8)
    ww = AYTextBox(
        parent=w, variant=AYTextBox.Variants.High, show_categories=True
    )
    ww.set_markdown(
        "## Title\nText can be **bold** or *italic*, as expected !\n"
        "- [ ] Do this\n- [ ] Do that\n"
    )
    w.add_widget(ww)
    ww.signals.comment_submitted.connect(
        lambda x, y: print(
            f"Comment [{y}] {'=' * (70 - len(y) - 2)}\n{x}{'=' * 78}"
        )
    )

    # Test adding attachments
    # ww.add_annotation_attachments(
    #     [
    #         {
    #             "file_path": "test1.png",
    #             "filename": "test_annotation1.png",
    #             "timestamp": 12345678,
    #         },
    #         {
    #             "file_path": "test2.png",
    #             "filename": "test_annotation2.png",
    #             "timestamp": 12345679,
    #         },
    #     ]
    # )

    return w


if __name__ == "__main__":
    preview_widget(
        build_text_box_preview_widget,
        style=Style.AYONStyle
    )
