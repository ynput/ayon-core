"""Markdown text edit with mentions and checklists."""

from __future__ import annotations

import logging

from qtpy.QtCore import QPoint, Qt, Signal
from qtpy.QtGui import QTextCharFormat, QTextCursor, QTextDocument
from qtpy.QtWidgets import QTextEdit

from ..data_models import EntityMention, User
from ..variants import QTextEditVariants
from .checkbox_handler import (
    CHECKBOX_CHECKED_PROP,
    CHECKBOX_FORMAT_TYPE,
    CHECKBOX_INDEX_PROP,
    CheckboxHandler,
)
from .comment_completion import (
    MentionCompleter,
    apply_code_block_backgrounds,
    mentions_to_display,
    mentions_to_storage,
)
from .text_edit import AYTextEdit

logger = logging.getLogger(__name__)

MD_DIALECT = QTextDocument.MarkdownFeature.MarkdownDialectGitHub


class AYMarkdownEdit(AYTextEdit):
    """Text edit to display and edit the markdown of a comment.

    Supports GitHub-flavored markdown checkboxes (- [ ] and - [x]) which
    can be toggled even in read-only mode, and mentions of users (``@``),
    versions (``@@``) and tasks (``@@@``).

    Signals:
        checklist_changed: Emitted when a checkbox state changes.
        mention_entities_requested: Emitted when the popup to mention a
            version or task opens. Answer with
            :meth:`set_mention_entities`, right away or later.
    """

    Variants = QTextEditVariants
    checklist_changed = Signal()
    mention_entities_requested = Signal()

    # Text inserted in front of a new checkbox
    _checkbox_indent = ""

    def __init__(
        self,
        *args,
        user_list: list[User] | None = None,
        variant: Variants = Variants.Default,
        **kwargs,
    ) -> None:
        self._user_list: list[User] = user_list or []
        self._checkbox_handler: CheckboxHandler | None = None
        # Guard flag: when True, apply_code_block_backgrounds is a no-op.
        self._suppress_formatting: bool = False

        super().__init__(*args, variant=variant, **kwargs)
        # Enable mouse tracking on viewport to receive mouseMoveEvent
        self.viewport().setMouseTracking(True)
        self.document().setIndentWidth(22)  # pixels per indent level
        # automatic bullet lists
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoAll)

        self._mentions = MentionCompleter(self, self._user_list)
        self._mentions.entities_requested.connect(
            self.mention_entities_requested
        )
        self.document().contentsChanged.connect(self._on_contents_changed)

    def _on_contents_changed(self) -> None:
        apply_code_block_backgrounds(self)

    # MENTIONS ---------------------------------------------------------------

    def set_user_list(self, user_list: list[User]) -> None:
        """Set the users which can be mentioned with ``@``."""
        self._user_list = user_list
        self._mentions.set_users(user_list)

    def set_mention_entities(
        self,
        versions: list[EntityMention] | None = None,
        tasks: list[EntityMention] | None = None,
    ) -> None:
        """Set the versions (``@@``) and tasks (``@@@``) to mention.

        Either up front or, to only get them when they are needed, in
        response to :attr:`mention_entities_requested`.
        """
        self._mentions.set_entities(versions, tasks)

    def clear_mention_entities(self) -> None:
        """Forget the versions and tasks to mention.

        Call it when they are of another context than the one commented
        on now. They show as loading until :meth:`set_mention_entities`.
        """
        self._mentions.clear_entities()

    def insert_mention_trigger(self, trigger: str) -> None:
        """Type ``@``, ``@@`` or ``@@@`` at the text cursor to mention."""
        self._mentions.insert_trigger(trigger)
        self.setFocus()

    # MARKDOWN ---------------------------------------------------------------

    def set_markdown(self, md: str) -> None:
        """Set markdown content with checkbox and mention support.

        Args:
            md: Markdown text to display
        """
        md = mentions_to_display(md)
        if CheckboxHandler.contains_checkboxes(md):
            self._setup_checkbox_handler().parse_and_render(md)
        else:
            self.document().setMarkdown(md, MD_DIALECT)
        apply_code_block_backgrounds(self)

    def as_markdown(self) -> str:
        """Get the content as GitHub-flavored markdown.

        Checkboxes are returned in checkbox syntax (- [ ] and - [x])
        reflecting their current state and mentions as links like
        ``[label](user:name)``.

        Returns:
            Markdown string.
        """
        if self._checkbox_handler:
            md = self._checkbox_handler.to_markdown()
        else:
            md = self.document().toMarkdown(MD_DIALECT)
        return mentions_to_storage(md)

    def clear(self) -> None:
        """Remove the content and the style to type in.

        The text edit keeps the style of the last character as the one to
        continue typing in, also when all text is removed. Without the
        reset a next comment would start as the link, bold text or code
        the previous one ended with.
        """
        super().clear()
        self.setCurrentCharFormat(QTextCharFormat())

    def insertFromMimeData(self, source) -> None:
        """Paste without the underline of rich text.

        Rich text from the clipboard has its links underlined, also when
        copied from a comment. Markdown has no underline, it is written as
        emphasis: text typed after a pasted link continued its underline
        and ended up in the comment with ``_`` around it.
        """
        no_underline = QTextCharFormat()
        no_underline.setFontUnderline(False)

        cursor = self.textCursor()
        start = cursor.selectionStart()
        cursor.beginEditBlock()
        try:
            super().insertFromMimeData(source)
            cursor = self.textCursor()
            end = cursor.position()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(no_underline)
        finally:
            cursor.endEditBlock()
        self.mergeCurrentCharFormat(no_underline)

    # CHECKBOXES -------------------------------------------------------------

    def _setup_checkbox_handler(self) -> CheckboxHandler:
        """Initialize checkbox handler if not already done."""
        if self._checkbox_handler is None:
            self._checkbox_handler = CheckboxHandler(self)
            self._checkbox_handler.checklist_changed.connect(
                self._on_checklist_changed
            )
        return self._checkbox_handler

    def _on_checklist_changed(self) -> None:
        """Handle checkbox state changes."""
        self.checklist_changed.emit()

    def _insert_checkbox_at_cursor(self, cursor: QTextCursor) -> None:
        """Insert a new unchecked checkbox object at the cursor position.

        Inserts the custom checkbox object character (``\\ufffc``) and a
        trailing space, then records the document position on the
        :class:`CheckboxItem` for fast hit-testing.

        Args:
            cursor: Cursor at the insertion point; advanced past the
                inserted characters on return.
        """
        new_item = self._setup_checkbox_handler().add_checkbox()
        fmt = QTextCharFormat()
        fmt.setObjectType(CHECKBOX_FORMAT_TYPE)
        fmt.setProperty(CHECKBOX_CHECKED_PROP, False)
        fmt.setProperty(CHECKBOX_INDEX_PROP, new_item.index)
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignBaseline
        )
        cursor.insertText(self._checkbox_indent)
        new_item.doc_position = cursor.position()
        cursor.insertText("￼", fmt)
        cursor.insertText(" ")

    def _checkbox_index_at(self, pos: QPoint) -> int | None:
        """Get the index of the checkbox at a viewport position."""
        if not self._checkbox_handler:
            return None

        # Account for scroll offset
        scroll_offset = QPoint(
            -self.horizontalScrollBar().value(),
            -self.verticalScrollBar().value(),
        )
        is_checkbox, doc_pos = self._checkbox_handler.find_checkbox_at_click(
            pos, scroll_offset
        )
        if not is_checkbox or doc_pos is None:
            return None
        return self._checkbox_handler.get_checkbox_at_position(doc_pos)

    def _continue_checklist(self) -> bool:
        """Continue or end the checklist of the current line.

        Returns:
            True if a new checkbox was inserted. False if a regular new line
            should be inserted instead.
        """
        handler = self._checkbox_handler
        cursor = self.textCursor()
        block = cursor.block()
        token_pos = block.text().find("￼")
        if not handler or not handler.has_checkboxes() or token_pos == -1:
            return False

        self._suppress_formatting = True
        cursor.beginEditBlock()
        try:
            if block.text()[token_pos + 1:].strip():
                # Non-empty checkbox line → insert new checkbox
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.insertBlock()
                self._insert_checkbox_at_cursor(cursor)
                return True

            # Empty checkbox line → end the list
            cb_index = handler.get_checkbox_at_position(
                block.position() + token_pos + 1
            )
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()
            if cb_index is not None:
                handler.remove_checkbox(cb_index)
            return False
        finally:
            cursor.endEditBlock()
            self._suppress_formatting = False
            self.setTextCursor(cursor)

    # EVENTS -----------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        """Complete mentions and continue checklists on Enter."""
        if self._mentions.handle_key_press(event):
            event.accept()
            return

        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and self._continue_checklist()
        ):
            event.accept()
            return

        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        """Toggle checkboxes, also in read-only mode."""
        checkbox_idx = self._checkbox_index_at(event.pos())
        if checkbox_idx is not None:
            self._checkbox_handler.toggle_checkbox(checkbox_idx)
            self.viewport().update()
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        """Prevent text selection when double-clicking checkboxes."""
        if self._checkbox_index_at(event.pos()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Show arrow cursor over checkboxes, hand over clickable links."""
        if self._checkbox_index_at(event.pos()) is not None:
            shape = Qt.CursorShape.ArrowCursor
        elif not self.isReadOnly():
            shape = Qt.CursorShape.IBeamCursor
        elif self.anchorAt(event.pos()):
            shape = Qt.CursorShape.PointingHandCursor
        else:
            shape = Qt.CursorShape.ArrowCursor
        self.viewport().setCursor(shape)
        super().mouseMoveEvent(event)
