"""Tests for mentioning users, versions and tasks in comments."""

from __future__ import annotations

import pytest
from qtpy.QtCore import QMimeData, Qt
from qtpy.QtGui import QColor, QImage, QPainter, QTextCursor
from qtpy.QtWidgets import QStyleOptionViewItem

from ayon_core.ui.components.comment import AYComment, AYCommentField
from ayon_core.ui.components.comment_completion import (
    mentions_to_display,
    mentions_to_storage,
)
from ayon_core.ui.components.text_box import AYTextBox, AYTextEditor
from ayon_core.ui.data_models import CommentModel, EntityMention, User

USERS = [
    User("bigroy", "RN", "Roy Nieterau", ""),
    User("admin", "AA", "Ayon admin", ""),
]
VERSIONS = [
    EntityMention("version", "v3id", "v003", "renderMain"),
    EntityMention("version", "v2id", "v002", "renderMain"),
    EntityMention("version", "w1id", "v001", "workfileCompositing"),
]
TASKS = [
    EntityMention("task", "t1id", "compositing", "sh010"),
    EntityMention("task", "t2id", "lighting", "sh010"),
]

STORED = (
    "Hey [Roy Nieterau](user:bigroy) see [v003](version:v3id)"
    " for [compositing](task:t1id)"
)
DISPLAYED = (
    "Hey [@Roy Nieterau](user:bigroy) see [@@v003](version:v3id)"
    " for [@@@compositing](task:t1id)"
)


@pytest.fixture
def editor(qtbot) -> AYTextEditor:
    widget = AYTextEditor(num_lines=4, user_list=USERS)
    widget.set_mention_entities(VERSIONS, TASKS)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _completions(editor: AYTextEditor) -> list[str]:
    completer = editor._mentions._completer
    if not editor._mentions.popup_visible():
        return []
    model = completer.completionModel()
    return [model.index(row, 0).data() for row in range(model.rowCount())]


def _markdown(editor: AYTextEditor | AYCommentField) -> str:
    """Markdown of the editor on a single line."""
    # Qt marks the text as code when the application font set by a previous
    # test happens to be monospace.
    return " ".join(editor.as_markdown().replace("`", "").split())


def test_mentions_to_display():
    assert mentions_to_display(STORED) == DISPLAYED
    # Regular links are untouched
    md = "[site](https://ynput.io) [mail](mailto:a@b.c)"
    assert mentions_to_display(md) == md


def test_mentions_to_storage():
    assert mentions_to_storage(DISPLAYED) == STORED
    assert mentions_to_storage(STORED) == STORED
    # Label wrapped over two lines by Qt's markdown writer
    assert (
        mentions_to_storage("[@Roy\nNieterau](user:bigroy)")
        == "[Roy Nieterau](user:bigroy)"
    )


@pytest.mark.parametrize(
    "md",
    [
        # Name of a user typed without picking it from the completer
        "Hi @Roy Nieterau!",
        "mail roy@Ayon admin.com or bob@admin.com",
        "@@v003 and @@@compositing",
        "```\n@Roy Nieterau\n```",
        "`@Ayon admin`",
    ],
    ids=["name", "mail", "entities", "code_block", "inline_code"],
)
def test_typed_text_is_not_a_mention(md):
    assert mentions_to_storage(md) == md
    assert mentions_to_display(md) == md


def test_typed_name_is_stored_as_text(qtbot, editor):
    qtbot.keyClicks(editor, "Hi @Roy Nieterau")
    # Close the popup without picking the user
    qtbot.keyClick(editor._mentions._completer.popup(), Qt.Key.Key_Escape)
    qtbot.keyClicks(editor, " and bob@admin.com")

    assert _markdown(editor) == "Hi @Roy Nieterau and bob@admin.com"
    # Only picked mentions are highlighted as mention
    editor._mentions._highlighter.rehighlight()
    assert _format_ranges(editor) == []


@pytest.mark.parametrize(
    "typed, expected",
    [
        ("@", ["Roy Nieterau", "Ayon admin"]),
        ("@adm", ["Ayon admin"]),
        ("@@", [
            "renderMain v003",
            "renderMain v002",
            "workfileCompositing v001",
        ]),
        ("@@v002", ["renderMain v002"]),
        ("@@workfile", ["workfileCompositing v001"]),
        ("@@@", ["sh010 compositing", "sh010 lighting"]),
        ("@@@light", ["sh010 lighting"]),
        ("see (@@@comp", ["sh010 compositing"]),
        # No completions
        ("@@@@", []),
        ("mail@adm", []),
        ("@nobody", []),
        ("@@ ", []),
    ],
)
def test_completions_per_trigger(qtbot, editor, typed, expected):
    qtbot.keyClicks(editor, typed)
    assert _completions(editor) == expected


