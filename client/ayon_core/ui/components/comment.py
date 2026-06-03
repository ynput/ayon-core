from __future__ import annotations

import atexit
import logging
import tempfile
import webbrowser
from pathlib import Path
from shutil import rmtree

from qtpy.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRect,
    Qt,
    Signal,  # type: ignore
)
from qtpy.QtGui import (
    QColor,
    QEnterEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from qtpy.QtWidgets import QLabel, QLayout, QMessageBox, QTextEdit, QWidget

from ..data_models import (
    CommentModel,
    StatusChangeModel,
    StatusUiModel,
    User,
    VersionPublishModel,
)
from ..image_cache import ImageCache, make_activity_cache_key
from ..utils import color_blend
from ..variants import QTextEditVariants
from .buttons import AYButton
from .checkbox_handler import (
    CHECKBOX_CHECKED_PROP,
    CHECKBOX_FORMAT_TYPE,
    CHECKBOX_INDEX_PROP,
    CheckboxHandler,
)
from .combo_box import ALL_STATUSES
from .comment_completion import (
    apply_code_block_backgrounds,
    format_comment_on_change,
    on_completer_activated,
    on_completer_key_press,
    on_completer_text_changed,
    setup_user_completer,
)
from .container import AYContainer, AYFrame
from .gallery_dialog import GalleryDialog
from .label import AYLabel, get_icon
from .layouts import AYHBoxLayout, AYVBoxLayout
from .text_edit import AYTextEdit
from .user_image import AYUserImage

logger = logging.getLogger(__name__)

# STATUS ---------------------------------------------------------------------


class AYStatusChange(AYFrame):
    def __init__(
        self,
        *args,
        data: StatusChangeModel | None = None,
        status_definitions: dict | None = None,
        **kwargs,
    ):
        self._data = data or StatusChangeModel()
        self.statuses = {
            kw["text"]: StatusUiModel(**kw)
            for kw in status_definitions or ALL_STATUSES
        }
        super().__init__(
            *args, variant=AYFrame.Variants.Low, margin=0, **kwargs
        )
        self._build()

    @property
    def unknown_status(self):
        return StatusUiModel(
            "Unknown Status", "UKN", "shield_question", "#d05050"
        )

    def status_icon(self, status):
        model = self.statuses.get(status, self.unknown_status)
        return model.icon, model.color

    def _build_top_bar(self):
        small_icon_size = 14
        self.str_1 = AYLabel(
            f"{self._data.user_full_name} - {self._data.product} / "
            f"{self._data.version} - ",
            dim=True,
            rel_text_size=-2,
        )
        icon_name_0, icon_color_0 = self.status_icon(self._data.old_status)
        self.status_0 = AYLabel(
            self._data.old_status,
            icon=icon_name_0,
            icon_color=icon_color_0,
            icon_size=small_icon_size,
            icon_text_spacing=3,
            dim=True,
            rel_text_size=-2,
        )
        self.str_2 = AYLabel(" → ", dim=True, rel_text_size=-2)
        icon_name_1, icon_color_1 = self.status_icon(self._data.new_status)
        self.status_1 = AYLabel(
            self._data.new_status,
            icon=icon_name_1,
            icon_color=icon_color_1,
            icon_size=small_icon_size,
            icon_text_spacing=3,
            dim=True,
            rel_text_size=-2,
        )
        self.date = AYLabel(self._data.short_date, dim=True, rel_text_size=-2)
        cntr = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=0,
        )
        cntr.add_widget(self.str_1, stretch=0)
        cntr.add_widget(self.status_0, stretch=0)
        cntr.add_widget(self.str_2, stretch=0)
        cntr.add_widget(self.status_1, stretch=0)
        cntr.addStretch()
        cntr.add_widget(self.date, stretch=0)
        return cntr

    def _build(self):
        lyt = AYVBoxLayout(self, margin=0, spacing=0)
        lyt.addWidget(self._build_top_bar(), stretch=0)


# PUBLISH ---------------------------------------------------------------------


