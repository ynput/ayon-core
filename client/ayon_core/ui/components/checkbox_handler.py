"""Checkbox handler for markdown checkboxes in QTextEdit."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from qtmaterialsymbols import get_icon
from qtpy.QtCore import (
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSizeF,
    Signal,
)
from qtpy.QtGui import (
    QPainter,
    QPixmap,
    QPyTextObject,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
    QFontMetrics,
    QTextListFormat,
)
from qtpy.QtWidgets import QTextEdit


log = logging.getLogger(__name__)

# Custom format type for checkboxes (must be unique)
CHECKBOX_FORMAT_TYPE = QTextFormat.ObjectTypes.UserObject + 1

# Property keys for checkbox data stored in QTextCharFormat
CHECKBOX_CHECKED_PROP = 1
CHECKBOX_INDEX_PROP = 2

# Icon configuration
UNCHECKED_ICON = "radio_button_unchecked"
UNCHECKED_COLOR = "#FFFFFF"
CHECKED_ICON = "check_circle"
CHECKED_COLOR = "#4CAF50"

MD_DIALECT = QTextDocument.MarkdownFeature.MarkdownDialectGitHub

_PH_RE = re.compile(r"[*_`]+$")


@dataclass
class CheckboxItem:
    """Represents a checkbox item in the document.

    Attributes:
        index: Unique index of the checkbox.
        checked: Whether the checkbox is checked.
        text: Text following the checkbox.
        line_number: Line number in the original markdown.
        prefix: Characters before the checkbox (e.g., "- ", "* ").
        doc_position: Character position of the \\ufffc object in the
            document, or -1 if not yet placed.
    """

    index: int
    checked: bool
    text: str
    line_number: int
    prefix: str = "- "
    doc_position: int = field(default=-1)


class CheckboxTextObject(QPyTextObject):
    """Custom text object for rendering checkbox icons in QTextDocument.

    Uses Material icons to render checkboxes:
    - Unchecked: white radio_button_unchecked
    - Checked: green check_circle
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._icon_cache: dict[bool, QPixmap] = {}

    def intrinsicSize(
        self,
        doc: QTextDocument,
        posInDocument: int,
        format: QTextFormat,
    ) -> QSizeF:
        """Return the size of the checkbox icon.

        Args:
            doc: The document containing the object.
            posInDocument: Position in the document.
            format: The text format of the object.

        Returns:
            Size of the checkbox icon based on font size.
        """
        font = doc.defaultFont()
        size = max(font.pointSizeF() * 1.4, 14)
        return QSizeF(size, size)

    def drawObject(
        self,
        painter: QPainter,
        rect: QRectF | QRect,
        doc: QTextDocument,
        posInDocument: int,
        format: QTextFormat,
    ) -> None:
        """Draw the checkbox icon.

        Args:
            painter: The painter to draw with.
            rect: The rectangle to draw in.
            doc: The document containing the object.
            posInDocument: Position in the document.
            format: The text format containing checkbox state.
        """
        is_checked = format.property(CHECKBOX_CHECKED_PROP)

        if is_checked:
            icon = get_icon(CHECKED_ICON, color=CHECKED_COLOR)
        else:
            icon = get_icon(UNCHECKED_ICON, color=UNCHECKED_COLOR)

        size = int(min(rect.width(), rect.height()))
        pixmap = icon.pixmap(size, size)

        # Vertically center the icon relative to text ascent
        font_metrics = QFontMetrics(doc.defaultFont())
        ascent = font_metrics.ascent()
        y_offset = (ascent - size) // 3
        draw_point = rect.topLeft().toPoint() + QPoint(0, -y_offset)

        painter.drawPixmap(draw_point, pixmap)