@pytest.mark.parametrize(
    "typed, text, markdown",
    [
        ("@roy", "@Roy Nieterau ", "[Roy Nieterau](user:bigroy)"),
        ("@@v002", "@@v002 ", "[v002](version:v2id)"),
        ("@@@light", "@@@lighting ", "[lighting](task:t2id)"),
    ],
    ids=["user", "version", "task"],
)
def test_pick_mention(qtbot, editor, typed, text, markdown):
    qtbot.keyClicks(editor, f"Check {typed}")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert not editor._mentions.popup_visible()
    assert editor.toPlainText() == f"Check {text}"
    assert _markdown(editor) == f"Check {markdown}"

    # Text typed after the mention is not part of the link
    qtbot.keyClicks(editor, "please")
    assert _markdown(editor) == f"Check {markdown} please"


def test_pick_mention_with_arrow_keys(qtbot, editor):
    qtbot.keyClicks(editor, "@@")
    popup = editor._mentions._completer.popup()
    qtbot.keyClick(popup, Qt.Key.Key_Down)
    qtbot.keyClick(popup, Qt.Key.Key_Return)
    assert _markdown(editor) == "[v002](version:v2id)"


def test_no_entities_to_mention(qtbot, editor):
    editor.set_mention_entities([], [])
    qtbot.keyClicks(editor, "@@")
    assert _completions(editor) == ["No versions to mention"]

    # The placeholder can't be picked
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert "version:" not in editor.as_markdown()


def test_mention_in_checklist(qtbot, editor):
    editor.set_format("fmt_checklist")
    qtbot.keyClicks(editor, "review @@v003")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "ask @adm")
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    markdown = editor.as_markdown().replace("`", "")
    assert [line for line in markdown.splitlines() if line] == [
        "- [ ] review [v003](version:v3id)",
        "- [ ] ask [Ayon admin](user:admin)",
    ]


def test_ending_checklist_removes_its_checkbox(qtbot, editor):
    editor.set_format("fmt_checklist")
    qtbot.keyClicks(editor, "one")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    # Enter on the empty checkbox line ends the list
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "done")

    assert len(editor._checkbox_handler.checkboxes) == 1
    assert "- [ ] one" in editor.as_markdown()


@pytest.mark.parametrize(
    "stored",
    [STORED, f"- [ ] {STORED}\n- [x] done"],
    ids=["plain", "checklist"],
)
def test_comment_field_round_trip(qtbot, stored):
    field = AYCommentField(text=stored, read_only=True, user_list=USERS)
    qtbot.addWidget(field)

    assert "@Roy Nieterau see @@v003 for @@@compositing" in field.toPlainText()
    assert _markdown(field) == " ".join(stored.split())


@pytest.mark.parametrize("key", [Qt.Key.Key_Home, Qt.Key.Key_End])
def test_typing_next_to_loaded_mention(qtbot, editor, key):
    editor.set_markdown("[Roy Nieterau](user:bigroy)")
    qtbot.keyClick(editor, key)
    qtbot.keyClicks(editor, " hi ")

    text = "hi [Roy Nieterau](user:bigroy)"
    if key == Qt.Key.Key_End:
        text = "[Roy Nieterau](user:bigroy) hi"
    assert _markdown(editor) == text


@pytest.fixture
def text_box(qtbot) -> AYTextBox:
    widget = AYTextBox(num_lines=4, user_list=USERS)
    widget.set_mention_entities(VERSIONS, TASKS)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_text_box_mention_buttons(qtbot, text_box):
    editor = text_box.edit_field

    qtbot.keyClicks(editor, "see")
    text_box._add_mention_to_editor("@@")
    assert editor.toPlainText() == "see @@"
    assert len(_completions(editor)) == len(VERSIONS)

    # Another button switches the type of the mention being typed
    qtbot.keyClicks(editor, "v00")
    text_box._add_mention_to_editor("@@@")
    assert editor.toPlainText() == "see @@@"
    assert _completions(editor) == ["sh010 compositing", "sh010 lighting"]

    text_box._add_mention_to_editor("@")
    assert editor.toPlainText() == "see @"
    assert _completions(editor) == ["Roy Nieterau", "Ayon admin"]


def test_text_box_submits_stored_mentions(qtbot, text_box):
    editor = text_box.edit_field
    for typed in ("Hey @roy", "see @@v003", "for @@@comp"):
        qtbot.keyClicks(editor, typed)
        qtbot.keyClick(editor, Qt.Key.Key_Return)

    with qtbot.waitSignal(text_box.signals.comment_submitted) as submitted:
        qtbot.keyClick(
            editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
        )

    markdown, _category, attachments = submitted.args
    assert " ".join(markdown.replace("`", "").split()) == STORED
    assert attachments == []
    assert editor.toPlainText() == ""


