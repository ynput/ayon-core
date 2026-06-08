from __future__ import annotations

import logging
import os
from functools import partial

from qtpy import QtWidgets
from qtpy.QtCore import (
    QObject,
    QPoint,
    Qt,
    Signal,  # type: ignore
    Slot,  # type: ignore
)  # type: ignore
from qtpy.QtGui import (
    QColor,
    QFont,
    QPalette,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextListFormat,
)
from qtpy.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
)

from ..data_models import CommentCategory, ProjectData, User
from ..style import get_ayon_style
from ..variants import QFrameVariants, QTextEditVariants
from .buttons import AYButton
from .checkbox_handler import (
    CHECKBOX_CHECKED_PROP,
    CHECKBOX_FORMAT_TYPE,
    CHECKBOX_INDEX_PROP,
    CheckboxHandler,
)
from .combo_box import AYComboBox
from .comment_completion import (
    CODE_BG,
    CODE_FG,
    apply_code_block_backgrounds,
    format_comment_on_change,
    on_completer_activated,
    on_completer_key_press,
    on_completer_text_changed,
    on_users_updated,
    setup_user_completer,
)
from .container import AYContainer
from .layouts import AYHBoxLayout, AYVBoxLayout
from .text_edit import AYTextEdit

logger = logging.getLogger(__name__)

MD_DIALECT = QTextDocument.MarkdownFeature.MarkdownDialectGitHub