class CheckboxHandler(QObject):
    """Handles checkbox parsing, rendering, and state management.

    This class manages:
    - Parsing markdown to extract checkbox items
    - Registering custom text objects for checkbox rendering
    - Tracking checkbox state and positions
    - Converting back to markdown format

    Signals:
        checklist_changed: Emitted when any checkbox state changes.
    """

    checklist_changed = Signal()

    # GitHub-flavored markdown checkbox patterns
    # Matches: - [ ] text, - [x] text, * [ ] text, * [X] text, + [ ] text
    CHECKBOX_PATTERN = re.compile(
        r"^(\s*[-*+]\s+)\[([xX ])\]\s*(.*)$", re.MULTILINE
    )

    def __init__(self, text_edit: QTextEdit, parent: QObject | None = None):
        """Initialize the checkbox handler.

        Args:
            text_edit: The QTextEdit widget to manage checkboxes for.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._text_edit = text_edit
        self._checkboxes: list[CheckboxItem] = []
        self._checkbox_object: CheckboxTextObject | None = None
        self._original_markdown: str = ""
        self._register_handler()

    def _register_handler(self) -> None:
        """Register the custom checkbox text object with the document."""
        self._checkbox_object = CheckboxTextObject(self)
        doc = self._text_edit.document()
        doc_layout = doc.documentLayout()
        doc_layout.registerHandler(CHECKBOX_FORMAT_TYPE, self._checkbox_object)

    def parse_and_render(self, markdown: str) -> None:
        """Parse markdown and render checkboxes in the document.

        Extracts checkbox items from markdown, stores their state,
        and renders them as custom text objects with icons.

        Args:
            markdown: The markdown string containing checkboxes.
        """
        self._original_markdown = markdown
        self._checkboxes.clear()

        # Find all checkbox patterns
        lines = markdown.split("\n")
        processed_lines: list[str] = []
        checkbox_index = 0

        for line_num, line in enumerate(lines):
            match = self.CHECKBOX_PATTERN.match(line)
            if match:
                prefix = match.group(1)
                checked_char = match.group(2)
                text = match.group(3)
                is_checked = checked_char.lower() == "x"

                # Store checkbox info (doc_position filled after insertion)
                self._checkboxes.append(
                    CheckboxItem(
                        index=checkbox_index,
                        checked=is_checked,
                        text=text,
                        line_number=line_num,
                        prefix=prefix,
                    )
                )

                # Replace checkbox syntax with placeholder
                # We'll insert the actual object after setting plain text
                processed_lines.append(f"{prefix}\ufffc {text}")
                checkbox_index += 1
            else:
                processed_lines.append(line)

        # Set the processed text
        processed_text = "\n".join(processed_lines)
        self._text_edit.setMarkdown(processed_text)
        self._remove_list_bullets()

        # Now insert checkbox objects at placeholder positions
        self._insert_checkbox_objects()

    def _remove_list_bullets(self) -> None:
        """Remove bullet markers from list blocks containing checkboxes and
        correct the indentation to match front-end."""
        doc = self._text_edit.document()
        processed_lists: set[int] = set()

        block = doc.begin()
        while block.isValid():
            text_list = block.textList()
            if text_list and id(text_list) not in processed_lists:
                list_key = text_list.item(0).position()
                if "\ufffc" in block.text():
                    fmt = text_list.format()
                    fmt.setStyle(QTextListFormat.Style.ListStyleUndefined)
                    fmt.setIndent(0)
                    text_list.setFormat(fmt)
                    processed_lists.add(list_key)
            block = block.next()

    def _insert_checkbox_objects(self) -> None:
        """Insert checkbox custom objects at placeholder positions."""
        doc = self._text_edit.document()
        doc.blockSignals(True)

        cursor = QTextCursor(doc)
        cursor.beginEditBlock()

        # Find all placeholder characters and replace with checkbox objects
        text = doc.toPlainText()
        offset = 0

        for i, cb in enumerate(self._checkboxes):
            # Find the placeholder character (OBJECT REPLACEMENT CHARACTER)
            pos = text.find("\ufffc", offset)
            if pos == -1:
                log.warning("Could not find placeholder for checkbox %d", i)
                continue

            # Create format for the checkbox
            fmt = QTextCharFormat()
            fmt.setObjectType(CHECKBOX_FORMAT_TYPE)
            fmt.setProperty(CHECKBOX_CHECKED_PROP, cb.checked)
            fmt.setProperty(CHECKBOX_INDEX_PROP, cb.index)
            fmt.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignBaseline
            )

            # Select and replace the placeholder
            cursor.setPosition(pos)
            cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText("\ufffc", fmt)

            # Store the document position for fast hit-testing
            cb.doc_position = pos

            offset = pos + 1

        cursor.endEditBlock()
        doc.blockSignals(False)

    def get_checkbox_at_position(self, pos: int) -> int | None:
        """Get the checkbox index at the given document position.

        Args:
            pos: Position in the document (one past the \\ufffc char).

        Returns:
            Checkbox index if found, None otherwise.
        """
        doc = self._text_edit.document()
        cursor = QTextCursor(doc)
        cursor.setPosition(pos)
        fmt = cursor.charFormat()
        fmt_type = fmt.objectType()

        if fmt_type == CHECKBOX_FORMAT_TYPE:
            return fmt.property(CHECKBOX_INDEX_PROP)
        return None

    def find_checkbox_at_click(
        self, click_pos: "QPoint", content_offset: "QPoint | None" = None
    ) -> tuple[bool, int | None]:
        """Find the checkbox hit by a viewport click using stored positions.

        Uses the cached ``doc_position`` on each :class:`CheckboxItem`
        instead of scanning the full document text, making hit-testing O(n)
        in the number of checkboxes rather than O(len(document)).

        Args:
            click_pos: Click position in viewport coordinates.
            content_offset: Optional scroll offset (x, y) as a QPoint.
                Defaults to (0, 0) when not provided.

        Returns:
            ``(True, doc_position + 1)`` when the click lands on a checkbox,
            ``(False, None)`` otherwise.
        """
        if not self._checkboxes:
            return False, None

        doc = self._text_edit.document()
        ox = content_offset.x() if content_offset else 0
        oy = content_offset.y() if content_offset else 0

        for cb in self._checkboxes:
            pos = cb.doc_position
            if pos < 0:
                continue

            cursor = QTextCursor(doc)
            cursor.setPosition(pos)
            block = cursor.block()
            block_layout = block.layout()

            if not block_layout:
                continue

            rel_pos = pos - block.position()
            line = block_layout.lineForTextPosition(rel_pos)
            if not line.isValid():
                continue

            x1 = line.cursorToX(rel_pos)[0]  # type: ignore[index]
            x2 = line.cursorToX(rel_pos + 1)[0]  # type: ignore[index]
            y = line.y() + block_layout.position().y()
            h = line.height()

            rect = QRectF(x1 + ox, y + oy, x2 - x1, h)
            if rect.contains(QPointF(click_pos)):
                return True, pos + 1

        return False, None

    def toggle_checkbox(self, index: int) -> bool:
        """Toggle a checkbox by its index.

        Args:
            index: The index of the checkbox to toggle.

        Returns:
            True if the checkbox was toggled, False otherwise.
        """
        if not 0 <= index < len(self._checkboxes):
            return False

        # Toggle the state
        self._checkboxes[index].checked = not self._checkboxes[index].checked

        # Update the document
        self._update_checkbox_in_document(index)

        # Emit signal
        self.checklist_changed.emit()
        return True

    def _update_checkbox_in_document(self, index: int) -> None:
        """Update a single checkbox display in the document.

        Args:
            index: The index of the checkbox to update.
        """
        doc = self._text_edit.document()
        cb = self._checkboxes[index]

        # Block signals to prevent triggering format_comment_on_change
        # which would clear all formatting including checkboxes
        doc.blockSignals(True)

        try:
            pos = cb.doc_position
            if pos < 0:
                # Fall back to scanning if position is unknown
                text = doc.toPlainText()
                count = 0
                for i, char in enumerate(text):
                    if char == "\ufffc":
                        if count == index:
                            pos = i
                            break
                        count += 1

            if pos < 0:
                log.warning(
                    "Cannot find document position for checkbox %d", index
                )
                return

            cursor = QTextCursor(doc)
            cursor.setPosition(pos)
            cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)

            fmt = QTextCharFormat()
            fmt.setObjectType(CHECKBOX_FORMAT_TYPE)
            fmt.setProperty(CHECKBOX_CHECKED_PROP, cb.checked)
            fmt.setProperty(CHECKBOX_INDEX_PROP, cb.index)
            fmt.setVerticalAlignment(
                QTextCharFormat.VerticalAlignment.AlignBaseline
            )

            cursor.setCharFormat(fmt)
        finally:
            doc.blockSignals(False)

    def add_checkbox(
        self,
        checked: bool = False,
        prefix: str = "- ",
        doc_position: int = -1,
    ) -> CheckboxItem:
        """Append a new checkbox to the tracked list.

        This is the public API for adding a checkbox programmatically
        (e.g. when the user presses Enter on a checkbox line or clicks
        the checklist toolbar button).  The caller is responsible for
        inserting the actual ``\\ufffc`` character into the document and
        then updating :attr:`CheckboxItem.doc_position`.

        Args:
            checked: Initial checked state.
            prefix: Markdown list prefix (e.g. ``"- "``).
            doc_position: Document character position of the ``\\ufffc``
                object, or ``-1`` if not yet known.

        Returns:
            The newly created :class:`CheckboxItem`.
        """
        new_index = len(self._checkboxes)
        item = CheckboxItem(
            index=new_index,
            checked=checked,
            text="",
            line_number=-1,
            prefix=prefix,
            doc_position=doc_position,
        )
        self._checkboxes.append(item)
        return item

    def remove_checkbox(self, index: int) -> None:
        """Remove a checkbox from the tracked list.

        Re-indexes the Python list **and** patches the stale
        ``CHECKBOX_INDEX_PROP`` values stored in the live
        ``QTextDocument`` so that subsequent hit-tests via
        :meth:`get_checkbox_at_position` return correct indices.

        Args:
            index: The index of the checkbox to remove.
        """
        if not 0 <= index < len(self._checkboxes):
            return

        self._checkboxes.pop(index)

        # Re-index the Python list and sync each affected document char format.
        doc = self._text_edit.document()
        doc.blockSignals(True)
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        try:
            for i, cb in enumerate(self._checkboxes[index:], start=index):
                cb.index = i
                pos = cb.doc_position
                if pos < 0:
                    continue
                cursor.setPosition(pos)
                cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setObjectType(CHECKBOX_FORMAT_TYPE)
                fmt.setProperty(CHECKBOX_CHECKED_PROP, cb.checked)
                fmt.setProperty(CHECKBOX_INDEX_PROP, cb.index)
                fmt.setVerticalAlignment(
                    QTextCharFormat.VerticalAlignment.AlignBaseline
                )
                cursor.setCharFormat(fmt)
        except Exception:
            log.warning(
                "Failed to re-index checkboxes in document", exc_info=True
            )
        finally:
            cursor.endEditBlock()
            doc.blockSignals(False)

    def remove_last_checkbox(self) -> bool:
        """Remove the last checkbox from the tracked list.

        Used when the user presses Enter on an empty checkbox line to
        terminate the list.

        Returns:
            True if a checkbox was removed, False if the list was empty.
        """
        if not self._checkboxes:
            return False
        self._checkboxes.pop()
        return True

    def to_markdown(self) -> str:
        """Reconstruct markdown with current checkbox states.

        Returns:
            GitHub-flavored markdown string with checkbox syntax.
        """
        if not self._checkboxes:
            return self._text_edit.toMarkdown(MD_DIALECT)

        # Get current text and replace placeholders with checkbox syntax
        # we use toMarkdown() to make sure the other formatted items have
        # already been dealt with.
        text = self._text_edit.toMarkdown(MD_DIALECT)
        lines = text.split("\n")
        result_lines: list[str] = []

        checkbox_iter = iter(self._checkboxes)
        current_cb = next(checkbox_iter, None)

        for line in lines:
            if "\ufffc" in line and current_cb:
                checked_char = "x" if current_cb.checked else " "
                cb_idx = line.index("\ufffc")
                raw_after = line[cb_idx + 1 :]  # everything after \ufffc
                raw_after = raw_after.lstrip(" ")  # drop the space Qt inserts
                raw_after = _PH_RE.sub("", raw_after).rstrip()
                line = f"{current_cb.prefix}[{checked_char}] {raw_after}"
                current_cb = next(checkbox_iter, None)
            result_lines.append(line)

        return "\n".join(result_lines)

    @property
    def checkboxes(self) -> list[CheckboxItem]:
        """Get the list of checkbox items.

        Returns:
            List of CheckboxItem objects.
        """
        return self._checkboxes.copy()

    def has_checkboxes(self) -> bool:
        """Check if the document contains any checkboxes.

        Returns:
            True if there are checkboxes, False otherwise.
        """
        return bool(self._checkboxes)

    @staticmethod
    def contains_checkboxes(markdown: str) -> bool:
        """Check if markdown text contains checkbox syntax.

        Args:
            markdown: The markdown string to check.

        Returns:
            True if checkbox syntax is found, False otherwise.
        """
        return bool(CheckboxHandler.CHECKBOX_PATTERN.search(markdown))
