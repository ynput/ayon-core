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
    QRect,
    Qt,
    Signal,
)
from qtpy.QtGui import (
    QColor,
    QEnterEvent,
    QPainter,
    QPaintEvent,
    QPixmap,
)
from qtpy.QtWidgets import QLabel, QLayout, QMessageBox, QTextEdit, QWidget

from ..data_models import (
    CommentModel,
    EntityMention,
    StatusChangeModel,
    StatusUiModel,
    User,
    VersionPublishModel,
)
from ..image_cache import ImageCache, make_activity_cache_key
from ..utils import color_blend
from .buttons import AYButton
from .comment_completion import is_mention_href
from .container import AYContainer, AYFrame
from .gallery_dialog import GalleryDialog
from .label import AYLabel, get_icon
from .layouts import AYHBoxLayout, AYVBoxLayout
from .markdown_edit import AYMarkdownEdit
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
            for kw in status_definitions or []
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


class AYCommentField(AYMarkdownEdit):
    """Text field for comment display with markdown and checkbox support.

    Supports GitHub-flavored markdown checkboxes (- [ ] and - [x]) that
    render with Material icons and can be toggled even in read-only mode.

    Signals:
        checklist_changed: Emitted when a checkbox state changes.
    """

    def __init__(
        self,
        *args,
        text: str = "",
        read_only: bool = False,
        num_lines: int = 0,
        user_list: list[User] | None = None,
        model: CommentModel | None = None,
        variant: AYMarkdownEdit.Variants = AYMarkdownEdit.Variants.Default,
        **kwargs,
    ) -> None:
        # remove our kwargs
        self._num_lines = num_lines
        self._read_only: bool = read_only
        self._data = model
        self._bg_color = None

        super().__init__(
            *args, user_list=user_list, variant=variant, **kwargs
        )
        self.setSizeAdjustPolicy(QTextEdit.SizeAdjustPolicy.AdjustToContents)
        self.set_markdown(text)

        # configure
        if self._read_only:
            # Auto-size to content for read-only fields
            self.document().contentsChanged.connect(
                self._adjust_height_to_content
            )
        elif num_lines:
            height = int(self.fontMetrics().lineSpacing()) * num_lines + 8 + 8
            self.setFixedHeight(height)

        if not self._read_only:
            self.setPlaceholderText(
                "Comment or mention with @user, @@version, @@@task..."
            )
        self.setReadOnly(self._read_only)

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
        - Web markdown syntax (text\n----, **bold**, _italic_, [link](url))
        - Standard QTextDocument markdown

        Args:
            md: Markdown text to display
        """
        super().set_markdown(md)
        self._adjust_height_to_content()

    def _on_checklist_changed(self) -> None:
        """Handle checkbox state changes."""
        super()._on_checklist_changed()
        self._adjust_height_to_content()

    def _adjust_height_to_content(self) -> None:
        """Adjust widget height to fit document content
        (read-only mode only)."""
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
        self._adjust_height_to_content()

    def mousePressEvent(self, event) -> None:
        """Handle mouse press events for checkboxes and links.

        Checkboxes can be toggled even in read-only mode.
        Links are opened only in read-only mode.
        """
        url = self.anchorAt(event.pos()) if self.isReadOnly() else ""
        if url and self._checkbox_index_at(event.pos()) is None:
            # Mentions link to an entity instead of a web page
            if not is_mention_href(url):
                webbrowser.open(url)
            event.accept()
            return

        super().mousePressEvent(event)


class AYImageAttachment(QLabel):
    """Widget to display an image attachment with thumbnail and full-size
    preview.

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
        """Draw a semi-transparent overlay with a fullscreen icon when
        hovered."""
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
        font.setPointSizeF(10)
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

        # Build gallery images list - use gallery_images if set, otherwise
        # just this image
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
    # The popup to mention a version or task opened
    mention_entities_requested = Signal()

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
        self.text_field.mention_entities_requested.connect(
            self.mention_entities_requested
        )

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

    def set_mention_entities(
        self,
        versions: list[EntityMention] | None = None,
        tasks: list[EntityMention] | None = None,
    ) -> None:
        """Set the versions (``@@``) and tasks (``@@@``) to mention.

        Either up front or in response to
        :attr:`mention_entities_requested`.
        """
        self.text_field.set_mention_entities(versions, tasks)

    def clear_mention_entities(self) -> None:
        """Forget the versions and tasks, they show as loading until set."""
        self.text_field.clear_mention_entities()

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