def test_ctrl_enter_picks_mention_instead_of_submitting(qtbot, text_box):
    editor = text_box.edit_field
    qtbot.keyClicks(editor, "@@v002")
    with qtbot.assertNotEmitted(text_box.signals.comment_submitted):
        qtbot.keyClick(
            editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
        )
    assert _markdown(editor) == "[v002](version:v2id)"


def test_tab_picks_mention(qtbot, editor):
    qtbot.keyClicks(editor, "@@@light")
    qtbot.keyClick(editor, Qt.Key.Key_Tab)
    assert _markdown(editor) == "[lighting](task:t2id)"


def test_escape_closes_popup(qtbot, editor):
    qtbot.keyClicks(editor, "@@")
    assert _completions(editor)
    qtbot.keyClick(editor._mentions._completer.popup(), Qt.Key.Key_Escape)

    assert not editor._mentions.popup_visible()
    # Enter is a regular new line again
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "@@\n"
    assert "version:" not in editor.as_markdown()


def test_backspace_deletes_mention_as_a_whole(qtbot, editor):
    qtbot.keyClicks(editor, "Check @@v002")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "now")
    assert editor.toPlainText() == "Check @@v002 now"

    for _ in "now ":
        qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == "Check @@v002"

    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == "Check "
    # Text typed in place of the mention is not a link
    qtbot.keyClicks(editor, "this")
    assert _markdown(editor) == "Check this"


@pytest.mark.parametrize(
    "key, moves, expected",
    [
        # Text cursor in front of the mention
        (Qt.Key.Key_Delete, 4, "see for [compositing](task:t1id)"),
        # Text cursor in the middle of the mention
        (Qt.Key.Key_Delete, 6, "see for [compositing](task:t1id)"),
        (Qt.Key.Key_Backspace, 6, "see for [compositing](task:t1id)"),
        # Text outside of a mention is deleted per character
        (Qt.Key.Key_Delete, 0, "ee [v003](version:v3id) for"
                               " [compositing](task:t1id)"),
        (Qt.Key.Key_Backspace, 3, "se [v003](version:v3id) for"
                                  " [compositing](task:t1id)"),
    ],
    ids=[
        "delete_in_front",
        "delete_inside",
        "backspace_inside",
        "delete_text",
        "backspace_text",
    ],
)
def test_delete_loaded_mention(qtbot, editor, key, moves, expected):
    editor.set_markdown(
        "see [v003](version:v3id) for [compositing](task:t1id)"
    )
    qtbot.keyClick(editor, Qt.Key.Key_Home)
    for _ in range(moves):
        qtbot.keyClick(editor, Qt.Key.Key_Right)

    qtbot.keyClick(editor, key)
    assert _markdown(editor) == expected


def test_delete_selection_with_mention(qtbot, editor):
    editor.set_markdown("see [v003](version:v3id) now")
    editor.selectAll()
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == ""


def test_mention_not_deleted_in_read_only_field(qtbot):
    field = AYCommentField(text=STORED, read_only=True, user_list=USERS)
    qtbot.addWidget(field)
    text = field.toPlainText()
    qtbot.keyClick(field, Qt.Key.Key_Backspace)
    qtbot.keyClick(field, Qt.Key.Key_Delete)
    assert field.toPlainText() == text


def test_undo_restores_deleted_mention(qtbot, editor):
    editor.set_markdown("see [v003](version:v3id)")
    qtbot.keyClick(editor, Qt.Key.Key_End)
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == "see "

    editor.undo()
    assert _markdown(editor) == "see [v003](version:v3id)"