class AYPublish(AYFrame):
    def __init__(
        self, *args, data: VersionPublishModel | None = None, **kwargs
    ):
        self._data = data or VersionPublishModel()
        super().__init__(
            *args, variant=AYFrame.Variants.Low, margin=0, **kwargs
        )
        self._build()

    def _build_top_bar(self):
        self.user_icon = AYUserImage(
            parent=self,
            size=20,
            src=self._data.user_src,
            name=self._data.user_name,
            full_name=self._data.user_full_name,
            outline=False,
        )
        self.user_name = AYLabel(self._data.user_full_name, bold=True)
        self.date = AYLabel(self._data.short_date, dim=True, rel_text_size=-2)
        self.static = AYLabel(
            "published a version", dim=True, rel_text_size=-2
        )
        cntr = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=8,
        )
        cntr.setContentsMargins(0, 0, 0, 4)
        cntr.add_widget(self.user_icon, stretch=0)
        cntr.add_widget(self.user_name, stretch=0)
        cntr.add_widget(self.static, stretch=0)
        cntr.addStretch()
        cntr.add_widget(self.date, stretch=0)
        return cntr

    def _build(self):
        lyt = AYVBoxLayout(self, margin=0, spacing=0)
        lyt.addWidget(self._build_top_bar(), stretch=0)

        cntr = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
        )
        self.text_field = AYCommentField(
            text=f"**{self._data.product}**\n{self._data.version}",
            num_lines=3,
            read_only=True,
        )
        cntr.add_widget(self.text_field, stretch=0)

        lyt.addWidget(cntr, stretch=0)

    def update_params(self, model: CommentModel):
        if self._data:
            self.user_icon.update_params(
                self._data.user_src, self._data.user_full_name
            )
            self.user_name.setText(self._data.user_name)
            self.date.setText(self._data.short_date)


# COMMENT ---------------------------------------------------------------------

MD_DIALECT = QTextDocument.MarkdownFeature.MarkdownDialectGitHub


