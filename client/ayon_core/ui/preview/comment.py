from __future__ import annotations

from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.text_box import AYTextBox
from ayon_core.ui.components.comment import AYComment
from ayon_core.ui.data_models import CommentModel
from ayon_core.ui.preview.utils import (
    Style,
    preview_widget,
    get_test_data_dir,
)


def build_comment_preview_widget():
    rsrc_dir = get_test_data_dir()
    av1 = rsrc_dir / "avatar1.jpg" if rsrc_dir else ""
    av2 = rsrc_dir / "avatar2.jpg" if rsrc_dir else ""

    w = AYContainer(
        layout=AYContainer.Layout.VBox,
        variant=AYContainer.Variants.Low,
        # margin=8,
        layout_spacing=8,
        layout_margin=16,
    )

    w.add_widget(
        AYComment(
            data=CommentModel(
                user_src=str(av1),
                user_full_name="Bob Morane",
                comment=(
                    "Text Styling\n"
                    "------------\n"
                    "regular, **bold**, *italic*, ***bold italic*** "
                    "and `some code` text.\n\n"
                    "[A link](https://www.google.com)\n\n"
                    "```\n"
                    "# A code fragment\n"
                    "print('Hello World')\n"
                    "```\n\n"
                    "1. First item\n"
                    "2. Second item\n"
                    "3. Third item\n\n"
                    "Is it all working ?\n"
                ),
            )
        )
    )
    w.add_widget(
        AYComment(
            data=CommentModel(
                user_src=(str(av2)),
                user_full_name="Leia Organa",
                comment="Can you avoid the dark side @Luke ?",
                category="Review",
                category_color="#44ee9f",
            )
        )
    )
    w.add_widget(
        AYComment(
            data=CommentModel(
                user_full_name="Katniss Evergreen",
                comment=(
                    "Please check "
                    "[this link]"
                    "(https://doc.qt.io/qt-6/qtextdocument.html)\n\n"
                    "or [that one]"
                    "(https://doc.qt.io/qt-6/qtextblock.html#details) "
                    "if need be. "
                    "maybe [a last URL]"
                    "(https://doc.qt.io/qt-6/qtextblock.html#details) ?"
                ),
            )
        )
    )

    # Test checkbox functionality
    checklist_comment = AYComment(
        data=CommentModel(
            user_full_name="Task Manager",
            comment=(
                "Review checklist:\n"
                "- [x] Check animation timing\n"
                "- [ ] Review color grading\n"
                "- [ ] Verify audio sync\n"
                "- [x] Approve final render"
            ),
            category="Checklist",
            category_color="#5599ff",
        )
    )
    # Connect to log checkbox changes
    checklist_comment.text_field.checklist_changed.connect(
        lambda: print(
            "Checkbox changed! New markdown:\n"
            + checklist_comment.text_field.as_markdown()
        )
    )
    w.add_widget(checklist_comment)

    tb = AYTextBox(num_lines=10, variant=AYTextBox.Variants.High)
    w.add_widget(tb)
    tb.signals.comment_submitted.connect(
        lambda *args: print(
            "Comment submitted: "
            f"{'=' * (80 - len('Comment submitted: '))}\n",
            f"{args[0]}",
            f"{'-' * 80}\n",
            f"   markdown: {args[0]!r}\n",
            f"   category: {args[1]!r}\n",
            f"attachments: {args[2]}\n",
            f"{'-' * 80}\n",
        )
    )

    return w


if __name__ == "__main__":
    preview_widget(
        build_comment_preview_widget,
        style=Style.AYONStyleOverCSS
    )