class AYTextEditor(AYTextEdit):
    Variants = QTextEditVariants

    submitted = Signal()  # Signal emitted when Ctrl+Enter is pressed
    checklist_changed = Signal()  # Signal emitted when checkbox state changes

    def __init__(
        self,
        *args,
        num_lines: int = 0,
        read_only: bool = False,
        user_list: list[User] | None,
        variant: Variants = Variants.Default,
        **kwargs,
    ):
        # remove our kwargs
        self.num_lines: int = num_lines
        self._read_only: bool = read_only
        self._user_list: list[User] = user_list or []
        self._variant_str: str = variant.value
        self._checkbox_handler: CheckboxHandler | None = None
        # Guard flag: when True, format_comment_on_change is a no-op.
        self._suppress_formatting: bool = False

        super().__init__(*args, variant=variant, **kwargs)
        self.setStyle(get_ayon_style())
        # Enable mouse tracking on viewport to receive mouseMoveEvent
        self.viewport().setMouseTracking(True)

        self.document().setIndentWidth(22)  # pixels per indent level

        if self.num_lines:
            doc = self.document()
            fm = self.fontMetrics()
            frame_w = self.frameWidth()
            cm = self.contentsMargins()
            height = (
                fm.lineSpacing() * self.num_lines
                + int(doc.documentMargin()) * 2
                + frame_w * 2
                + cm.top()
                + cm.bottom()
            )
            self.setFixedHeight(height)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
            if self.num_lines
            else QSizePolicy.Policy.Fixed,
        )

        # automatic bullet lists
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoAll)

        if not self._read_only:
            self.setPlaceholderText(
                "Comment or mention with @user, @@version, @@@task..."
            )
        self.setReadOnly(self._read_only)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("white"))
        self.setPalette(palette)
        # Setup user completer
        setup_user_completer(
            self,
            self._on_completer_activated,
            self._on_text_changed,
        )

        self.document().contentsChanged.connect(self._on_contents_changed)

    def _on_contents_changed(self) -> None:
        """Forward contentsChanged to format_comment_on_change.

        Skipped when ``_suppress_formatting`` is True so that checkbox
        insertion code can mutate the document without triggering a
        full re-format pass.
        """
        if not self._suppress_formatting:
            format_comment_on_change(self)
            apply_code_block_backgrounds(self)

    def _on_text_changed(self) -> None:
        """Handle text changes to show/hide completer."""
        on_completer_text_changed(self)

    def _on_completer_activated(self, text: str) -> None:
        """Handle completer selection."""
        on_completer_activated(self, text)

    def keyPressEvent(self, event) -> None:
        """Handle key press events for completer."""
        if on_completer_key_press(self, event):
            event.accept()
            return

        # ctrl/cmd-enter to submit
        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.submitted.emit()

        # Auto-continue checkbox on Enter
        if (
            event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}
            and self._checkbox_handler
            and self._checkbox_handler.has_checkboxes()
        ):
            cursor = self.textCursor()
            block_text = cursor.block().text()

            if "\ufffc" in block_text:
                # Extract text after the checkbox object char
                parts = block_text.split("\ufffc", 1)
                after_checkbox = parts[1].strip() if len(parts) > 1 else ""

                if not after_checkbox:
                    # Empty checkbox line → end the list
                    # Remove the checkbox content from current block
                    cursor.movePosition(
                        QTextCursor.MoveOperation.StartOfBlock,
                        QTextCursor.MoveMode.MoveAnchor,
                    )
                    cursor.movePosition(
                        QTextCursor.MoveOperation.EndOfBlock,
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.removeSelectedText()
                    # Remove the last checkbox from handler
                    self._checkbox_handler.remove_last_checkbox()
                    # Insert a plain newline
                    super().keyPressEvent(event)
                    return

                # Non-empty checkbox line → insert new checkbox
                event.accept()
                self._suppress_formatting = True

                cursor.beginEditBlock()
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.insertBlock()
                self._insert_checkbox_at_cursor(cursor)
                cursor.endEditBlock()

                self._suppress_formatting = False
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def _setup_checkbox_handler(self) -> None:
        """Initialize checkbox handler if not already done."""
        if self._checkbox_handler is None:
            self._checkbox_handler = CheckboxHandler(self)
            self._checkbox_handler.checklist_changed.connect(
                self._on_checklist_changed
            )

    def _on_checklist_changed(self) -> None:
        """Handle checkbox state changes."""
        self.checklist_changed.emit()

    def _insert_checkbox_at_cursor(self, cursor: QTextCursor) -> None:
        """Insert a new unchecked checkbox object at the cursor position.

        Inserts a two-space prefix, the custom checkbox object character
        (``\\ufffc``), and a trailing space, then records the document
        position on the :class:`CheckboxItem` for fast hit-testing.
        The checkbox handler must already be initialised via
        :meth:`_setup_checkbox_handler`.

        Args:
            cursor: Cursor at the insertion point; advanced past the
                inserted characters on return.
        """
        assert self._checkbox_handler is not None
        new_item = self._checkbox_handler.add_checkbox()
        fmt = QTextCharFormat()
        fmt.setObjectType(CHECKBOX_FORMAT_TYPE)
        fmt.setProperty(CHECKBOX_CHECKED_PROP, False)
        fmt.setProperty(CHECKBOX_INDEX_PROP, new_item.index)
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignBaseline
        )
        cursor.insertText("  ")
        new_item.doc_position = cursor.position()
        cursor.insertText("\ufffc", fmt)
        cursor.insertText(" ")

    def set_markdown(self, md: str) -> None:
        """Set markdown content with checkbox support.

        Args:
            md: Markdown text to display
        """
        if CheckboxHandler.contains_checkboxes(md):
            self._setup_checkbox_handler()
            assert self._checkbox_handler is not None
            self._checkbox_handler.parse_and_render(md)
        else:
            self.document().setMarkdown(md, MD_DIALECT)
        apply_code_block_backgrounds(self)

    def as_markdown(self) -> str:
        """Get the content as GitHub-flavored markdown.

        Returns:
            Markdown string.
        """
        if self._checkbox_handler and self._checkbox_handler.has_checkboxes():
            return self._checkbox_handler.to_markdown()
        return self.document().toMarkdown(MD_DIALECT)

    def _is_checkbox_at_cursor(
        self, click_pos: QPoint
    ) -> tuple[bool, int | None]:
        """Check if a click position hits a checkbox bounding rect.

        Delegates to :meth:`CheckboxHandler.find_checkbox_at_click` which
        uses stored document positions instead of scanning the full text.

        Args:
            click_pos: QPoint from event.pos(), viewport coords.

        Returns:
            Tuple of (is_checkbox, document_position_for_lookup).
        """
        if not self._checkbox_handler:
            return False, None

        # Account for scroll offset
        scroll_offset = QPoint(
            -self.horizontalScrollBar().value(),
            -self.verticalScrollBar().value(),
        )
        result = self._checkbox_handler.find_checkbox_at_click(
            click_pos, scroll_offset
        )
        if result is None:
            return False, None
        return result

    def mousePressEvent(self, event) -> None:
        """Handle mouse press events for checkboxes.

        Checkboxes can be toggled even in read-only mode.
        """
        is_cb, cb_pos = self._is_checkbox_at_cursor(event.pos())
        if is_cb and cb_pos is not None:
            assert self._checkbox_handler is not None  # implied by is_cb==True
            checkbox_idx = self._checkbox_handler.get_checkbox_at_position(
                cb_pos
            )
            if checkbox_idx is not None:
                self._checkbox_handler.toggle_checkbox(checkbox_idx)
                self.viewport().update()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Show arrow cursor over checkboxes, hand over links, I-beam else."""
        pos = event.pos()
        cursor = self.cursorForPosition(pos)
        fmt = cursor.charFormat()
        if fmt.objectType() == CHECKBOX_FORMAT_TYPE:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif fmt.isAnchor():
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        super().mouseMoveEvent(event)

    def set_style(self, style: str) -> None:
        """Apply a character style to the current selection or cursor.

        Styles are merged with the existing character formatting so that
        multiple styles (e.g. bold + italic) can be combined without
        removing previously applied styles.

        Args:
            style: Style identifier string (e.g. ``"stl_bold"``).
        """
        cursor = self.textCursor()

        # Suppress formatting during style application
        self._suppress_formatting = True

        cursor.beginEditBlock()

        if style == "stl_bold":
            # Toggle bold, preserving all other formatting
            current_weight = cursor.charFormat().fontWeight()
            new_weight = (
                QFont.Weight.Normal
                if current_weight == QFont.Weight.Bold
                else QFont.Weight.Bold
            )
            fmt = QTextCharFormat()
            fmt.setFontWeight(new_weight)

            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.mergeCurrentCharFormat(fmt)

            self.setTextCursor(cursor)

        elif style == "stl_italic":
            # Toggle italic, preserving all other formatting
            new_italic = not cursor.charFormat().fontItalic()
            fmt = QTextCharFormat()
            fmt.setFontItalic(new_italic)

            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.mergeCurrentCharFormat(fmt)

            self.setTextCursor(cursor)

        elif style == "stl_h1":
            # Toggle heading size, preserving all other formatting
            base_size = self.font().pointSizeF()
            current_size = cursor.charFormat().fontPointSize()

            fmt = QTextCharFormat()
            if current_size > base_size:  # Already a header
                fmt.setFontPointSize(base_size)
                fmt.setFontWeight(QFont.Weight.Normal)
            else:  # Make it a header
                fmt.setFontPointSize(base_size * 1.5)
                fmt.setFontWeight(QFont.Weight.Bold)

            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.mergeCurrentCharFormat(fmt)

            self.setTextCursor(cursor)

        elif style == "stl_link":
            pw = self.parentWidget()
            if not pw:
                return

            selected_text = (
                cursor.selectedText() if cursor.hasSelection() else ""
            )
            field = QtWidgets.QLineEdit(selected_text, parent=pw)

            def _make_link():
                link = field.text()
                fmt = QTextCharFormat()
                fmt.setAnchor(True)
                fmt.setAnchorHref(link)
                fmt.setFontUnderline(True)

                if cursor.hasSelection():
                    cursor.mergeCharFormat(fmt)
                else:
                    self.mergeCurrentCharFormat(fmt)

                field.close()
                field.deleteLater()
                self.setFocus()
                self.update()

            # open link edit field
            field.show()
            fr = field.rect()
            field.setGeometry(4, 0, self.rect().width(), fr.height())
            field.selectAll()
            field.setFocus()
            field.returnPressed.connect(_make_link)

        elif style == "stl_code":
            # Detect if already in code style
            is_code = cursor.charFormat().fontFixedPitch()
            fmt = QTextCharFormat()

            if is_code:
                # Toggle off: revert code-specific properties to widget
                # defaults
                fmt.setFontFixedPitch(False)
                fmt.setFontFamilies([self.font().family()])
                fmt.setBackground(
                    self.palette().color(QPalette.ColorRole.Base)
                )
                fmt.setForeground(
                    self.palette().color(QPalette.ColorRole.Text)
                )
            else:
                # Toggle on: apply code style
                fmt.setFontFixedPitch(True)
                fmt.setFontFamilies(
                    ["Courier New", "Menlo", "Monaco", "monospace"]
                )
                fmt.setBackground(CODE_BG)
                fmt.setForeground(CODE_FG)

            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.mergeCurrentCharFormat(fmt)

            self.setTextCursor(cursor)

        cursor.endEditBlock()
        self._suppress_formatting = False
        self.setFocus()

    def _insert_fmt_checklist(self) -> None:
        """Insert an unchecked checklist checkbox at the current cursor.

        If the cursor is on a bullet or numbered list line, the list
        item is converted into a checkbox line, preserving its text.
        Otherwise inserts on the current (empty) block, or on a new
        block inserted above when the current line is non-empty.
        """
        self._setup_checkbox_handler()
        assert self._checkbox_handler is not None

        self._suppress_formatting = True
        cursor = self.textCursor()
        cursor.beginEditBlock()

        block = cursor.block()
        text_list = block.textList()

        if text_list is not None:
            # Convert existing list item to checkbox.
            # Qt stores block text WITHOUT the list marker,
            # so block.text() gives us the clean content.
            line_text = block.text().strip()

            # Remove this block from the QTextList
            text_list.remove(block)

            # Reset the block indent that the QTextList left behind
            block_fmt = cursor.blockFormat()
            block_fmt.setIndent(0)
            cursor.setBlockFormat(block_fmt)

            # Select all content in the block and delete it
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor,
            )
            cursor.removeSelectedText()

            # Insert checkbox + original text
            self._insert_checkbox_at_cursor(cursor)
            cursor.insertText(line_text)
        else:
            # Original behavior for plain text
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            if cursor.block().text().strip():
                cursor.insertBlock()
                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)

            self._insert_checkbox_at_cursor(cursor)

        cursor.endEditBlock()
        self._suppress_formatting = False
        self.setTextCursor(cursor)
        self.setFocus()

    def set_format(self, format: str) -> None:
        """Set up the bullet/numbered/checklist formatting."""
        if format == "fmt_checklist":
            self._insert_fmt_checklist()
            return

        cursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)

        if format == "fmt_bullet":
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDisc)
            cursor.createList(list_fmt)
        elif format == "fmt_number":
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDecimal)
            cursor.createList(list_fmt)

        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.setFocus()

    def paintEvent(self, event) -> None:
        """Override paintEvent to make sure the placeholder text is not
        displayed when an empty list is added to an empty document."""
        if (
            self.placeholderText()
            and self.document().isEmpty()
            and self._has_list_block()
        ):
            self._suppress_formatting = True
            saved = self.placeholderText()
            super().setPlaceholderText("")
            super().paintEvent(event)
            super().setPlaceholderText(saved)
            self._suppress_formatting = False
            return
        super().paintEvent(event)

    def _has_list_block(self) -> bool:
        block = self.document().begin()
        while block.isValid():
            if block.textList() is not None:
                return True
            block = block.next()
        return False


NO_CATEGORY = {
    "text": "Category",
    "short_text": "Category",
    "icon": "close_small",
    "color": "#707070",
}


def _dict_from_comment_category(
    comment_categories: list[CommentCategory],
) -> list[dict]:
    if comment_categories:
        return [NO_CATEGORY] + [
            {
                "text": c.name,
                "short_text": c.name,
                "icon": "crop_square",
                "color": c.color,
            }
            for c in comment_categories
        ]
    return [NO_CATEGORY]


class AttachmentWidget(QtWidgets.QWidget):
    """Widget to display a single attachment thumbnail with remove button."""

    # Signal emits (index, type: 'screenshot' or 'file')
    remove_clicked = Signal(int, str)
    # Signal emits (index, type) when thumbnail clicked
    thumbnail_clicked = Signal(int, str)

    def __init__(
        self,
        parent=None,
        index=0,
        filename="",
        file_path="",
        attachment_type="file",
    ):
        super().__init__(parent)
        self.index = index
        self.filename = filename
        self.file_path = file_path
        self.attachment_type = attachment_type  # 'screenshot' or 'file'
        self.setup_ui()
        self.load_image()

    def setup_ui(self):
        # Use a container for the thumbnail with overlay button
        container = QtWidgets.QWidget(self)
        container.setFixedSize(80, 60)
        container.setCursor(Qt.CursorShape.PointingHandCursor)

        # Thumbnail
        self.thumbnail_label = QLabel(container)
        self.thumbnail_label.setFixedSize(80, 60)
        self.thumbnail_label.setScaledContents(True)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setStyleSheet(
            "QLabel { background-color: #2b2b2b; border: 1px solid #3d3d3d; }"
        )

        # Make thumbnail clickable
        self.thumbnail_label.mousePressEvent = (
            lambda e: self.thumbnail_clicked.emit(
                self.index, self.attachment_type
            )
        )

        # Remove button overlaid on top-right corner
        self.remove_btn = AYButton(
            "×", variant=AYButton.Variants.Nav, parent=container
        )
        self.remove_btn.setFixedSize(18, 18)
        self.remove_btn.move(62, 0)  # Position at top-right corner
        self.remove_btn.clicked.connect(
            lambda: self.remove_clicked.emit(self.index, self.attachment_type)
        )
        self.remove_btn.raise_()

        # Main layout
        layout = AYVBoxLayout(margin=4, spacing=2)
        layout.addWidget(container)

        # Filename label (truncated)
        self.filename_label = QLabel(self)
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.filename_label.setStyleSheet("font-size: 10px; color: #9aa4ad;")
        layout.addWidget(self.filename_label)

        self.setLayout(layout)
        self.update_display()

        # Set tooltip
        self.setToolTip(self.filename)

    def load_image(self):
        """Load thumbnail from file_path"""
        pixmap = QPixmap(self.file_path)
        if not pixmap.isNull():
            self.thumbnail_label.setPixmap(
                pixmap.scaled(
                    80,
                    60,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.thumbnail_label.setText("Image")

    def update_display(self):
        """Update the display with current filename and image"""
        # Update filename label
        display_name = (
            self.filename[:10] + "..."
            if len(self.filename) > 10
            else self.filename
        )
        self.filename_label.setText(display_name)
        self.load_image()

    def update_content(self, filename="", file_path=""):
        """Update the widget content"""
        if filename:
            self.filename = filename
            self.setToolTip(filename)
        if file_path:
            self.file_path = file_path
        self.update_display()


class AYTextBoxSignals(QObject):
    # Signal emitted when comment button is clicked, passes markdown content
    comment_submitted = Signal(str, str, list)  # type: ignore


class AYTextBox(AYContainer):
    signals = AYTextBoxSignals()
    Variants = QFrameVariants
    style_icons = {
        "stl_h1": "format_h1",
        "stl_bold": "format_bold",
        "stl_italic": "format_italic",
        "stl_link": "link",
        "stl_code": "code",
    }
    format_icons = {
        "fmt_number": "format_list_numbered",
        "fmt_bullet": "format_list_bulleted",
        "fmt_checklist": "checklist",
    }
    mention_map = {
        "person": "@",
        # TODO: Implement support for version and task mentions in completer
        #  before enabling these
        # "layers": "@@",
        # "check_circle": "@@@",
    }

    def __init__(
        self,
        *args,
        num_lines=0,
        show_categories=False,
        user_list: list[User] | None = None,
        variant: Variants = Variants.Default,
        **kwargs,
    ):
        self._variant_str: str = variant.value
        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=variant,
            margin=0,
            **kwargs,
        )

        self.show_categories = show_categories
        self.comment_categories: list[dict] = _dict_from_comment_category([])
        self.category = self.comment_categories[0]["text"]
        self._user_list: list[User] = user_list or []
        # Store attachments - unified list for both screenshots and files
        # List of dicts:
        #   {'type': 'screenshot'|'file', 'path': str, 'filename': str}
        self._attachments = []
        self.screenshot_handler = None  # Will be initialized in _build
        self._build(num_lines)

    def _build_upper_bar(self):
        grp_spacing = 16
        lyt = AYHBoxLayout(spacing=0, margin=0)
        # comment category if available
        if self.show_categories:
            self.com_cat = AYComboBox(
                parent=self, items=self.comment_categories
            )
            self.com_cat.currentTextChanged.connect(self._on_category_changed)
            lyt.addWidget(self.com_cat)
        lyt.addStretch()
        # styling buttons
        for var, icn in self.style_icons.items():
            setattr(
                self,
                var,
                AYButton(self, variant=AYButton.Variants.Nav, icon=icn),
            )
            lyt.addWidget(getattr(self, var))
        # formatting buttons
        for var, icn in self.format_icons.items():
            setattr(
                self,
                var,
                AYButton(self, variant=AYButton.Variants.Nav, icon=icn),
            )
            lyt.addWidget(getattr(self, var))
        lyt.addSpacing(grp_spacing)
        self.screenshot_btn = AYButton(
            self, variant=AYButton.Variants.Nav, icon="photo_camera"
        )
        lyt.addWidget(self.screenshot_btn)
        self.attach_file_btn = AYButton(
            self, variant=AYButton.Variants.Nav, icon="attach_file"
        )
        self.attach_file_btn.clicked.connect(self._on_attach_file_clicked)
        lyt.addWidget(self.attach_file_btn)
        return lyt

    def _build_attachment_area(self):
        """Build the unified scrollable attachment display area for both
        screenshots and files."""
        # Container for attachments
        self.attachment_container = QtWidgets.QWidget(self)
        self.attachment_layout = AYHBoxLayout(
            self.attachment_container, margin=4, spacing=4
        )

        # Scroll area
        self.attachment_scroll = QScrollArea(self)
        self.attachment_scroll.setWidget(self.attachment_container)
        self.attachment_scroll.setWidgetResizable(True)
        self.attachment_scroll.setFixedHeight(100)
        self.attachment_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.attachment_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.attachment_scroll.hide()  # Hidden by default

        return self.attachment_scroll

    def _build_edit_field(self, num_lines):
        self.edit_field = AYTextEditor(
            self,
            num_lines=num_lines,
            user_list=self._user_list,
            variant=AYTextEditor.Variants.Default,
        )
        for var in self.style_icons:
            getattr(self, var).clicked.connect(
                partial(self.edit_field.set_style, var)
            )
        for var in self.format_icons:
            getattr(self, var).clicked.connect(
                partial(self.edit_field.set_format, var)
            )

        self.edit_field.submitted.connect(self._on_comment_clicked)

        return self.edit_field

    def _build_lower_bar(self):
        lyt = AYHBoxLayout(margin=0, spacing=0)

        for icn, mention in self.mention_map.items():
            btn = AYButton(self, variant=AYButton.Variants.Nav, icon=icn)
            btn.clicked.connect(partial(self._add_mention_to_editor, mention))
            lyt.addWidget(btn)

        lyt.addSpacerItem(
            QtWidgets.QSpacerItem(0, 0, QSizePolicy.Policy.MinimumExpanding)
        )
        self.comment_button = AYButton(
            "Comment", variant=AYButton.Variants.Filled
        )
        self.comment_button.clicked.connect(self._on_comment_clicked)
        lyt.addWidget(self.comment_button)
        return lyt

    def _on_comment_clicked(self) -> None:
        """Handle comment button click and emit signal with markdown
        content."""
        markdown_content = self.edit_field.as_markdown()

        # Get all attachment paths
        all_attachment_paths = [att["path"] for att in self._attachments]

        self.signals.comment_submitted.emit(
            markdown_content, self.category, all_attachment_paths
        )
        self.edit_field.clear()
        if self.show_categories:
            self.com_cat.setCurrentIndex(0)
        self.clear_all_attachments()

        # Clear screenshots after submission
        if self.screenshot_handler:
            self.screenshot_handler.clear_screenshots()

    def _add_mention_to_editor(self, mention: str) -> None:
        """Add mention text to the editor at cursor position."""
        cursor = self.edit_field.textCursor()
        cursor.insertText(mention)
        self.edit_field.setTextCursor(cursor)
        self.edit_field.setFocus()

    def _on_category_changed(self, category: str) -> None:
        self.category = category if category != NO_CATEGORY["text"] else ""

    def _on_attach_file_clicked(self) -> None:
        """Handle attach file button click and open file dialog."""
        file_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self,
            "Select files to attach",
            "",
            "Image Files (*.png *.jpeg *.jpg);;All Files (*)",
        )

        if file_paths:
            for file_path in file_paths:
                self.add_attachment(file_path, "file")

    def _on_attachment_removed(self, index: int, attachment_type: str) -> None:
        """Handle removal of an attachment."""
        if 0 <= index < len(self._attachments):
            attachment = self._attachments[index]
            # Optionally delete temp files (screenshots)
            if attachment["type"] == "screenshot":
                file_path = attachment["path"]
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        logger.warning(
                            f"Failed to remove temp file {file_path}: {e}"
                        )

            self._attachments.pop(index)
            self._refresh_attachment_display()
            self._update_attachment_buttons()

    def _on_thumbnail_clicked(self, index: int, attachment_type: str) -> None:
        """Handle thumbnail click to open gallery."""
        if not self._attachments:
            return

        from .gallery_dialog import GalleryDialog

        # Prepare images list for GalleryDialog
        images = [(att["path"], att["filename"]) for att in self._attachments]

        dialog = GalleryDialog(images, current_index=index, parent=self)
        dialog.setWindowTitle("Attachments Preview")
        dialog.exec_()

    def _refresh_attachment_display(self) -> None:
        """Refresh the unified attachment display area."""
        # Clear existing widgets
        while self.attachment_layout.count():
            item = self.attachment_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        # Add attachment widgets
        if self._attachments:
            for idx, attachment in enumerate(self._attachments):
                widget = AttachmentWidget(
                    parent=self.attachment_container,
                    index=idx,
                    filename=attachment["filename"],
                    file_path=attachment["path"],
                    attachment_type=attachment["type"],
                )
                widget.remove_clicked.connect(self._on_attachment_removed)
                widget.thumbnail_clicked.connect(self._on_thumbnail_clicked)
                self.attachment_layout.addWidget(widget)

            self.attachment_layout.addStretch()
            self.attachment_scroll.show()
        else:
            self.attachment_scroll.hide()

        self.attachment_container.update()
        self.attachment_scroll.viewport().update()

    def add_attachment(
        self, file_path: str, attachment_type: str = "file"
    ) -> None:
        """Add a single attachment (screenshot or file).

        Args:
            file_path: Path to the file
            attachment_type: 'screenshot' or 'file'
        """
        if not file_path or file_path in [
            att["path"] for att in self._attachments
        ]:
            return

        filename = os.path.basename(file_path)
        if attachment_type == "screenshot":
            # Generate screenshot number
            screenshot_count = sum(
                1 for att in self._attachments if att["type"] == "screenshot"
            )
            filename = f"Screenshot {screenshot_count + 1}"

        self._attachments.append(
            {"type": attachment_type, "path": file_path, "filename": filename}
        )

        self._refresh_attachment_display()
        self._update_attachment_buttons()

    def _update_attachment_buttons(self) -> None:
        """Update button badges to show counts."""
        screenshot_count = sum(
            1 for att in self._attachments if att["type"] == "screenshot"
        )
        file_count = sum(
            1 for att in self._attachments if att["type"] == "file"
        )

        # Update screenshot button
        if screenshot_count > 0:
            self.screenshot_btn.setText(f"{screenshot_count}")
            self.screenshot_btn.setStyleSheet(
                "background-color: rgba(92, 173, 214, .4);"
            )
        else:
            self.screenshot_btn.setText("")
            self.screenshot_btn.setStyleSheet("")

        # Update attach file button
        if file_count > 0:
            self.attach_file_btn.setText(f"{file_count}")
            self.attach_file_btn.setStyleSheet(
                "background-color: rgba(92, 173, 214, .4);"
            )
        else:
            self.attach_file_btn.setText("")
            self.attach_file_btn.setStyleSheet("")

    def clear_all_attachments(self) -> None:
        """Clear all attachments."""
        self._attachments.clear()
        self._refresh_attachment_display()
        self._update_attachment_buttons()

    def get_attachments(self) -> list[dict]:
        """Get the current list of attachments.

        Returns:
            List of attachment dictionaries
        """
        return self._attachments.copy()

    @Slot(ProjectData)
    def on_ctlr_project_changed(self, data: ProjectData):
        self.comment_categories = _dict_from_comment_category(
            data.comment_category
        )
        if self.show_categories:
            self.com_cat.update_items(self.comment_categories)
        self.edit_field._user_list = self._user_list = data.users
        on_users_updated(self.edit_field)

    def _build(self, num_lines):
        self.add_layout(self._build_upper_bar())

        # Initialize screenshot handler after screenshot_btn is created
        from .screenshot_capture import ScreenshotHandler

        self.screenshot_handler = ScreenshotHandler(self, self.screenshot_btn)

        # Click to capture, but if screenshots exist, show gallery
        self.screenshot_btn.clicked.connect(self._on_screenshot_btn_clicked)

        self.add_widget(
            self._build_attachment_area()
        )  # Add unified attachment area
        self.add_widget(self._build_edit_field(num_lines), stretch=10)
        self.add_layout(self._build_lower_bar())

    def set_markdown(self, md: str):
        """Set markdown content with checkbox support.

        Args:
            md: Markdown text to display
        """
        self.edit_field.set_markdown(md)

    def _on_screenshot_btn_clicked(self):
        """Handle screenshot button click - always capture new screenshot."""
        self.screenshot_handler.launch_capture()


# TEST ------------------------------------------------------------------------


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def build():
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
        ww.add_annotation_attachments(
            [
                {
                    "file_path": "test1.png",
                    "filename": "test_annotation1.png",
                    "timestamp": 12345678,
                },
                {
                    "file_path": "test2.png",
                    "filename": "test_annotation2.png",
                    "timestamp": 12345679,
                },
            ]
        )

        return w

    test(build, style=Style.AyonStyle)