class AYCommentField(AYTextEdit):
    """Text field for comment display with markdown and checkbox support.

    Supports GitHub-flavored markdown checkboxes (- [ ] and - [x]) that
    render with Material icons and can be toggled even in read-only mode.

    Signals:
        checklist_changed: Emitted when a checkbox state changes.
    """

    Variants = QTextEditVariants
    checklist_changed = Signal()

    def __init__(
        self,
        *args,
        text: str = "",
        read_only: bool = False,
        num_lines: int = 0,
        user_list: list[User] | None = None,
        model: CommentModel | None = None,
        variant: Variants = Variants.Default,
        **kwargs,
    ) -> None:
        # remove our kwargs
        self._num_lines = num_lines
        self._read_only: bool = read_only
        self._user_list: list[User] = user_list or []
        self._data = model
        self._bg_color = None
        self._checkbox_handler: CheckboxHandler | None = None
        # Guard flag: when True, format_comment_on_change is a no-op.
        self._suppress_formatting: bool = False

        super().__init__(*args, variant=variant, **kwargs)
        self.setAutoFormatting(QTextEdit.AutoFormattingFlag.AutoAll)
        self.setSizeAdjustPolicy(QTextEdit.SizeAdjustPolicy.AdjustToContents)
        self.document().setIndentWidth(22)
        # Enable mouse tracking on viewport to receive mouseMoveEvent
        # self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.set_markdown(text)

        # configure
        if self._read_only:
            # Auto-size to content for read-only fields
            self.document().contentsChanged.connect(
                self._adjust_height_to_content
            )
            self._adjust_height_to_content()
        elif num_lines:
            height = int(self.fontMetrics().lineSpacing()) * num_lines + 8 + 8
            self.setFixedHeight(height)

        if not self._read_only:
            self.setPlaceholderText(
                "Comment or mention with @user, @@version, @@@task..."
            )
        self.setReadOnly(self._read_only)

        # Setup user completer
        setup_user_completer(
            self,
            self._on_completer_activated,
            self._on_text_changed,
        )

        # Connect text changed signal to format mentions
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

    def get_bg_color(self, base_color: str):
        if not self._bg_color:
            self._bg_color = base_color
            if self._data and self._data.category_color:
                self._bg_color = color_blend(
                    base_color, self._data.category_color, 0.1
                )
        return self._bg_color

    def set_markdown(self, md: str) -> None:
        """Set markdown content with checkbox and web markdown support.

        Supports:
        - GitHub-flavored markdown checkboxes (- [ ] and - [x])
        - Web markdown syntax (text\\n----, **bold**, _italic_, [link](url))
        - Standard QTextDocument markdown

        Args:
            md: Markdown text to display
        """
        # Check for checkboxes first
        if CheckboxHandler.contains_checkboxes(md):
            self._setup_checkbox_handler()
            # Handler is guaranteed to exist after _setup_checkbox_handler
            assert self._checkbox_handler is not None
            self._checkbox_handler.parse_and_render(md)
            if self._read_only:
                self._adjust_height_to_content()
            return

        self.document().setMarkdown(md, MD_DIALECT)
        apply_code_block_backgrounds(self)

        if self._read_only:
            self._adjust_height_to_content()

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
        if self._read_only:
            self._adjust_height_to_content()

    def as_markdown(self) -> str:
        """Get the content as GitHub-flavored markdown.

        If the field contains checkboxes, returns the markdown with
        checkbox syntax (- [ ] and - [x]) reflecting current state.

        Returns:
            Markdown string.
        """
        if self._checkbox_handler and self._checkbox_handler.has_checkboxes():
            return self._checkbox_handler.to_markdown()
        return self.document().toMarkdown(MD_DIALECT)

    def _on_text_changed(self) -> None:
        """Handle text changes to show/hide completer."""
        on_completer_text_changed(self)

    def _on_completer_activated(self, text: str) -> None:
        """Handle completer selection."""
        on_completer_activated(self, text)

    def _adjust_height_to_content(self) -> None:
        """Adjust widget height to fit document content (read-only mode only)."""
        if not self._read_only:
            return

        # Get document height
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        doc_height = doc.size().height()

        # Add frame margins (top + bottom)
        frame_width = self.frameWidth()
        margins = self.contentsMargins()
        total_height = (
            int(doc_height)
            + frame_width * 2
            + margins.top()
            + margins.bottom()
        )

        self.setFixedHeight(total_height)

    def resizeEvent(self, event) -> None:
        """Recalculate height when width changes (affects text wrapping)."""
        super().resizeEvent(event)
        if self._read_only:
            self._adjust_height_to_content()

    def contentOffset(self) -> QPointF:
        """Compute content offset (QPlainTextEdit compatibility).

        Returns the offset from viewport coordinates to document coordinates.
        This method provides compatibility with QPlainTextEdit for checkbox
        hit-testing in _is_checkbox_at_cursor.

        Returns:
            QPointF offset where viewport origin corresponds to document coords.
        """
        return QPointF(
            -self.horizontalScrollBar().value(),
            -self.verticalScrollBar().value(),
        )

    def _insert_checkbox_at_cursor(self, cursor: QTextCursor) -> None:
        """Insert a new unchecked checkbox object at the cursor position.

        Inserts the custom checkbox object character (``\\ufffc``), and a
        trailing space, then records the document position on the
        :class:`CheckboxItem` for fast hit-testing.
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
        new_item.doc_position = cursor.position()
        cursor.insertText("\ufffc", fmt)
        cursor.insertText(" ")

    def keyPressEvent(self, event) -> None:
        """Handle key press events for completer."""
        if on_completer_key_press(self, event):
            event.accept()
            return

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
                position_in_block = cursor.positionInBlock()
                token_pos_in_block = block_text.index("\ufffc")
                token_pos = (
                    cursor.position() - position_in_block + token_pos_in_block
                )
                cb_index = self._checkbox_handler.get_checkbox_at_position(
                    token_pos
                )

                if not after_checkbox:
                    self._suppress_formatting = True
                    try:
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
                        if cb_index is not None:
                            self._checkbox_handler.remove_checkbox(cb_index)
                    finally:
                        self._suppress_formatting = False
                    # Insert a plain newline
                    super().keyPressEvent(event)
                    return

                # Non-empty checkbox line → insert new checkbox
                event.accept()
                self._suppress_formatting = True

                try:
                    cursor.beginEditBlock()
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                    cursor.insertBlock()
                    self._insert_checkbox_at_cursor(cursor)
                    cursor.endEditBlock()
                except Exception as err:
                    logger.debug("Error inserting checkbox: %s", err)
                finally:
                    self._suppress_formatting = False
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)

    def _is_checkbox_at_cursor(
        self, click_pos: QPoint
    ) -> tuple[bool, int | None]:
        """Check if a click position hits a checkbox bounding rect.

        Delegates to `CheckboxHandler.find_checkbox_at_click` which
        uses stored document positions instead of scanning the full text.

        Args:
            click_pos: QPoint from event.pos(), viewport coords.

        Returns:
            Tuple of (is_checkbox, document_position_for_lookup).
        """
        if not self._checkbox_handler:
            return False, None

        result = self._checkbox_handler.find_checkbox_at_click(
            click_pos, self.contentOffset().toPoint()
        )
        if result is None:
            return False, None
        return result

    def mouseDoubleClickEvent(self, event) -> None:
        """Prevent text selection when double-clicking checkboxes."""
        is_cb, cb_pos = self._is_checkbox_at_cursor(event.pos())
        if is_cb and cb_pos is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press events for checkboxes and links.

        Checkboxes can be toggled even in read-only mode.
        Links are opened only in read-only mode.
        """
        # Get the character at the click position
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()

        # Check if clicked on a checkbox (works in both modes)
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

        # Handle link clicks only in read-only mode (display comments)
        if self.isReadOnly():
            # Check if the clicked text is a link (has anchor href)
            if char_format.isAnchor() and char_format.anchorHref():
                url = char_format.anchorHref()
                webbrowser.open(url)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        """Change cursor to arrow when hovering over checkboxes, hand for links."""
        cursor = self.cursorForPosition(event.pos())
        char_format = cursor.charFormat()

        # Show arrow cursor for checkboxes (in any mode)
        if char_format.objectType() == CHECKBOX_FORMAT_TYPE:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(event)
            return

        # Show hand cursor for links (only in read-only mode)
        if self.isReadOnly():
            if char_format.isAnchor() and char_format.anchorHref():
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

        super().mouseMoveEvent(event)


