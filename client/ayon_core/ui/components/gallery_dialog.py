"""Gallery dialog for navigating through activity thumbnails/images."""

from __future__ import annotations

import logging
from pathlib import Path

from qtpy.QtCore import (
    QEvent,
    Qt,
    Signal,  # type: ignore
)
from qtpy.QtGui import QPixmap, QShowEvent
from qtpy.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QWidget,
)

from ..style_types import get_ayon_style
from .buttons import AYButton
from .container import AYContainer
from .label import AYLabel
from .layouts import AYVBoxLayout

logger = logging.getLogger(__name__)


class GalleryDialog(QDialog):
    """Dialog for viewing and navigating through multiple images.

    This dialog provides a simple gallery view using standard Qt widgets,
    matching the official AYON style for image preview dialogs.

    Attributes:
        image_changed: Signal emitted when the current image changes.
            Emits the current index.

    Example:
        >>> images = [
        ...     ("/path/to/image1.png", "image1.png"),
        ...     ("/path/to/image2.png", "image2.png"),
        ... ]
        >>> dialog = GalleryDialog(images, current_index=0)
        >>> dialog.exec()
    """

    image_changed = Signal(int)

    def __init__(
        self,
        images: list[tuple[str, str]],
        current_index: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        """Initialize the gallery dialog.

        Args:
            images: List of tuples (image_path, filename) for each image.
            current_index: Index of the image to show initially.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.Tool)
        self.setStyle(get_ayon_style())
        self.images = images
        self.current_index = current_index
        # Track if dialog size has been set based on first image
        self._dialog_size_set = False

        self.setWindowTitle("Image Preview")

        # Set focus policy so dialog can receive keyboard events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Install event filter to intercept keyboard events from child widgets
        self.installEventFilter(self)

        self._setup_ui()
        self._show_current_image()

    def showEvent(self, event: QShowEvent) -> None:
        """Handle dialog show event to set focus properly.

        Args:
            event: Show event.
        """
        super().showEvent(event)
        # Activate window and set focus to the dialog so keyboard events work
        # immediately
        self.activateWindow()
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def eventFilter(self, obj, event: QEvent) -> bool:
        """Filter events to intercept keyboard navigation from any widget.

        This ensures arrow key navigation works even if a child widget
        somehow gains focus.

        Args:
            obj: Object that received the event.
            event: Event to filter.

        Returns:
            True if the event was handled, False otherwise.
        """
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Left:
                self._show_previous()
                return True
            elif key == Qt.Key.Key_Right:
                self._show_next()
                return True
            elif key == Qt.Key.Key_Escape:
                self.accept()
                return True
        return super().eventFilter(obj, event)

    def _setup_ui(self) -> None:
        """Set up the dialog UI components using standard Qt widgets."""
        dialog_lyt = AYVBoxLayout(self, margin=0, spacing=0)

        self.top_lyt = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=10,
        )
        # Prevent container from accepting focus
        self.top_lyt.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        dialog_lyt.addWidget(self.top_lyt)

        # Image display area
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setScaledContents(False)
        # Prevent label from accepting focus
        self.image_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.top_lyt.add_widget(self.image_label, stretch=1)

        # Only show navigation controls if multiple images
        if len(self.images) > 1:
            # Navigation controls
            nav_widget = AYContainer(
                layout=AYContainer.Layout.HBox,
                variant=AYContainer.Variants.High,
                layout_margin=0,
                layout_spacing=10,
            )
            # Prevent container from accepting focus
            nav_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            # Previous button
            self.prev_btn = AYButton(
                "◀ Previous", variant=AYButton.Variants.Nav
            )
            self.prev_btn.clicked.connect(self._show_previous)
            # Prevent button from stealing focus
            self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.prev_btn.installEventFilter(self)
            nav_widget.add_widget(self.prev_btn)

            # Info label (counter and filename)
            self.info_label = AYLabel(variant=AYLabel.Variants.Default)
            self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Prevent label from accepting focus
            self.info_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            nav_widget.add_widget(self.info_label, stretch=1)

            # Next button
            self.next_btn = AYButton("Next ▶", variant=AYButton.Variants.Nav)
            self.next_btn.clicked.connect(self._show_next)
            # Prevent button from stealing focus
            self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.next_btn.installEventFilter(self)
            nav_widget.add_widget(self.next_btn)

            self.top_lyt.add_widget(nav_widget)

    def _show_current_image(self) -> None:
        """Display the current image with proper scaling."""
        if not self.images or self.current_index >= len(self.images):
            return

        image_path, filename = self.images[self.current_index]

        # Load the full-size image
        if not Path(image_path).exists():
            self.image_label.setText("Image not found")
            return

        original_pixmap = QPixmap(image_path)
        if original_pixmap.isNull():
            self.image_label.setText("Failed to load image")
            return

        # Get screen dimensions for sizing
        screen = self.screen() or QApplication.primaryScreen()
        screen_size = screen.availableGeometry()
        max_w = int(screen_size.width() * 0.8)
        max_h = int(screen_size.height() * 0.8)

        # Scale if too large for screen while maintaining aspect ratio
        display_pixmap = original_pixmap
        if original_pixmap.width() > max_w or original_pixmap.height() > max_h:
            display_pixmap = original_pixmap.scaled(
                max_w,
                max_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self.image_label.setPixmap(display_pixmap)

        # Set dialog size once on first image, then keep it consistent
        if not self._dialog_size_set:
            _layout = self.top_lyt.layout()
            if _layout:
                self.resize(_layout.sizeHint())
                self._dialog_size_set = True
            else:
                logger.warning("Failed to get layout to size the dialog")

        # Update navigation controls if multiple images
        if len(self.images) > 1:
            # Update info label
            display_name = Path(filename).stem if filename else "Unknown"
            info_text = (
                f"{self.current_index + 1} / {len(self.images)} - "
                f"{display_name}"
            )
            self.info_label.setText(info_text)

            # Update button states
            self.prev_btn.setEnabled(self.current_index > 0)
            self.next_btn.setEnabled(self.current_index < len(self.images) - 1)

        # Emit signal
        self.image_changed.emit(self.current_index)

    def _show_previous(self) -> None:
        """Show the previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self._show_current_image()

    def _show_next(self) -> None:
        """Show the next image."""
        if self.current_index < len(self.images) - 1:
            self.current_index += 1
            self._show_current_image()


if __name__ == "__main__":
    from pathlib import Path

    from .. import _get_test_data_dir
    from ..tester import Style, test

    def build():
        rsrc_dir = (
            _get_test_data_dir() or Path(__file__).parent.parent / "resources"
        )
        images = []

        # Add any available test images
        for img_file in rsrc_dir.glob("*.jpg"):
            images.append((str(img_file), img_file.name))
        for img_file in rsrc_dir.glob("*.png"):
            images.append((str(img_file), img_file.name))

        if not images:
            # Create dummy entries for testing
            images = [
                ("test1.png", "Test Image 1"),
                ("test2.png", "Test Image 2"),
            ]

        dialog = GalleryDialog(images, current_index=0)
        return dialog

    test(build, style=Style.AyonStyleOverCSS)
