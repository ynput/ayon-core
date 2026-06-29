from __future__ import annotations

import re
import logging

from qtpy.QtCore import QSize, Qt
from qtpy.QtGui import (
    QColor,
    QFont,
    QPainter,
    QStandardItem,
    QStandardItemModel,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
)
from qtpy.QtWidgets import (
    QCompleter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
)

from ..style_types import get_ayon_style
from ..data_models import User
from .user_image import AYUserImage

# Background colour used for both character-level (inline code) and
# block-level (fenced code block) highlighting.  Defined once here so
# that both the highlighter and ``apply_code_block_backgrounds()`` always
# use the same value.
CODE_BG: QColor = QColor("#1e1e1e")
CODE_FG: QColor = QColor("#eeeeee")


class UserCompleterDelegate(QStyledItemDelegate):
    """Custom delegate to display user icon and full name in completer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size = 20
        self._user_pixmap = {}

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Paint user icon and full name."""
        user: User = index.data(Qt.ItemDataRole.UserRole)
        if not user:
            super().paint(painter, option, index)
            return

        # Draw background
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.light())
        else:
            painter.fillRect(option.rect, option.palette.midlight())

        # Draw user icon
        try:
            icon_pixmap = self._user_pixmap[user.name]
        except KeyError:
            user_image = AYUserImage(
                src=user.avatar_url,
                full_name=user.full_name,
                size=self.icon_size,
                outline=False,
            )
            icon_pixmap = user_image.pixmap()
            self._user_pixmap[user.name] = icon_pixmap

        icon_x = option.rect.x() + 4
        icon_y = option.rect.y() + (option.rect.height() - self.icon_size) // 2
        painter.drawPixmap(icon_x, icon_y, icon_pixmap)

        # Draw full name
        text_x = icon_x + self.icon_size + 8
        text_rect = option.rect.adjusted(text_x, 0, 0, 0)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter,
            user.full_name,
        )

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QSize:
        """Return size hint for completer items."""
        return QSize(option.rect.width(), self.icon_size + 8)


class UserCompleterModel(QStandardItemModel):
    """Model for user completer."""

    def __init__(self, users: list[User], parent=None):
        super().__init__(parent)
        self.users = users
        self._populate()

    def _populate(self) -> None:
        """Populate model with users."""
        self.clear()
        for user in self.users:
            item = QStandardItem(user.full_name)
            item.setData(user, Qt.ItemDataRole.UserRole)
            self.appendRow(item)


def setup_user_completer(
    text_edit: QTextEdit,
    on_completer_activated,
    on_text_changed,
) -> None:
    """Setup user name completer for a QTextEdit widget.

    Args:
        text_edit: The QTextEdit widget to attach completer to.
        on_completer_activated: Callback for completer activation.
        on_text_changed: Callback for text changes.
    """
    users = getattr(text_edit, "_user_list")
    if not users:
        users = [
            User(
                name="not available",
                short_name="not available",
                full_name="not available",
                email="",
                avatar_url="",
            )
        ]
    model = UserCompleterModel(users, text_edit)
    text_edit.completer = QCompleter(model, text_edit)
    text_edit.completer.setCompletionMode(
        QCompleter.CompletionMode.PopupCompletion
    )
    text_edit.completer.setFilterMode(Qt.MatchFlag.MatchContains)
    text_edit.completer.setMaxVisibleItems(4)
    text_edit.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    text_edit.completer.setWidget(text_edit)

    # Set custom delegate
    popup = text_edit.completer.popup()
    if popup:
        delegate = UserCompleterDelegate(popup)
        popup.setItemDelegate(delegate)
        popup.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)

    # Connect completer signals
    text_edit.completer.activated.connect(on_completer_activated)
    text_edit.textChanged.connect(on_text_changed)


def on_users_updated(text_edit: QTextEdit):
    if not hasattr(text_edit, "completer"):
        return

    users = getattr(text_edit, "_user_list")
    if not users:
        users = [
            User(
                name="not available",
                short_name="not available",
                full_name="not available",
                email="",
                avatar_url="",
            )
        ]
    model = UserCompleterModel(users, text_edit)
    text_edit.completer.setModel(model)