class AYImageAttachment(QLabel):
    """Widget to display an image attachment with thumbnail and full-size preview.

    Supports gallery mode when multiple images are associated together.
    When gallery_images is set, clicking the thumbnail opens a GalleryDialog
    that allows navigating through all images.

    Attributes:
        gallery_images: List of (image_path, filename) tuples for gallery mode.
        gallery_index: Current image index within the gallery.
    """

    no_img = None
    cacher_tmp_dir: Path | None = None

    def __init__(
        self,
        parent: QWidget | None = None,
        image_path: str | None = None,
        thumb_path: str | None = None,
        max_width: int = 100,
        max_height: int = 47,
        frame: int = 0,
        gallery_images: list | None = None,
        gallery_index: int = 0,
    ):
        super().__init__(parent)
        self._image_path = image_path
        self._thumb_path = thumb_path or image_path
        if (
            self._thumb_path is not None
            and not Path(self._thumb_path).exists()
        ):
            self._thumb_path = None
        self._max_width = max_width
        self._max_height = max_height
        self._frame = frame
        self._gallery_images = gallery_images or []
        self._gallery_index = gallery_index

        self.setScaledContents(False)
        self.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Set tooltip
        self.setToolTip("Click to view full size")

        self._hovered = False
        self._label_height = 16

        self.setFixedSize(
            self._max_width, self._max_height + self._label_height
        )

        # Load and display thumbnail
        self._load_thumbnail()
        self._draw_icon = get_icon("draw", color="#eeeeee")

    @property
    def image_path(self) -> str:
        """Get the path to the full-size image."""
        return self._image_path

    @property
    def frame(self) -> int:
        """Get the frame number associated with the image."""
        return self._frame

    def _load_thumbnail(self):
        """Load and display the thumbnail image."""
        if AYImageAttachment.no_img is None:
            AYImageAttachment.no_img = get_icon("panorama", color="#666666")

        if not self._thumb_path or not Path(self._thumb_path).exists():
            self.setPixmap(AYImageAttachment.no_img.pixmap(32, 32))
            return

        thumb_path = Path(self._thumb_path)
        cache_key = f"{thumb_path.name}_{self._max_width}_{self._max_height}"

        def _thumbnail_cacher() -> Path:
            """Cache the scaled-down thumbnail image."""
            pixmap = QPixmap(self._thumb_path or "")
            if pixmap.isNull():
                raise ValueError(
                    f"Cannot load image from path: {self._thumb_path!r}"
                )

            # Scale pixmap to fit within max dimensions while maintaining
            # aspect ratio.
            scaled_pixmap = pixmap.scaled(
                self._max_width,
                self._max_height,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            tmp_dir = AYImageAttachment.get_cacher_tmp_dir()
            tmp_file_path = tmp_dir / f"{cache_key}.thumb.png"
            scaled_pixmap.save(str(tmp_file_path), quality=75)
            return tmp_file_path

        ic = ImageCache.get_instance()
        pxm = QPixmap(ic.get(cache_key, _thumbnail_cacher))
        self.setPixmap(pxm)
        self.setFixedSize(pxm.width(), pxm.height() + self._label_height)

    def enterEvent(self, event):
        """Dim the image slightly when mouse enters."""
        self._hovered = True
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Restore full opacity when mouse leaves."""
        self._hovered = False
        super().leaveEvent(event)

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        """Draw a semi-transparent overlay with a fullscreen icon when hovered."""
        # draw image
        super().paintEvent(arg__1)
        # setup painter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        if self._hovered:
            img_rect = self.rect().adjusted(0, 0, 0, -self._label_height)
            painter.setBrush(QColor(0, 0, 0, 144))
            painter.drawRect(img_rect)
            icon = get_icon("open_in_full", color="#eeeeee")
            painter.drawPixmap(
                img_rect.center() - QPoint(12, 12), icon.pixmap(24, 24)
            )

        # draw label background
        lrect = QRect(
            0,
            self.height() - self._label_height,
            self.width(),
            self._label_height,
        )
        painter.setBrush(QColor("#1c2026"))
        painter.drawRect(lrect)
        # draw icon on the left side
        painter.drawPixmap(
            lrect.left() + 3, lrect.top() + 3, self._draw_icon.pixmap(10, 10)
        )
        # draw text on the right side
        painter.setPen(QColor("#eeeeee"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(
            lrect.adjusted(16 + 4, 0, 0, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            str(self._frame if self._frame > 0 else "n/a"),
        )

    def mousePressEvent(self, event):
        """Handle click to show full-size image."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._show_full_size()
        super().mousePressEvent(event)

    def _show_full_size(self):
        """Show full-size image in a dialog that respects aspect ratio.

        Uses GalleryDialog for consistent UI regardless of whether there's
        a single image or multiple images in the gallery.
        """

        # Collect gallery images if not already done
        if not self._gallery_images or any(
            t[0] == "" for t in self._gallery_images
        ):
            self._gallery_images = self._image_collector()

        # Build gallery images list - use gallery_images if set, otherwise just this image
        if self._gallery_images:
            images = self._gallery_images
            current_index = self._gallery_index
        else:
            # Single image case - still use gallery dialog for consistency
            if not self._image_path or not Path(self._image_path).exists():
                QMessageBox.warning(
                    self,
                    "Image Not Available",
                    "The full-size image is not available.",
                )
                return
            images = [(self._image_path, f"Frame {self._frame}")]
            current_index = 0

        dialog = GalleryDialog(
            images=images,
            current_index=current_index,
            parent=self,
        )
        dialog.exec()

    def set_gallery_images(self, images: list, current_index: int = 0) -> None:
        """Set the gallery images for navigation.

        Args:
            images: List of (image_path, filename) tuples.
            current_index: Index of this image in the gallery.
        """
        self._gallery_images = images
        self._gallery_index = current_index

    def _image_collector(self) -> list[tuple[str, str]]:
        """Collect all images in the parent layout."""
        try:
            parent_layout = self.parentWidget().layout()
        except AttributeError:
            logger.info(
                "Parent widget has no valid layout for image collector"
            )
            return []  # invalid parent widget

        assert isinstance(parent_layout, QLayout)
        image_list = []
        for i in range(parent_layout.count()):
            try:
                widget = parent_layout.itemAt(i).widget()
            except AttributeError:
                continue  # invalid layout item
            if isinstance(widget, AYImageAttachment):
                image_list.append((widget.image_path, f"Frame {widget.frame}"))

        return image_list

    @classmethod
    def get_cacher_tmp_dir(cls) -> Path:
        if cls.cacher_tmp_dir is None:
            cls.cacher_tmp_dir = Path(
                tempfile.mkdtemp(
                    prefix="ayon_review_desktop_thumbnail_cacher_"
                )
            )
        return cls.cacher_tmp_dir

    @staticmethod
    def cleanup_cacher_directory() -> None:
        if (
            AYImageAttachment.cacher_tmp_dir
            and AYImageAttachment.cacher_tmp_dir.exists()
        ):
            rmtree(AYImageAttachment.cacher_tmp_dir, ignore_errors=True)


class AYComment(AYContainer):
    """Enhanced comment widget that displays images from CommentModel.files."""

    comment_deleted = Signal(object)
    comment_edited = Signal(object)

    def __init__(
        self,
        *args,
        data: CommentModel | None = None,
        user_list: list[User] | None = None,
        **kwargs,
    ):
        self._data = data if data else CommentModel()
        self._user_list: list[User] = user_list or []
        self._bg_color = None
        self._image_widgets = {}
        self._attachments_built = False

        super().__init__(
            *args,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            bg_tint="",  # keep neutral
            margin=0,
            layout_spacing=0,
            layout_margin=1,
            **kwargs,
        )

        self._build()

        # configure
        if self._data:
            self.update_comment()

        self.text_field.checklist_changed.connect(self._on_checklist_changed)

    def update_comment(self, data: CommentModel | None = None):
        prev_data = self._data
        if data:
            self._data = data
        self.text_field.set_markdown(self._data.comment)
        self.date.setText(self._data.short_date)
        self.set_comment_category()
        if not self._attachments_built or prev_data.files != self._data.files:
            self.images_container.clear()
            self._build_image_attachments()

    def _build_top_bar(self):
        self.user_icon = AYUserImage(
            parent=self,
            size=20,
            src=self._data.user_src,
            name=self._data.user_name,
            full_name=self._data.user_full_name,
            outline=False,
        )
        self.user_name = AYLabel(self._data.user_full_name, bold=True)
        self.date = AYLabel(self._data.short_date, dim=True, rel_text_size=-2)
        cntr = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            margin=0,
            layout_spacing=8,
        )
        cntr.setContentsMargins(0, 0, 0, 4)
        cntr.add_widget(self.user_icon)
        cntr.add_widget(self.user_name)
        cntr.addStretch()
        cntr.add_widget(self.date)
        return cntr

    def _build_editor_toolbar(self):
        lyt = AYHBoxLayout()
        self.reaction = AYButton(
            variant=AYButton.Variants.Nav_Small,
            icon="add_reaction",
            icon_color="#888",
            tooltip="Not Implemented Yet !",
            parent=self,
        )
        self.cancel_edit = AYButton(
            "Cancel", variant=AYButton.Variants.Nav, parent=self
        )
        self.save_edit = AYButton(
            "Save", variant=AYButton.Variants.Filled, parent=self
        )
        lyt.addWidget(self.reaction)
        lyt.addStretch(10)
        lyt.addWidget(self.cancel_edit)
        lyt.addWidget(self.save_edit)

        self.cancel_edit.clicked.connect(self._cancel_edit)
        self.cancel_edit.setVisible(False)
        self.save_edit.clicked.connect(self._save_edit)
        self.save_edit.setVisible(False)
        return lyt

    def _build_edit_buttons(self):
        self.edit_frame = AYContainer(
            layout=AYContainer.Layout.HBox,
            bg_tint=self._data.category_color,
            parent=self.top_line,
        )
        bsize = 22
        self.del_button = AYButton(
            variant=AYButton.Variants.Nav_Small, icon="delete", parent=self
        )
        self.del_button.setFixedSize(bsize, bsize)
        self.edit_button = AYButton(
            variant=AYButton.Variants.Nav_Small,
            icon="edit_square",
            parent=self,
        )
        self.edit_button.setFixedSize(bsize, bsize)
        self.edit_frame.add_widget(self.del_button)
        self.edit_frame.add_widget(self.edit_button)
        self.top_line.addStretch(100)
        self.top_line.add_widget(self.edit_frame)
        self.edit_frame.setVisible(False)
        self.del_button.clicked.connect(self._confirm_delete)
        self.edit_button.clicked.connect(self._edit_comment)

    def _build(self):
        self.add_widget(self._build_top_bar())
        self.text_field = AYCommentField(
            self,
            text=self._data.comment,
            read_only=True,
            user_list=self._user_list,
            model=self._data,
            variant=AYCommentField.Variants.High,
        )

        self.editor_lyt = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            bg_tint=self._data.category_color,
            layout_margin=4,
        )
        self.top_line = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.High,
            bg_tint=self._data.category_color,
        )
        self.images_container = AYContainer(
            layout=AYContainer.Layout.Flow,
            variant=AYContainer.Variants.High,
            bg_tint=self._data.category_color,
            layout_spacing=4,
            layout_margin=0,
        )
        self.images_container.setContentsMargins(0, 0, 0, 0)
        self.top_line.setFixedHeight(20)

        # Create comment category once — hidden until a category is set
        self.comment_category = AYLabel(
            "",
            icon_color="",
            variant=AYLabel.Variants.Badge,
            rel_text_size=-2,
        )
        self.comment_category.setVisible(False)
        self.top_line.insert_widget(0, self.comment_category)

        self.editor_lyt.add_widget(self.top_line, stretch=0)
        self.editor_lyt.add_widget(self.images_container, stretch=0)
        self.editor_lyt.add_widget(self.text_field, stretch=10)

        self.editor_lyt.add_layout(self._build_editor_toolbar(), stretch=0)
        self.add_widget(self.editor_lyt)
        self._build_edit_buttons()

    def _build_image_attachments(self):
        """Build and display image attachments as separate clickable widgets.

        Supports gallery view: when multiple images are present, clicking
        any thumbnail opens a GalleryDialog for navigating through all images.
        """
        if (
            not self._data
            or not hasattr(self._data, "files")
            or not self._data.files
        ):
            return

        # First pass: collect all valid images for gallery view
        valid_files = []
        for file_model in self._data.files:
            # Check if this file is marked as transparent in annotations
            is_transparent = False
            if hasattr(self._data, "annotations"):
                for annotation in self._data.annotations:
                    if file_model.id == annotation.transparent:
                        is_transparent = True
                        break

            if is_transparent:
                continue
            # Check if file has local_path
            if not hasattr(file_model, "local_path"):
                continue

            # Guard against empty path: Path("") resolves to Path(".")
            # which always exists (current directory), leading to errors when
            # trying to cache it as an image.
            local_path = file_model.local_path
            if not local_path or not Path(local_path).exists():
                # Register as None so refresh_image can create the widget
                # once the background download completes.
                self._image_widgets.setdefault(file_model.id, None)

            valid_files.append(file_model)

        # Build gallery images list for navigation
        gallery_images = [
            (
                f.local_path,
                f"Frame {f.start_frame + f.frame - 1 if f.frame > 0 else -1}",
            )
            for f in valid_files
        ]

        # Second pass: create widgets with gallery support
        for idx, file_model in enumerate(valid_files):
            max_image_width = 100
            max_image_height = 47

            # coerce any invalid thumb path to None.
            thumb_path = getattr(file_model, "thumb_local_path", None) or None

            # frame sequences start at 1, so we need to subtract 1 to get the
            # actual frame number.
            # if frame is 0 or negative, we treat it as n/a. This happens when
            # attaching a screenshot or external file.
            frame = (
                file_model.start_frame + file_model.frame - 1
                if file_model.frame > 0
                else -1
            )

            # Create image widget with gallery support
            image_widget = AYImageAttachment(
                parent=self,
                image_path=local_path,
                thumb_path=thumb_path,
                max_width=max_image_width,
                max_height=max_image_height,
                frame=frame,
                gallery_images=gallery_images,
                gallery_index=idx,
            )

            self.images_container.add_widget(image_widget)
            self._image_widgets[file_model.id] = image_widget

        # mark as built to avoid rebuilding on every update
        self._attachments_built = True

    def _edit_comment(self):
        """Make the field editable, hide the edit/del buttons and show
        Save/Cancel."""
        self._show_edit_buttons(False)
        self.text_field.setReadOnly(False)
        self.cancel_edit.setVisible(True)
        self.save_edit.setVisible(True)

    def _cancel_edit(self):
        """Make the field read-only and restore text."""
        self.text_field.setReadOnly(True)
        self.cancel_edit.setVisible(False)
        self.save_edit.setVisible(False)
        self.text_field.set_markdown(self._data.comment)
        self._show_edit_buttons(True)

    def _save_edit(self):
        self.text_field.setReadOnly(True)
        self.cancel_edit.setVisible(False)
        self.save_edit.setVisible(False)
        self._show_edit_buttons(True)
        self._data.comment = self.text_field.as_markdown()
        self.comment_edited.emit(self._data)

    def _confirm_delete(self):
        mb = QMessageBox(
            text="Are you sure you want to delete this comment?",
            standardButtons=QMessageBox.StandardButton.Cancel
            | QMessageBox.StandardButton.Yes,  # type: ignore
            parent=self,
        )
        if mb.exec() == QMessageBox.StandardButton.Yes:
            self.comment_deleted.emit(self._data)

    def _show_edit_buttons(self, state):
        """show / hide edit buttons and position them."""
        if not self.text_field.isReadOnly():
            return
        self.edit_frame.setVisible(state)
        if state:
            fr = self.edit_frame.rect()
            vr = self.text_field.visibleRegion().boundingRect()
            self.edit_frame.move((vr.width() + vr.x()) - fr.width(), 0)

    def set_comment_category(self):
        """Update the comment category and comment background tint"""
        self._update_category_bg_tint()

        if not self._data.category:
            self.comment_category.setVisible(False)
            return

        # Update comment category
        self.comment_category.setText(self._data.category)
        self.comment_category.set_icon_color(self._data.category_color)
        self.comment_category.setVisible(True)

    def _update_category_bg_tint(self):
        """Update bg_tint on containers that use category_color."""
        tint = self._data.category_color or ""
        for widget in (
            self.editor_lyt,
            self.top_line,
            self.images_container,
            self.edit_frame,
        ):
            widget._bg_tint = tint
            widget._bg_color = None  # reset cache so it recalculates
            widget.update()  # trigger repaint

    def enterEvent(self, event: QEnterEvent) -> None:
        self._show_edit_buttons(True)
        return super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:
        self._show_edit_buttons(False)
        return super().leaveEvent(event)

    def update_params(self, model: CommentModel):
        if self._data:
            self.user_icon.update_params(
                self._data.user_src, self._data.user_full_name
            )
            self.user_name.setText(self._data.user_name)
            self.date.setText(self._data.short_date)

    def refresh_image(
        self,
        file_id: str,
        filepath: str | None,
        project_name: str,
    ) -> None:
        """Refresh image attachment widget once a file download completes.

        Called by the activity stream when a background download finishes.
        If the widget hasn't been created yet (path was unavailable at build
        time), creates and adds it now.

        Args:
            file_id: The AYON file identifier.
            filepath: Unused - paths are resolved from ImageCache.
            project_name: AYON project name that owns the file, used to
                build the cache key via
                :func:`ayon_core.ui.image_cache.make_activity_cache_key`.
        """
        ic = ImageCache.get_instance()
        image_attachment = self._image_widgets.get(file_id)

        if image_attachment is None and file_id in self._image_widgets:
            # Widget placeholder registered but not yet created - build it
            # now that the download has completed.
            image_path = (
                ic.get_path(
                    make_activity_cache_key(project_name, file_id),
                )
                or ""
            )
            thumb_path = ic.get_path(
                make_activity_cache_key(
                    project_name, file_id, is_thumbnail=True
                )
            )
            if not image_path:
                return  # Full-size not ready yet; thumbnail alone is enough
            image_attachment = AYImageAttachment(
                parent=self,
                image_path=image_path,
                thumb_path=thumb_path,
                max_width=100,
                max_height=47,
            )
            self.images_container.add_widget(image_attachment)
            self._image_widgets[file_id] = image_attachment
            return

        if isinstance(image_attachment, AYImageAttachment):
            if not image_attachment._thumb_path:
                image_attachment._thumb_path = (
                    ic.get_path(
                        make_activity_cache_key(
                            project_name, file_id, is_thumbnail=True
                        )
                    )
                    or ""
                )
            if not image_attachment._image_path:
                image_attachment._image_path = (
                    ic.get_path(
                        make_activity_cache_key(project_name, file_id),
                    )
                    or ""
                )
            if image_attachment._thumb_path or image_attachment._image_path:
                image_attachment._load_thumbnail()

    def _on_checklist_changed(self):
        md = self.text_field.as_markdown()
        self._data.comment = md
        self.comment_edited.emit(self._data)


atexit.register(AYImageAttachment.cleanup_cacher_directory)


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer
    from .text_box import AYTextBox

    def build():
        rsrc_dir = Path(__file__).parent.parent / "resources"
        av1 = rsrc_dir / "avatar1.jpg"
        av2 = rsrc_dir / "avatar2.jpg"

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
                        "regular, **bold**, *italic*, ***bold italic*** and `some code` text.\n\n"
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
                        "[this link](https://doc.qt.io/qt-6/qtextdocument.html)\n\n"
                        "or [that one](https://doc.qt.io/qt-6/qtextblock.html#details) if need be. "
                        "maybe [a last URL](https://doc.qt.io/qt-6/qtextblock.html#details) ?"
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
                f"Comment submitted: {'=' * (80 - len('Comment submitted: '))}\n",
                f"{args[0]}",
                f"{'-' * 80}\n",
                f"   markdown: {args[0]!r}\n",
                f"   category: {args[1]!r}\n",
                f"attachments: {args[2]}\n",
                f"{'-' * 80}\n",
            )
        )

        return w

    test(build, style=Style.AyonStyleOverCSS)
