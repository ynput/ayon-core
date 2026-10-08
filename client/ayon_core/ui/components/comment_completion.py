from __future__ import annotations

import re
import logging

from qtmaterialsymbols import get_icon, get_icon_name_char
from qtpy.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QSize,
    Qt,
    Signal,
)
from qtpy.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPixmap,
    QStandardItem,
    QStandardItemModel,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextFormat,
    QPalette,
)
from qtpy.QtWidgets import (
    QCompleter,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTextEdit,
)

from ..style_types import get_ayon_style
from ..data_models import EntityMention, User
from .user_image import AYUserImage

# Background colour used for both character-level (inline code) and
# block-level (fenced code block) highlighting.  Defined once here so
# that both the highlighter and ``apply_code_block_backgrounds()`` always
# use the same value.
CODE_BG: QColor = QColor("#1e1e1e")
CODE_FG: QColor = QColor("#eeeeee")

# Characters typed to mention an entity of a certain type.
MENTION_TRIGGERS = {"user": "@", "version": "@@", "task": "@@@"}
_MENTION_NOUNS = {"@": "users", "@@": "versions", "@@@": "tasks"}
# Icons of entities without an icon for their product or task type.
_MENTION_ICONS = {"version": "layers", "task": "check_circle"}

# Mentions are stored in markdown as links like "[Joe](user:admin)",
# "[v003](version:<id>)" or "[modeling](task:<id>)".
_MENTION_TYPES = "|".join(MENTION_TRIGGERS)
MENTION_LINK_PATTERN = re.compile(
    r"\[@*(?P<label>[^\]]+)\]"
    rf"\((?P<ref>(?P<type>{_MENTION_TYPES}):[^)\s]+)\)"
)
_MENTION_HREF_PATTERN = re.compile(rf"(?:{_MENTION_TYPES}):.")
# One to three "@" at the start of a word, followed by the search text.
_MENTION_TRIGGER_PATTERN = re.compile(
    r"(?:^|(?<=[\s(\[{\"'￼]))(?P<trigger>@{1,3})(?P<prefix>[^\s@]*)$"
)
# Fenced code blocks and inline code spans of markdown, mentions are not
# converted in code.
_MD_CODE_PATTERN = re.compile(
    r"(```.*?(?:```|\Z)|~~~.*?(?:~~~|\Z)|`[^`\n]+`)", re.DOTALL
)


def _sub_outside_code(pattern: re.Pattern, repl, md: str) -> str:
    """Replace the matches of a pattern which are not in markdown code."""
    # The pattern has a single group, so every second part is code
    parts = _MD_CODE_PATTERN.split(md)
    parts[::2] = [pattern.sub(repl, part) for part in parts[::2]]
    return "".join(parts)


def _utf16_length(text: str) -> int:
    """Length of a text the way Qt counts it.

    Qt positions count UTF-16 code units, while Python counts code points.
    They differ for characters outside of the Basic Multilingual Plane, like
    most emoji, which take two UTF-16 code units.
    """
    if text.isascii():
        return len(text)
    return len(text.encode("utf-16-le")) // 2


def _text_before_cursor(cursor: QTextCursor) -> str:
    """Text of the block in front of a text cursor."""
    cursor = QTextCursor(cursor)
    cursor.setPosition(cursor.position())
    cursor.movePosition(
        QTextCursor.MoveOperation.StartOfBlock,
        QTextCursor.MoveMode.KeepAnchor,
    )
    return cursor.selectedText()


def is_mention_href(href: str) -> bool:
    """Whether a link target refers to a mentioned user or entity."""
    return bool(_MENTION_HREF_PATTERN.match(href))


def mentions_to_display(md: str) -> str:
    """Prefix the label of stored mention links with their trigger.

    ``[Joe](user:admin)`` becomes ``[@Joe](user:admin)`` and
    ``[v003](version:id)`` becomes ``[@@v003](version:id)`` so mentions
    are displayed the way they are typed. Code is left as it is.

    Args:
        md: Markdown text as stored on the server.

    Returns:
        Markdown text to display.
    """
    def repl(match: re.Match) -> str:
        trigger = MENTION_TRIGGERS[match["type"]]
        return f"[{trigger}{match['label']}]({match['ref']})"

    return _sub_outside_code(MENTION_LINK_PATTERN, repl, md)