def test_mentions_keep_text_style(qtbot, editor):
    qtbot.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(editor, "ask @adm")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClick(editor, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(editor, "and ")
    qtbot.keyClick(editor, Qt.Key.Key_I, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(editor, "wait")

    markdown = _markdown(editor)
    assert "[Ayon admin](user:admin)" in markdown
    assert markdown.startswith("**ask")
    assert markdown.endswith("and *wait*")


def test_no_mentions_in_code(qtbot, editor):
    editor.set_markdown("```\n@@v003\n```\n")
    assert "version:" not in editor.as_markdown()
    assert "@@v003" in editor.as_markdown()


@pytest.mark.parametrize(
    "stored",
    [
        "```\n[v003](version:v3id)\n```",
        "~~~\n[v003](version:v3id)\n~~~",
        "`[Joe](user:admin)`",
        "see `[v003](version:v3id)` and ```[lighting](task:t2id)```",
        # Fence which is not closed
        "```\n[v003](version:v3id)",
    ],
    ids=["fence", "tilde_fence", "inline", "inline_and_fence", "open_fence"],
)
def test_mention_links_in_code_are_not_converted(stored):
    assert mentions_to_display(stored) == stored
    displayed = stored.replace("[", "[@@")
    assert mentions_to_storage(displayed) == displayed


def test_mentions_next_to_code_are_converted():
    stored = (
        "[v003](version:v3id) `[v002](version:v2id)` [lighting](task:t2id)"
        "\n```\n[v003](version:v3id)\n```\n[Roy Nieterau](user:bigroy)"
    )
    displayed = (
        "[@@v003](version:v3id) `[v002](version:v2id)`"
        " [@@@lighting](task:t2id)"
        "\n```\n[v003](version:v3id)\n```\n[@Roy Nieterau](user:bigroy)"
    )
    assert mentions_to_display(stored) == displayed
    assert mentions_to_storage(displayed) == stored


def test_code_of_loaded_comment_is_displayed_as_is(qtbot):
    stored = "```\n[v003](version:v3id)\n```\n"
    field = AYCommentField(text=stored, read_only=True, user_list=USERS)
    qtbot.addWidget(field)

    assert "[v003](version:v3id)" in field.toPlainText()
    assert "@@" not in field.toPlainText()
    assert "[v003](version:v3id)" in field.as_markdown()


def _move_into_first_block(editor: AYTextEditor) -> None:
    cursor = editor.textCursor()
    cursor.setPosition(editor.document().firstBlock().length() - 1)
    editor.setTextCursor(cursor)


def test_no_popup_in_loaded_code_block(qtbot, editor):
    editor.set_markdown("```\ncode\n```\n")
    _move_into_first_block(editor)

    qtbot.keyClicks(editor, " @@v002")
    assert not editor._mentions.popup_visible()
    # Enter is a new line in the code
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert "version:" not in editor.as_markdown()
    assert "@@v002" in editor.as_markdown()


def test_no_popup_in_typed_code_block(qtbot, editor):
    qtbot.keyClicks(editor, "```")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "@@v002")
    assert not editor._mentions.popup_visible()
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "@roy")
    assert not editor._mentions.popup_visible()

    # After the closing fence mentions are completed again
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "```")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "@@v002")
    assert _completions(editor) == ["renderMain v002"]


def test_no_popup_in_inline_code(qtbot, editor):
    # Inline code being typed
    qtbot.keyClicks(editor, "run `tool @@v0")
    assert not editor._mentions.popup_visible()
    qtbot.keyClicks(editor, "` then @@v002")
    assert _completions(editor) == ["renderMain v002"]

    # Inline code of loaded markdown
    editor.set_markdown("`code`")
    _move_into_first_block(editor)
    qtbot.keyClicks(editor, " @@")
    assert not editor._mentions.popup_visible()


def test_no_popup_in_code_style(qtbot, editor):
    # Code style of the toolbar
    editor.set_style("stl_code")
    qtbot.keyClicks(editor, "@@")
    assert not editor._mentions.popup_visible()
    editor.set_style("stl_code")
    qtbot.keyClicks(editor, " @@")
    assert len(_completions(editor)) == len(VERSIONS)


def test_mention_button_in_code_types_the_trigger(qtbot, text_box):
    editor = text_box.edit_field
    editor.set_markdown("```\ncode\n```\n")
    _move_into_first_block(editor)

    text_box._add_mention_to_editor("@@")
    assert not editor._mentions.popup_visible()
    assert "code @@" in editor.toPlainText()


def test_unknown_mention_types_are_regular_links(qtbot, editor):
    stored = "[shot](folder:f1id) and [site](https://ynput.io)"
    editor.set_markdown(stored)
    assert editor.toPlainText() == "shot and site"
    assert _markdown(editor) == stored


def test_same_label_mentions_keep_their_own_id(qtbot, editor):
    editor.set_mention_entities(
        [
            EntityMention("version", "a1id", "v001", "renderMain"),
            EntityMention("version", "b1id", "v001", "renderBeauty"),
        ],
        [],
    )
    for typed in ("@@renderBeauty", "@@renderMain"):
        qtbot.keyClicks(editor, typed)
        qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert _markdown(editor) == "[v001](version:b1id) [v001](version:a1id)"