def on_completer_text_changed(
    text_edit: QTextEdit,
) -> None:
    """Handle text changes to show/hide completer.

    Args:
        text_edit: The QTextEdit widget with completer.
    """
    if not hasattr(text_edit, "completer") or text_edit.isReadOnly():
        return

    cursor = text_edit.textCursor()
    block = cursor.block()
    text = block.text()
    pos_in_block = cursor.positionInBlock()

    # Find the last '@' before cursor
    at_pos = text.rfind("@", 0, pos_in_block)
    if at_pos == -1:
        popup = text_edit.completer.popup()
        if popup:
            popup.hide()
        return

    # Get text after '@'
    prefix = text[at_pos + 1 : pos_in_block]

    # Show completer if '@' is followed by nothing or non-space characters
    if not prefix or (prefix and not prefix[0].isspace()):
        text_edit.completer.setCompletionPrefix(prefix)
        show_completer_popup(text_edit, at_pos)
        # Auto-select if only one item
        popup = text_edit.completer.popup()
        if popup:
            popup_model = popup.model()
            row_count = popup_model.rowCount() if popup_model else 0
            if row_count == 1:
                popup.setCurrentIndex(popup_model.index(0, 0))
    else:
        popup = text_edit.completer.popup()
        if popup:
            popup.hide()


def show_completer_popup(text_edit: QTextEdit, at_pos: int) -> None:
    """Show completer popup above the QTextEdit.

    Args:
        text_edit: The QTextEdit widget with completer.
        at_pos: Position of '@' character in the block.
    """
    popup = text_edit.completer.popup()
    if not popup:
        return

    # Get editor dimensions
    editor_rect = text_edit.rect()
    editor_width = editor_rect.width()

    # Show popup to get its height
    popup.show()

    # Calculate height based on max visible items (4)
    max_visible = text_edit.completer.maxVisibleItems()
    item_height = popup.sizeHintForRow(0)
    popup_height = item_height * max_visible

    # Position popup above the QTextEdit with same width as editor
    global_pos = text_edit.mapToGlobal(editor_rect.topLeft())
    popup_x = global_pos.x()
    popup_y = global_pos.y() - popup_height

    popup.setGeometry(popup_x, popup_y, editor_width, popup_height)


def on_completer_activated(
    text_edit: QTextEdit,
    text: str,
) -> None:
    """Handle completer selection.

    Args:
        text_edit: The QTextEdit widget with completer.
        text: The selected completion text (user full name).
    """
    cursor = text_edit.textCursor()
    block = cursor.block()
    text_in_block = block.text()
    pos_in_block = cursor.positionInBlock()

    # Find the '@' position
    at_pos = text_in_block.rfind("@", 0, pos_in_block)
    if at_pos == -1:
        return

    # Replace from '@' to cursor with '@' + full_name
    cursor.setPosition(block.position() + at_pos)
    cursor.setPosition(
        block.position() + pos_in_block,
        QTextCursor.MoveMode.KeepAnchor,
    )
    cursor.insertText(f"@{text}")
    text_edit.setTextCursor(cursor)
    popup = text_edit.completer.popup()
    if popup:
        popup.hide()


def on_completer_key_press(
    text_edit: QTextEdit,
    event,
) -> bool:
    """Handle key press events for completer.

    Args:
        text_edit: The QTextEdit widget with completer.
        event: The key press event.

    Returns:
        True if event was handled, False otherwise.
    """
    if not hasattr(text_edit, "completer"):
        return False

    popup = text_edit.completer.popup()
    if popup and popup.isVisible():
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Get current completion from the selected index
            current_index = popup.currentIndex()
            if current_index.isValid():
                completion = current_index.data()
                if completion:
                    text_edit.completer.activated.emit(completion)
                    return True
    return False


class MentionHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for @mentions, raw URLs, and code spans.

    Operates on block-local plain text so positions are always correct
    regardless of any rich-text formatting already present in the document
    (bold, italic, headings, code spans, etc.).

    Patterns highlighted:

    - Fenced code blocks (```\\`\\`\\` ... \\`\\`\\```) spanning multiple
      lines - black background, white monospace text.
      Block state ``1`` tracks whether the current block is inside a fence.
    - Qt-rendered code blocks (from ``setMarkdown()``) — detected via
      ``nonBreakableLines`` on the block format.
    - Qt-rendered inline code spans (from ``setMarkdown()``) — detected via
      ``fontFixedPitch`` on individual text fragments.
    - Inline code spans (`` \\`code\\` ``) in raw (un-rendered) text — same
      style, detected by backtick regex.
    - ``@@@word`` — task mention
    - ``@@word``  — version mention
    - ``@word``   — user mention (only the first word if the full name is not
      in the known user list; both words when it is)
    - ``https?://…`` — raw URL

    Args:
        document: The QTextDocument to attach to.
        user_list: Live list of :class:`~..data_models.User` objects used to
            decide whether a two-word mention should be highlighted in full.
    """

    # Compiled patterns — order matters: longer prefixes first so that
    # ``@@@`` is matched before ``@@`` and ``@@`` before ``@``.
    _P_TASK = re.compile(r"@@@\w+( \w+)?")
    _P_VERSION = re.compile(r"@@(?!@)\w+( \w+)?")
    _P_USER = re.compile(r"@(?!@)\w+( \w+)?")
    _P_RAW_LINK = re.compile(r"https?://\S+")
    # Inline code: single backtick pair on the same line.
    _P_CODE_INLINE = re.compile(r"`[^`\n]+`")

    def __init__(self, document, user_list: list) -> None:
        super().__init__(document)
        self._user_list = user_list
        pal = get_ayon_style().model.base_palette
        self._mention_fmt = QTextCharFormat()
        self._mention_fmt.setForeground(pal.link())
        self._code_fmt = None

    def update_user_list(self, user_list: list) -> None:
        """Replace the user list and trigger a full rehighlight.

        Args:
            user_list: Updated list of User objects.
        """
        self._user_list = user_list
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        """Apply code, mention, and URL highlighting to a single block.

        Two detection strategies are combined so that code is styled in both
        *edit mode* (raw markdown typed by the user) and *display mode*
        (rich text rendered via ``document().setMarkdown()``):

        **Edit mode — raw fence markers:**
        Uses block state ``1`` to track multi-line fenced code blocks. A line
        starting with *```* opens or closes a fence; every line inside the
        fence is styled with :attr:`_code_fmt`.  A line that both opens and
        closes a fence on the same line (e.g. ``\\`\\`\\`code\\`\\`\\```) is
        treated as a single-line code block with no state change.

        **Display mode — Qt-rendered char formats:**
        After ``setMarkdown()`` Qt strips the fence markers and stores rich
        text character formats.  Fenced code blocks have
        ``nonBreakableLines=True`` set on the block format (``fontFixedPitch``
        stays ``False`` on the block-level char format).  Inline code spans
        set ``fontFixedPitch=True`` on individual text *fragments* within a
        paragraph.  Both are detected here and styled with :attr:`_code_fmt`.

        Inline code spans from raw backtick syntax (`` \\`code\\` ``) are also
        detected via :attr:`_P_CODE_INLINE` for live-typed backtick spans.

        Code formatting is applied *after* mention/URL patterns so that it
        takes precedence over any mention highlight inside a code span.

        Called automatically by Qt whenever the block changes.

        Args:
            text: Plain text content of the current block.
        """
        block = self.currentBlock()
        in_fence = self.previousBlockState() == 1
        code_fmt = self._get_code_char_format()

        # ── Edit mode: raw fence markers ─────────────────────────────────
        if in_fence:
            # The entire line belongs to the open fenced block.
            self.setFormat(0, len(text), code_fmt)
            # A line starting with ``` closes the fence.
            if text.startswith("```"):
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return

        if text.startswith("```"):
            self.setFormat(0, len(text), code_fmt)
            rest = text[3:]
            # Closing ``` on the same line → single-line block, no state.
            if "```" in rest:
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return

        self.setCurrentBlockState(0)

        # ── Display mode: Qt-rendered whole-block code ───────────────────
        # After setMarkdown(), Qt marks fenced code block lines with
        # nonBreakableLines=True on the block format.  The char format
        # carries fontFamilies=['monospace'] but fontFixedPitch stays False.
        # Style the whole line and skip mention/URL patterns — they don't
        # belong inside code.
        if block.blockFormat().nonBreakableLines():
            self.setFormat(0, len(text), code_fmt)
            return

        # ── Mentions and URLs (applied before inline code) ───────────────
        users = {u.full_name for u in self._user_list}

        # Task mentions (@@@)
        for m in self._P_TASK.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._mention_fmt)

        # Version mentions (@@)
        for m in self._P_VERSION.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._mention_fmt)

        # User mentions (@) — highlight only the first word unless the full
        # two-word name is in the known user list.
        for m in self._P_USER.finditer(text):
            full_match = m.group(0)
            mention_name = full_match[1:]  # strip leading @
            if mention_name in users:
                length = len(full_match)
            else:
                # Highlight only up to the first word (no trailing space+word)
                length = len(full_match.split()[0])
            self.setFormat(m.start(), length, self._mention_fmt)

        # Raw URLs
        for m in self._P_RAW_LINK.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), self._mention_fmt)

        # ── Inline code (applied last, overrides mention formatting) ─────

        # Raw backtick syntax `code` — detected in plain text for live
        # editing where backtick characters are still present:
        for m in self._P_CODE_INLINE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), code_fmt)

        # Qt-rendered inline code spans — after setMarkdown() the backticks
        # are consumed and individual fragments carry fontFixedPitch=True:
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid() and fragment.charFormat().fontFixedPitch():
                frag_start = fragment.position() - block.position()
                self.setFormat(frag_start, fragment.length(), code_fmt)
            it += 1

    def _get_code_char_format(self) -> QTextCharFormat:
        """Return a QTextCharFormat for inline code spans."""
        if self._code_fmt is not None:
            return self._code_fmt

        fmt = QTextCharFormat()
        fmt.setFontFixedPitch(True)
        fmt.setFontFamilies(["Noto Sans Mono"])
        fmt.setBackground(CODE_BG)
        fmt.setForeground(CODE_FG)
        self._code_fmt = fmt
        return fmt