def mentions_to_storage(md: str) -> str:
    """Convert displayed mentions back to stored mention links.

    Reverts :func:`mentions_to_display`. Only mentions picked from the
    completer are mentions: text like ``@Full Name`` typed without picking
    the user stays text, the same as in the web frontend.

    Args:
        md: Markdown text of the displayed document.

    Returns:
        Markdown text to store on the server.
    """
    def repl(match: re.Match) -> str:
        # Qt may wrap long lines in the middle of a label
        label = " ".join(match["label"].split())
        return f"[{label}]({match['ref']})"

    return _sub_outside_code(MENTION_LINK_PATTERN, repl, md)


class MentionCompleterDelegate(QStyledItemDelegate):
    """Display users with their icon and entities with their context."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.icon_size = 20
        self._user_pixmap = {}
        self._entity_pixmap = {}

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index,
    ) -> None:
        """Paint a user or entity which can be mentioned."""
        item: User | EntityMention | None = index.data(
            Qt.ItemDataRole.UserRole
        )
        if not item:
            super().paint(painter, option, index)
            return

        # Draw background
        palette = get_ayon_style().model.base_palette
        text_color = palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Text
        )
        bg_role = QPalette.ColorRole.Midlight
        if option.state & QStyle.StateFlag.State_Selected:
            bg_role = QPalette.ColorRole.Light
        painter.fillRect(
            option.rect, palette.color(QPalette.ColorGroup.Active, bg_role)
        )
        painter.setPen(text_color)

        text_rect = option.rect.adjusted(4, 0, -4, 0)
        if isinstance(item, User):
            self._paint_user_icon(painter, text_rect, item)
            text_rect.adjust(self.icon_size + 8, 0, 0, 0)
            painter.drawText(
                text_rect, Qt.AlignmentFlag.AlignVCenter, item.full_name
            )
            return

        self._paint_entity_icon(painter, text_rect, item, text_color)
        text_rect.adjust(self.icon_size + 8, 0, 0, 0)

        # Suffix on the right, e.g. how long ago a version was created
        if item.suffix:
            painter.setPen(palette.color(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
            ))
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                item.suffix,
            )
            text_rect.adjust(
                0,
                0,
                -painter.fontMetrics().horizontalAdvance(item.suffix) - 8,
                0,
            )
            painter.setPen(text_color)

        # "context - label" with the label emphasized
        painter.save()
        if item.context:
            context = f"{item.context} - "
            painter.drawText(
                text_rect, Qt.AlignmentFlag.AlignVCenter, context
            )
            text_rect.adjust(
                painter.fontMetrics().horizontalAdvance(context), 0, 0, 0
            )
        font = painter.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                item.label or "",
                Qt.TextElideMode.ElideRight,
                text_rect.width(),
            ),
        )
        painter.restore()

    def _paint_entity_icon(
        self, painter: QPainter, rect, item: EntityMention, text_color
    ) -> None:
        """Paint the icon of the product type or task type in its color."""
        color = QColor(item.color)
        if not item.color or not color.isValid():
            color = text_color
        key = (item.entity_type, item.icon, color.name())
        pixmap = self._entity_pixmap.get(key)
        if pixmap is None:
            icon_name = item.icon
            if get_icon_name_char(icon_name) is None:
                # Type without an icon or with one unknown to the icon font
                icon_name = _MENTION_ICONS.get(item.entity_type, "")
            pixmap = QPixmap()
            if icon_name:
                icon_size = self.icon_size - 2
                pixmap = get_icon(icon_name, color=color.name()).pixmap(
                    icon_size, icon_size
                )
            self._entity_pixmap[key] = pixmap

        if pixmap.isNull():
            return
        ratio = pixmap.devicePixelRatio() or 1.0
        painter.drawPixmap(
            rect.x() + (self.icon_size - int(pixmap.width() / ratio)) // 2,
            rect.y() + (rect.height() - int(pixmap.height() / ratio)) // 2,
            pixmap,
        )

    def _paint_user_icon(self, painter: QPainter, rect, user: User) -> None:
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

        icon_y = rect.y() + (rect.height() - self.icon_size) // 2
        painter.drawPixmap(rect.x(), icon_y, icon_pixmap)

    def sizeHint(
        self,
        option: QStyleOptionViewItem,
        index,
    ) -> QSize:
        """Return size hint for completer items."""
        return QSize(option.rect.width(), self.icon_size + 8)


class MentionCompleter(QObject):
    """Mention completion and highlighting for a QTextEdit.

    Typing ``@``, ``@@`` or ``@@@`` at the start of a word opens a popup
    listing the users, versions or tasks which can be mentioned. The picked
    item is inserted as a link, e.g. ``@@v003`` linking to ``version:<id>``,
    so the document's markdown contains ``[@@v003](version:<id>)``. Use
    :func:`mentions_to_display` and :func:`mentions_to_storage` to convert
    from and to the markdown stored on the server.

    The versions and tasks don't have to be known up front:
    :attr:`entities_requested` is emitted each time the popup opens for
    them, to answer with :meth:`set_entities` whenever they are available.

    Signals:
        entities_requested: The popup opened to mention a version or task.

    Args:
        text_edit: The QTextEdit to complete mentions in.
        users: Users which can be mentioned.
    """

    entities_requested = Signal()

    # Events which can type text, to not make it part of a mention's link
    _LEAVE_EVENTS = frozenset((
        QEvent.Type.KeyPress, QEvent.Type.InputMethod,
    ))

    def __init__(
        self, text_edit: QTextEdit, users: list[User] | None = None
    ) -> None:
        super().__init__(text_edit)
        self._text_edit = text_edit
        self._items: dict[str, list] = {"@": [], "@@": [], "@@@": []}
        # Trigger the completer model is currently populated for
        self._trigger = ""
        # Whether the versions and tasks are waited for
        self._entities_loading = False
        # Whether the entities were requested for the open popup
        self._entities_requested = False

        self._completer = QCompleter(self)
        self._completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setMaxVisibleItems(4)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setWidget(text_edit)

        popup = self._completer.popup()
        popup.setItemDelegate(MentionCompleterDelegate(popup))
        popup.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, True)

        self._highlighter = MentionHighlighter(text_edit.document())
        self.set_users(users or [])

        self._completer.activated[QModelIndex].connect(self._insert_mention)
        text_edit.textChanged.connect(self._update_popup)
        # Close the popup when the text cursor leaves the mention
        text_edit.cursorPositionChanged.connect(self._update_popup)
        text_edit.installEventFilter(self)

    def set_users(self, users: list[User]) -> None:
        """Set the users which can be mentioned with ``@``."""
        self._items["@"] = users
        self._trigger = ""

    def set_entities(
        self,
        versions: list[EntityMention] | None = None,
        tasks: list[EntityMention] | None = None,
    ) -> None:
        """Set the versions (``@@``) and tasks (``@@@``) to mention.

        An open popup is updated, so this can be called at any time after
        :attr:`entities_requested`.
        """
        self._items["@@"] = versions or []
        self._items["@@@"] = tasks or []
        self._entities_loading = False
        self._trigger = ""
        self._update_popup()

    def clear_entities(self) -> None:
        """Forget the versions and tasks, e.g. of another version.

        The popup shows them as loading until :meth:`set_entities` is
        called, which is asked for with :attr:`entities_requested` the next
        time the popup opens.
        """
        self._items["@@"] = []
        self._items["@@@"] = []
        self._entities_loading = True
        self._entities_requested = False
        self._trigger = ""
        self._update_popup()

    def popup_visible(self) -> bool:
        """Whether the popup to pick a mention is open."""
        return self._completer.popup().isVisible()

    def insert_trigger(self, trigger: str) -> None:
        """Type a trigger at the text cursor to open the popup.

        A mention which is being typed is replaced, so the type of the
        mention can be switched.

        Args:
            trigger: ``@``, ``@@`` or ``@@@``.
        """
        cursor = self._text_edit.textCursor()
        found = self._find_trigger()
        if found is not None:
            cursor.setPosition(found[0], QTextCursor.MoveMode.KeepAnchor)
        else:
            # A mention is only completed at the start of a word
            text_before = _text_before_cursor(cursor)
            if text_before and not text_before[-1].isspace():
                trigger = f" {trigger}"
        cursor.insertText(trigger)
        self._text_edit.setTextCursor(cursor)

    def handle_key_press(self, event) -> bool:
        """Complete the mention being typed or delete a mention as a whole.

        Returns:
            True if the event was handled, False otherwise.
        """
        key = event.key()
        if key in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            return self._delete_mention(key == Qt.Key.Key_Backspace)

        if not self.popup_visible() or key not in (
            Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab
        ):
            return False

        index = self._completer.popup().currentIndex()
        if not index.isValid():
            return False
        if self._find_trigger() is None:
            # Nothing to complete, don't swallow the key
            self._completer.popup().hide()
            return False
        self._insert_mention(index)
        return True

    def _mention_range(self, position: int) -> tuple[int, int] | None:
        """Get the start and end of the mention a character is part of.

        Args:
            position: Position of the character in the document.
        """
        block = self._text_edit.document().findBlock(position)
        start = end = -1
        href = ""
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if not fragment.isValid():
                continue
            fragment_href = fragment.charFormat().anchorHref()
            if fragment_href != href or fragment.position() != end:
                if start <= position < end:
                    break
                # A mention may consist of fragments in different styles
                href = fragment_href
                start = fragment.position()
            end = fragment.position() + fragment.length()

        if is_mention_href(href) and start <= position < end:
            return start, end
        return None

    def _delete_mention(self, backwards: bool) -> bool:
        """Delete the mention next to the text cursor as a whole.

        Args:
            backwards: Delete the mention in front of the text cursor
                instead of the one after it.

        Returns:
            True if a mention was deleted, False otherwise.
        """
        cursor = self._text_edit.textCursor()
        if cursor.hasSelection() or self._text_edit.isReadOnly():
            return False

        position = cursor.position() - 1 if backwards else cursor.position()
        mention_range = self._mention_range(position)
        if mention_range is None:
            return False

        cursor.setPosition(mention_range[0])
        cursor.setPosition(mention_range[1], QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self._text_edit.setTextCursor(cursor)
        return True

    def _find_trigger(self) -> tuple[int, str, str] | None:
        """Find the mention being typed in front of the text cursor.

        Returns:
            Position of the trigger in the document, the trigger and the
            search text typed after it. None if no mention is being typed.
        """
        cursor = self._text_edit.textCursor()
        text_before = _text_before_cursor(cursor)
        match = _MENTION_TRIGGER_PATTERN.search(text_before)
        if not match or self._in_code(cursor, text_before):
            return None
        # The mention being typed ends at the text cursor
        typed = match["trigger"] + match["prefix"]
        start = cursor.position() - _utf16_length(typed)
        return start, match["trigger"], match["prefix"]

    @staticmethod
    def _in_code(cursor: QTextCursor, text_before: str) -> bool:
        """Whether the text cursor is in a code block or inline code.

        Mentions are not completed in code, there an ``@`` is just text.

        Args:
            cursor: The text cursor.
            text_before: Text of the block in front of the text cursor.
        """
        block = cursor.block()
        # Code block of loaded markdown
        if block.blockFormat().nonBreakableLines():
            return True
        # Code block being typed, the highlighter marks the blocks of an
        # open fence with state 1.
        if block.previous().userState() == 1 or block.text().startswith(
            "```"
        ):
            return True
        # Inline code of loaded markdown or of the code style button
        if cursor.charFormat().fontFixedPitch():
            return True
        # Inline code being typed
        return text_before.count("`") % 2 == 1

    def _populate(self, trigger: str) -> None:
        """Fill the completer with the items of a trigger."""
        if trigger == self._trigger:
            return
        self._trigger = trigger

        model = QStandardItemModel(self._completer)
        for item in self._items[trigger]:
            if isinstance(item, User):
                text = item.full_name
            else:
                # Both may be missing in data coming from a server
                text = f"{item.context or ''} {item.label or ''}".strip()
            row = QStandardItem(text)
            row.setData(item, Qt.ItemDataRole.UserRole)
            model.appendRow(row)
        if not model.rowCount():
            text = f"No {_MENTION_NOUNS[trigger]} to mention"
            if trigger != "@" and self._entities_loading:
                text = f"Loading {_MENTION_NOUNS[trigger]}..."
            row = QStandardItem(text)
            row.setFlags(Qt.ItemFlag.NoItemFlags)
            model.appendRow(row)
        self._completer.setModel(model)

    def _update_popup(self) -> None:
        """Show the popup while a mention is being typed."""
        popup = self._completer.popup()
        found = None
        if not self._text_edit.isReadOnly():
            found = self._find_trigger()
        if found is None:
            self._entities_requested = False
            popup.hide()
            return

        _, trigger, prefix = found
        if trigger != "@" and not self._entities_requested:
            # Once each time the popup opens for versions or tasks, typing
            # "@@@" passes "@@" and one answer has both of them.
            self._entities_requested = True
            self.entities_requested.emit()
        self._populate(trigger)
        self._completer.setCompletionPrefix(prefix)
        row_count = self._completer.completionCount()
        if not row_count:
            popup.hide()
            return

        # Show the popup above the QTextEdit with the same width
        row_count = min(row_count, self._completer.maxVisibleItems())
        height = popup.sizeHintForRow(0) * row_count + 2 * popup.frameWidth()
        top_left = self._text_edit.mapToGlobal(
            self._text_edit.rect().topLeft()
        )
        popup.setGeometry(
            top_left.x(),
            top_left.y() - height,
            self._text_edit.width(),
            height,
        )
        popup.show()
        popup.setCurrentIndex(self._completer.completionModel().index(0, 0))

    def eventFilter(self, obj, event) -> bool:
        if event.type() in self._LEAVE_EVENTS:
            self._leave_mention()
        return False

    def _leave_mention(self) -> None:
        """Don't make text typed next to a mention part of its link."""
        cursor = self._text_edit.textCursor()
        char_fmt = self._text_edit.currentCharFormat()
        if cursor.hasSelection() or not is_mention_href(char_fmt.anchorHref()):
            return

        if not cursor.atBlockStart() and not cursor.atBlockEnd():
            next_cursor = QTextCursor(cursor)
            next_cursor.movePosition(QTextCursor.MoveOperation.NextCharacter)
            next_href = next_cursor.charFormat().anchorHref()
            if next_href == cursor.charFormat().anchorHref():
                # Inside of the mention
                return

        char_fmt.setAnchor(False)
        char_fmt.clearProperty(QTextFormat.Property.AnchorHref)
        self._text_edit.setCurrentCharFormat(char_fmt)

    def _insert_mention(self, index: QModelIndex) -> None:
        """Replace the mention being typed with a link to the picked item."""
        item: User | EntityMention | None = index.data(
            Qt.ItemDataRole.UserRole
        )
        found = self._find_trigger()
        self._completer.popup().hide()
        if item is None or found is None:
            return

        if isinstance(item, User):
            entity_type, entity_id, label = "user", item.name, item.full_name
        else:
            entity_type, entity_id, label = (
                item.entity_type, item.id, item.label
            )

        cursor = self._text_edit.textCursor()
        end = cursor.position()
        start = found[0]

        # Keep the surrounding style, the text typed after the mention
        # should not be part of the link.
        plain_fmt = cursor.charFormat()
        plain_fmt.setAnchor(False)
        plain_fmt.clearProperty(QTextFormat.Property.AnchorHref)
        mention_fmt = QTextCharFormat(plain_fmt)
        mention_fmt.setAnchor(True)
        mention_fmt.setAnchorHref(f"{entity_type}:{entity_id}")

        cursor.beginEditBlock()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(
            f"{MENTION_TRIGGERS[entity_type]}{label}", mention_fmt
        )
        cursor.insertText(" ", plain_fmt)
        cursor.endEditBlock()
        self._text_edit.setTextCursor(cursor)


class MentionHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for mentions, raw URLs, and code spans.

    Operates on block-local plain text so positions are always correct
    regardless of any rich-text formatting already present in the document
    (bold, italic, headings, code spans, etc.).

    Patterns highlighted:

    - Fenced code blocks (```\\`\\`\\` ... \\`\\`\\```) spanning multiple
      lines - black background, white monospace text.  Block state ``1``
      tracks whether the current block is inside a fence.
    - Qt-rendered code blocks (from ``setMarkdown()``) — detected via
      ``nonBreakableLines`` on the block format.
    - Qt-rendered inline code spans (from ``setMarkdown()``) — detected via
      ``fontFixedPitch`` on individual text fragments.
    - Inline code spans (`` \\`code\\` ``) in raw (un-rendered) text — same
      style, detected by backtick regex.
    - Links to ``user:name``, ``version:id`` or ``task:id`` — mentions
      inserted by :class:`MentionCompleter` or loaded from markdown.
    - ``https?://…`` — raw URL

    Text like ``@name`` which is not a link is not a mention and is not
    highlighted as one.

    Args:
        document: The QTextDocument to attach to.
    """

    _P_RAW_LINK = re.compile(r"https?://\S+")
    # Inline code: single backtick pair on the same line.
    _P_CODE_INLINE = re.compile(r"`[^`\n]+`")

    def __init__(self, document) -> None:
        super().__init__(document)
        pal = get_ayon_style().model.base_palette
        self._mention_fmt = QTextCharFormat()
        self._mention_fmt.setForeground(pal.link())
        self._code_fmt = None
        self._plain_fmt = self._get_plain_char_format()

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
            self.setFormat(0, _utf16_length(text), code_fmt)
            # A line starting with ``` closes the fence.
            if text.startswith("```"):
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return

        if text.startswith("```"):
            self.setFormat(0, _utf16_length(text), code_fmt)
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
            self.setFormat(0, _utf16_length(text), code_fmt)
            return

        # ── Raw URLs (applied before inline code) ────────────────────────
        self.setFormat(0, _utf16_length(text), self._plain_fmt)

        for m in self._P_RAW_LINK.finditer(text):
            self._set_text_format(text, m.start(), m.end(), self._mention_fmt)

        # ── Inline code (overrides URL formatting) ───────────────────────

        # Raw backtick syntax `code` — detected in plain text for live
        # editing where backtick characters are still present:
        for m in self._P_CODE_INLINE.finditer(text):
            self._set_text_format(text, m.start(), m.end(), code_fmt)

        # ── Rich text fragments ──────────────────────────────────────────
        # Qt-rendered inline code spans — after setMarkdown() the backticks
        # are consumed and individual fragments carry fontFixedPitch=True.
        # Mentions are links to "user:name", "version:id" or "task:id".
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            it += 1
            if not fragment.isValid():
                continue
            char_fmt = fragment.charFormat()
            if char_fmt.fontFixedPitch():
                fmt = code_fmt
            elif is_mention_href(char_fmt.anchorHref()):
                fmt = self._mention_fmt
            else:
                continue
            self.setFormat(
                fragment.position() - block.position(), fragment.length(), fmt
            )

    def _set_text_format(
        self, text: str, start: int, end: int, fmt: QTextCharFormat
    ) -> None:
        """Format a range of the block given as indexes of its text.

        ``setFormat()`` counts UTF-16 code units like Qt does, which are
        not the indexes of a Python string once the text has characters
        like emoji in it.
        """
        if not text.isascii():
            end = _utf16_length(text[:end])
            start = _utf16_length(text[:start])
        self.setFormat(start, end - start, fmt)

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

    def _get_plain_char_format(self) -> QTextCharFormat:
        fmt = QTextCharFormat()
        pal = get_ayon_style().model.base_palette
        fmt.setForeground(pal.text())
        return fmt


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