def test_edit_comment_keeps_mentions(qtbot):
    data = CommentModel(comment=STORED)
    comment = AYComment(data=data, user_list=USERS)
    comment.set_mention_entities(VERSIONS, TASKS)
    qtbot.addWidget(comment)
    comment.show()
    qtbot.waitExposed(comment)
    field = comment.text_field

    comment._edit_comment()
    qtbot.keyClick(field, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(field, " and @@@light")
    qtbot.keyClick(field, Qt.Key.Key_Return)

    with qtbot.waitSignal(comment.comment_edited):
        comment._save_edit()
    assert " ".join(data.comment.replace("`", "").split()) == (
        f"{STORED} and [lighting](task:t2id)"
    )

    # Cancelling an edit restores the stored comment
    comment._edit_comment()
    qtbot.keyClick(field, Qt.Key.Key_Backspace)
    qtbot.keyClick(field, Qt.Key.Key_Backspace)
    comment._cancel_edit()
    assert _markdown(field) == f"{STORED} and [lighting](task:t2id)"


def _paint_row(editor: AYTextEditor, row: int, width: int = 400) -> QImage:
    """Paint a row of the open popup the way its delegate does."""
    popup = editor._mentions._completer.popup()
    index = editor._mentions._completer.completionModel().index(row, 0)
    image = QImage(width, 28, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    option = QStyleOptionViewItem()
    option.rect = image.rect()
    option.font = editor.font()
    painter = QPainter(image)
    painter.setFont(editor.font())
    popup.itemDelegate().paint(painter, option, index)
    painter.end()
    return image


def _count_pixels(image: QImage, color: str, x_range: range) -> int:
    """Count the pixels close to a color in a range of columns."""
    expected = QColor(color)
    count = 0
    for x in x_range:
        for y in range(image.height()):
            pixel = image.pixelColor(x, y)
            if (
                abs(pixel.red() - expected.red())
                + abs(pixel.green() - expected.green())
                + abs(pixel.blue() - expected.blue())
            ) < 30:  # noqa: PLR2004
                count += 1
    return count


ICON_COLUMNS = range(0, 28)
SUFFIX_COLUMNS = range(300, 400)


def test_entity_icons_in_type_color(qtbot, editor):
    editor.set_mention_entities(
        [
            EntityMention(
                "version", "v3id", "v003", "renderMain",
                icon="photo_library", color="#ff0000", suffix="2 days ago",
            ),
            # No product type known: default icon in the text color
            EntityMention("version", "v2id", "v002", "renderMain"),
        ],
        [
            EntityMention(
                "task", "t1id", "compositing", "sh010",
                icon="directions_run", color="#00ff00",
            ),
            # Icon which the icon font does not know
            EntityMention(
                "task", "t2id", "lighting", "sh010",
                icon="not_an_existing_icon", color="#0000ff",
            ),
        ],
    )

    qtbot.keyClicks(editor, "@@")
    typed = _paint_row(editor, 0)
    untyped = _paint_row(editor, 1)
    assert _count_pixels(typed, "#ff0000", ICON_COLUMNS) > 10  # noqa: PLR2004
    assert _count_pixels(untyped, "#ff0000", ICON_COLUMNS) == 0
    # The default icon is painted instead of leaving a gap
    background = untyped.pixelColor(399, 14)
    assert any(
        untyped.pixelColor(x, y) != background
        for x in ICON_COLUMNS
        for y in range(untyped.height())
    )
    # Only the version with a creation date has text on the right
    assert any(
        typed.pixelColor(x, y) != typed.pixelColor(399, 0)
        for x in SUFFIX_COLUMNS
        for y in range(typed.height())
    )
    assert all(
        untyped.pixelColor(x, y) == background
        for x in SUFFIX_COLUMNS
        for y in range(untyped.height())
    )

    editor.clear()
    qtbot.keyClicks(editor, "@@@")
    assert _count_pixels(
        _paint_row(editor, 0), "#00ff00", ICON_COLUMNS
    ) > 10  # noqa: PLR2004
    # Falls back to the task icon, still in the color of the task type
    assert _count_pixels(
        _paint_row(editor, 1), "#0000ff", ICON_COLUMNS
    ) > 10  # noqa: PLR2004


def test_icons_do_not_change_completion_or_markdown(qtbot, editor):
    editor.set_mention_entities(
        [
            EntityMention(
                "version", "v3id", "v003", "renderMain",
                icon="photo_library", color="#ff0000", suffix="2 days ago",
            ),
        ],
        [],
    )
    qtbot.keyClicks(editor, "@@render")
    assert _completions(editor) == ["renderMain v003"]
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _markdown(editor) == "[v003](version:v3id)"


@pytest.mark.parametrize(
    "before",
    ["\U0001F600 see ", "\U0001F600\U0001F600 see ", "see \U0001F600 "],
    ids=["one_emoji", "two_emoji", "emoji_in_front"],
)
def test_pick_mention_after_emoji(qtbot, editor, before):
    # Emoji take two positions in the document but are one character
    # of a Python string.
    editor.insertPlainText(before)
    qtbot.keyClicks(editor, "@@v002")
    assert _completions(editor) == ["renderMain v002"]
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    assert editor.toPlainText() == f"{before}@@v002 "
    assert _markdown(editor) == f"{before}[v002](version:v2id)"


def test_mention_button_after_emoji(qtbot, text_box):
    editor = text_box.edit_field
    editor.insertPlainText("\U0001F600\U0001F600 see ")
    qtbot.keyClicks(editor, "@@v0")
    text_box._add_mention_to_editor("@@@")
    assert editor.toPlainText() == "\U0001F600\U0001F600 see @@@"

    editor.clear()
    editor.insertPlainText("see\U0001F600")
    text_box._add_mention_to_editor("@")
    assert editor.toPlainText() == "see\U0001F600 @"


def _format_ranges(editor: AYTextEditor) -> list[str]:
    """Texts of the first block the highlighter colors as link."""
    block = editor.document().firstBlock()
    link = editor._mentions._highlighter._mention_fmt.foreground().color()
    # Qt counts UTF-16 code units
    encoded = block.text().encode("utf-16-le")
    return [
        encoded[2 * r.start:2 * (r.start + r.length)].decode("utf-16-le")
        for r in block.layout().formats()
        if r.format.foreground().color() == link
    ]


def test_highlight_after_emoji(qtbot, editor):
    editor.insertPlainText("\U0001F600 https://ynput.io and ")
    qtbot.keyClicks(editor, "@@v002")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    editor._mentions._highlighter.rehighlight()

    assert _format_ranges(editor) == ["https://ynput.io", "@@v002"]


def test_popup_closes_when_text_cursor_leaves_mention(qtbot, editor):
    qtbot.keyClicks(editor, "hello @@")
    assert _completions(editor)

    qtbot.keyClick(editor, Qt.Key.Key_Home)
    assert not editor._mentions.popup_visible()
    # Enter is a regular new line instead of being swallowed
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert editor.toPlainText() == "\nhello @@"
    assert "version:" not in editor.as_markdown()

    # Back at the mention the popup opens again
    qtbot.keyClick(editor, Qt.Key.Key_End)
    assert len(_completions(editor)) == len(VERSIONS)


def test_popup_closes_when_clicking_elsewhere(qtbot, editor):
    qtbot.keyClicks(editor, "hello @@")
    assert _completions(editor)

    start = editor.cursorRect(QTextCursor(editor.document())).center()
    qtbot.mouseClick(editor.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert not editor._mentions.popup_visible()


def test_popup_follows_text_cursor_in_mention(qtbot, editor):
    qtbot.keyClicks(editor, "@@v002")
    assert _completions(editor) == ["renderMain v002"]

    # Text cursor behind "@@v00", which matches all versions
    qtbot.keyClick(editor, Qt.Key.Key_Left)
    assert len(_completions(editor)) == len(VERSIONS)


def test_enter_not_swallowed_by_stale_popup(qtbot, editor):
    qtbot.keyClicks(editor, "hello @@")
    # A popup left open while nothing is being completed
    editor.blockSignals(True)
    qtbot.keyClick(editor, Qt.Key.Key_Home)
    editor.blockSignals(False)
    assert editor._mentions.popup_visible()

    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert not editor._mentions.popup_visible()
    assert editor.toPlainText() == "\nhello @@"


def test_narrow_popup_does_not_paint_label_over_suffix(qtbot, editor):
    suffix = "22 minutes ago"
    editor.set_mention_entities(
        [
            EntityMention(
                "version", "v3id", "v003",
                "aVeryLongProductNameWhichDoesNotFitInTheRow" * 3,
                suffix=suffix,
            ),
            EntityMention("version", "v2id", "", "", suffix=suffix),
        ],
        [],
    )
    qtbot.keyClicks(editor, "@@")

    # The row with only an icon and suffix shows what the suffix paints
    for width in (400, 160, 90, 40):
        long_row = _paint_row(editor, 0, width)
        suffix_row = _paint_row(editor, 1, width)
        suffix_width = editor.fontMetrics().horizontalAdvance(suffix)
        for x in range(max(28, width - suffix_width), width):
            for y in range(long_row.height()):
                assert long_row.pixelColor(x, y) == suffix_row.pixelColor(
                    x, y
                ), f"label painted over the suffix at width {width}"


def test_entities_with_missing_values(qtbot, editor):
    editor.set_mention_entities(
        [
            EntityMention("version", "v3id", "v003", None),
            EntityMention("version", "v2id", None, "renderMain"),
            EntityMention(
                "version", "v1id", "v001", None,
                icon=None, color=None, suffix=None,
            ),
        ],
        [],
    )
    qtbot.keyClicks(editor, "@@")
    assert _completions(editor) == ["v003", "renderMain", "v001"]
    for row in range(3):
        _paint_row(editor, row)

    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _markdown(editor) == "[v003](version:v3id)"


def _count_requests(widget) -> list[int]:
    """Count how often the entities to mention are requested."""
    requests = []
    widget.mention_entities_requested.connect(lambda: requests.append(1))
    return requests


def test_entities_requested_when_popup_opens(qtbot, editor):
    requests = _count_requests(editor)

    # Users are known up front
    qtbot.keyClicks(editor, "@ro")
    assert not requests
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    # Once for the popup, not for every key typed in it
    qtbot.keyClicks(editor, "@@")
    assert len(requests) == 1
    qtbot.keyClicks(editor, "v00")
    assert len(requests) == 1
    # Also not when moving the text cursor in the mention
    qtbot.keyClick(editor, Qt.Key.Key_Left)
    qtbot.keyClick(editor, Qt.Key.Key_Right)
    assert len(requests) == 1
    qtbot.keyClick(editor, Qt.Key.Key_Return)

    # Again the next time it opens, they may have changed
    qtbot.keyClicks(editor, "@@")
    assert len(requests) == 2  # noqa: PLR2004
    # One answer has both the versions and tasks
    editor.insert_mention_trigger("@@@")
    assert len(_completions(editor)) == len(TASKS)
    assert len(requests) == 2  # noqa: PLR2004


def test_entities_requested_once_when_typing_task_trigger(qtbot, editor):
    requests = _count_requests(editor)
    # Typing "@@@" passes "@" and "@@"
    qtbot.keyClicks(editor, "@@@comp")
    assert len(requests) == 1


def test_entities_not_requested_without_popup(qtbot, editor):
    requests = _count_requests(editor)

    qtbot.keyClicks(editor, "mail@@host ")
    editor.insertPlainText("@@@@ ")
    editor.set_markdown("see [v003](version:v3id) `@@code`")
    editor.setReadOnly(True)
    editor.set_markdown("@@")
    assert not requests


def test_entities_loading_until_set(qtbot, editor):
    editor.clear_mention_entities()

    qtbot.keyClicks(editor, "@@")
    assert _completions(editor) == ["Loading versions..."]
    # The placeholder can't be picked
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert "version:" not in editor.as_markdown()

    editor.clear()
    qtbot.keyClicks(editor, "@@@")
    assert _completions(editor) == ["Loading tasks..."]
    # Users don't wait for the entities
    editor.clear()
    qtbot.keyClicks(editor, "@")
    assert _completions(editor) == ["Roy Nieterau", "Ayon admin"]


def test_open_popup_updates_when_entities_arrive(qtbot, editor):
    editor.clear_mention_entities()
    qtbot.keyClicks(editor, "see @@v00")
    assert not _completions(editor)

    # The answer to the request comes in while typing
    editor.set_mention_entities(VERSIONS, TASKS)
    assert _completions(editor) == [
        "renderMain v003",
        "renderMain v002",
        "workfileCompositing v001",
    ]
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _markdown(editor) == "see [v003](version:v3id)"

    # Without any they are no longer loading
    editor.clear_mention_entities()
    qtbot.keyClicks(editor, "@@")
    editor.set_mention_entities([], [])
    assert _completions(editor) == ["No versions to mention"]


def test_entities_set_while_handling_request(qtbot, editor):
    # A cache answers right away, from within the signal
    editor.clear_mention_entities()
    editor.mention_entities_requested.connect(
        lambda: editor.set_mention_entities(VERSIONS, TASKS)
    )
    qtbot.keyClicks(editor, "@@v002")
    assert _completions(editor) == ["renderMain v002"]
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _markdown(editor) == "[v002](version:v2id)"


def test_known_entities_stay_while_refreshing(qtbot, editor):
    # Entities of an earlier request are shown while new ones are fetched
    requests = _count_requests(editor)
    qtbot.keyClicks(editor, "@@")
    assert len(requests) == 1
    assert len(_completions(editor)) == len(VERSIONS)

    newer = [EntityMention("version", "v4id", "v004", "renderMain")]
    editor.set_mention_entities(newer + VERSIONS, TASKS)
    assert _completions(editor)[0] == "renderMain v004"


def test_setting_entities_does_not_open_popup(qtbot, editor):
    qtbot.keyClicks(editor, "no mention here")
    editor.set_mention_entities(VERSIONS, TASKS)
    editor.clear_mention_entities()
    assert not editor._mentions.popup_visible()


def test_text_box_and_comment_request_entities(qtbot, text_box):
    requests = _count_requests(text_box)
    qtbot.keyClicks(text_box.edit_field, "@@")
    assert len(requests) == 1
    text_box.clear_mention_entities()
    assert _completions(text_box.edit_field) == ["Loading versions..."]

    comment = AYComment(data=CommentModel(comment="hi"), user_list=USERS)
    qtbot.addWidget(comment)
    comment.show()
    qtbot.waitExposed(comment)
    requests = _count_requests(comment)
    comment.clear_mention_entities()
    comment._edit_comment()
    qtbot.keyClick(
        comment.text_field, Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier
    )
    qtbot.keyClicks(comment.text_field, " @@@")
    assert len(requests) == 1
    assert _completions(comment.text_field) == ["Loading tasks..."]

    comment.set_mention_entities(VERSIONS, TASKS)
    assert _completions(comment.text_field) == [
        "sh010 compositing", "sh010 lighting",
    ]


def _underlined(editor: AYTextEditor) -> list[str]:
    """Texts of the first block which are underlined."""
    texts = []
    it = editor.document().firstBlock().begin()
    while not it.atEnd():
        fragment = it.fragment()
        it += 1
        if fragment.charFormat().fontUnderline():
            texts.append(fragment.text())
    return texts


def _paste_comment(qtbot, editor: AYTextEditor, stored: str) -> None:
    """Copy all of a displayed comment and paste it in the editor."""
    field = AYCommentField(text=stored, read_only=True, user_list=USERS)
    qtbot.addWidget(field)
    field.selectAll()
    editor.insertFromMimeData(field.createMimeDataFromSelection())


def test_pasted_comment_is_not_underlined(qtbot, editor):
    stored = f"[site](https://ynput.io) {STORED}"
    _paste_comment(qtbot, editor, stored)

    assert _underlined(editor) == []
    assert not editor.currentCharFormat().fontUnderline()
    # The links are kept
    assert _markdown(editor) == stored

    # Text and mentions typed after the pasted link
    qtbot.keyClicks(editor, " and @@v002")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "@@@light")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _underlined(editor) == []
    assert "_" not in editor.as_markdown()
    assert _markdown(editor).endswith(
        "and [v002](version:v2id) [lighting](task:t2id)"
    )


def test_paste_over_selection_and_undo(qtbot, editor):
    qtbot.keyClicks(editor, "replace me")
    editor.selectAll()
    _paste_comment(qtbot, editor, "see [v003](version:v3id)")
    assert editor.toPlainText() == "see @@v003"
    assert _underlined(editor) == []

    # Pasting is a single step to undo
    editor.undo()
    assert editor.toPlainText() == "replace me"


def test_paste_plain_text(qtbot, editor):
    mime = QMimeData()
    mime.setText("plain @@v003 text")
    qtbot.keyClicks(editor, "some ")
    editor.insertFromMimeData(mime)
    assert editor.toPlainText() == "some plain @@v003 text"
    assert _markdown(editor) == "some plain @@v003 text"


@pytest.mark.parametrize(
    "stored",
    [
        "[Roy Nieterau](user:bigroy)",
        "[site](https://ynput.io)",
        "**bold**",
        "`code`",
    ],
    ids=["mention", "link", "bold", "code"],
)
def test_clear_resets_style_to_type_in(qtbot, editor, stored):
    editor.set_markdown(stored)
    qtbot.keyClick(editor, Qt.Key.Key_End)
    editor.clear()

    qtbot.keyClicks(editor, "next comment")
    assert editor.as_markdown().strip() == "next comment"


def test_mentions_after_submitting_pasted_comment(qtbot, text_box):
    # The reported case: mentions picked after submitting a comment which
    # was pasted were underlined with their spaces as one link, and stored
    # with "_" between them.
    editor = text_box.edit_field
    _paste_comment(qtbot, editor, STORED)
    qtbot.keyClicks(editor, " [Roy Nieterau](user:bigroy)")
    with qtbot.waitSignal(text_box.signals.comment_submitted):
        qtbot.keyClick(
            editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
        )

    for typed in ("@adm", "@@v002", "@@@light"):
        qtbot.keyClicks(editor, typed)
        qtbot.keyClick(editor, Qt.Key.Key_Return)
    assert _underlined(editor) == []

    with qtbot.waitSignal(text_box.signals.comment_submitted) as submitted:
        qtbot.keyClick(
            editor, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier
        )
    assert " ".join(submitted.args[0].replace("`", "").split()) == (
        "[Ayon admin](user:admin) [v002](version:v2id) [lighting](task:t2id)"
    )