def format_comment_on_change(text_edit: QTextEdit) -> None:
    """Ensure a :class:`MentionHighlighter` is installed on *text_edit*.

    Idempotent: safe to call on every ``contentsChanged`` signal.  The
    highlighter is created once and attached to the document.  Subsequent
    calls only call :meth:`MentionHighlighter.update_user_list` when the
    ``_user_list`` reference on *text_edit* has been replaced (e.g. after a
    server refresh), which avoids triggering an unnecessary ``rehighlight``
    — and the infinite-recursion that would follow — on every keystroke.

    Args:
        text_edit: The QTextEdit whose document should have mention
            highlighting applied.
    """
    highlighter: MentionHighlighter | None = getattr(
        text_edit, "_mention_highlighter", None
    )
    user_list = getattr(text_edit, "_user_list", [])

    if highlighter is None:
        highlighter = MentionHighlighter(text_edit.document(), user_list)
        text_edit._mention_highlighter = highlighter  # type: ignore[attr-defined]
    elif highlighter._user_list is not user_list:
        # The list object was replaced (e.g. after a user-list refresh).
        # update_user_list() calls rehighlight() which is safe here because
        # this branch is only reached when _suppress_formatting is False and
        # the list identity has changed — not on every keystroke.
        highlighter.update_user_list(user_list)


def apply_code_block_backgrounds(text_edit: QTextEdit) -> None:
    """Apply a full-width background colour to every fenced code block.

    ``QSyntaxHighlighter.setFormat()`` only paints behind individual
    text characters, so the end of a short line keeps the regular widget
    background.  Setting ``QTextBlockFormat.background`` instead causes
    Qt's own layout engine to paint the background across the *entire*
    width of the block before any characters are drawn.

    This function is intentionally separate from
    :class:`MentionHighlighter` because Qt's documentation forbids
    modifying the document from inside ``highlightBlock()``.

    Two detection strategies are combined so that code blocks are
    recognised in both scenarios:

    - **Display mode** (after ``document().setMarkdown()``): Qt marks
      fenced code block lines with ``nonBreakableLines=True`` on the
      block format.
    - **Edit mode** (raw typing): Lines inside a ``\\`\\`\\`…\\`\\`\\```` fence
      are detected by tracking an open-fence flag while iterating from
      the first block of the document.

    The function is guarded by the ``_suppress_formatting`` attribute on
    *text_edit* to prevent infinite recursion: writing block formats
    emits ``contentsChanged``, which would otherwise re-enter this
    function.

    Args:
        text_edit: The QTextEdit whose document should have fenced code
            block backgrounds applied.
    """
    if getattr(text_edit, "_suppress_formatting", False):
        return

    doc = text_edit.document()
    setattr(text_edit, "_suppress_formatting", True)

    cursor = QTextCursor(doc)
    cursor.beginEditBlock()

    try:
        in_fence = False
        block = doc.begin()
        while block.isValid():
            text = block.text()
            is_code = False

            # Display mode: Qt-rendered fenced code block.
            if block.blockFormat().nonBreakableLines():
                is_code = True
            else:
                # Edit mode: raw ``` fence markers.
                if in_fence:
                    is_code = True
                    if text.startswith("```"):
                        in_fence = False  # closing fence line — still code
                elif text.startswith("```"):
                    is_code = True
                    rest = text[3:]
                    if "```" not in rest:
                        in_fence = True  # opening fence
                    # else: single-line ```…``` — is_code=True, no state change

            bg_brush = block.blockFormat().background()
            has_code_bg = (
                bg_brush.style() != Qt.BrushStyle.NoBrush
                and bg_brush.color().rgb() == CODE_BG.rgb()
            )

            if is_code and not has_code_bg:
                cursor.setPosition(block.position())
                new_fmt = QTextBlockFormat()
                new_fmt.setBackground(CODE_BG)
                cursor.mergeBlockFormat(new_fmt)
            elif not is_code and has_code_bg:
                # Remove the previously applied code background.
                cursor.setPosition(block.position())
                restored = QTextBlockFormat(block.blockFormat())
                restored.clearBackground()
                cursor.setBlockFormat(restored)

            block = block.next()
    except Exception as e:
        logging.info(f"Error in apply_code_block_backgrounds: {e}")
    finally:
        # Ensure we always end the edit block and reset the flag
        cursor.endEditBlock()
        setattr(text_edit, "_suppress_formatting", False)
