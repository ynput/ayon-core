"""Visual regression tests for AYTextBox."""

from __future__ import annotations

from qtpy import QtCore, QtGui
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QPainter
from qtpy.QtWidgets import QWidget

from widget_test import WidgetTest
from ayon_core.ui.components.text_box import (
    AYTextBox,
    AYTextEditor,
)
from ayon_core.ui.components.container import AYContainer
from ayon_core.ui.components.label import AYLabel


class _CompositeTextBoxWidget(QWidget):
    """A QWidget whose grab() composites the main widget and its dropdown.

    When the category combo box dropdown is visible, the pixmap is
    assembled by stacking the main widget and the dropdown, similar to
    the approach used in test_buttons.py for AYButtonMenu.
    """

    def __init__(
        self,
        text_box: AYTextBox,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text_box = text_box
        self._combo = getattr(text_box, "com_cat", None)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        p = QPainter(self)
        p.fillRect(event.rect(), QColor("#272d35"))
        return super().paintEvent(event)

    def grab(  # type: ignore[override]
        self,
        rectangle: QtCore.QRect = QtCore.QRect(
            QtCore.QPoint(0, 0), QtCore.QSize(-1, -1)
        ),
    ) -> QtGui.QPixmap:
        """Return a pixmap composited with the open dropdown if visible."""
        base_pixmap = super().grab(rectangle)

        # Check if the category combo dropdown is visible
        dropdown = None
        if self._combo is not None:
            view = self._combo.view()
            if view is not None and view.isVisible():
                dropdown = view

        if dropdown is None:
            return base_pixmap

        drop_pixmap = dropdown.grab()

        # Compute dropdown position relative to this widget
        drop_global = dropdown.mapToGlobal(QtCore.QPoint(0, 0))
        drop_local = self.mapFromGlobal(drop_global)

        total_height = max(
            base_pixmap.height(),
            drop_local.y() + drop_pixmap.height(),
        )
        total_width = max(
            base_pixmap.width(),
            drop_local.x() + drop_pixmap.width(),
        )
        canvas = QtGui.QPixmap(total_width, total_height)
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QtGui.QPainter(canvas)
        painter.drawPixmap(0, 0, base_pixmap)
        painter.drawPixmap(drop_local.x(), drop_local.y(), drop_pixmap)
        painter.end()

        return canvas


class TextBoxTest(WidgetTest):
    """Tests AYTextBox with and without categories, including dropdown
    capture."""

    size = (700, 350)
    # TODO resolve the difference
    tolerance = 0.02

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
            layout_spacing=12,
        )

        # TextBox with categories enabled
        root.add_widget(AYLabel("With categories:"))
        self._text_box_with_cat = AYTextBox(
            num_lines=4,
            show_categories=True,
            variant=AYTextBox.Variants.Default,
        )

        # Wrap in composite widget for dropdown capture
        self._composite_cat = _CompositeTextBoxWidget(self._text_box_with_cat)
        from qtpy.QtWidgets import QVBoxLayout

        cat_lyt = QVBoxLayout(self._composite_cat)
        cat_lyt.setContentsMargins(0, 0, 0, 0)
        cat_lyt.setSpacing(0)
        cat_lyt.addWidget(self._text_box_with_cat)
        root.add_widget(self._composite_cat, stretch=1)

        # TextBox without categories
        root.add_widget(AYLabel("Without categories:"))
        self._text_box_no_cat = AYTextBox(
            num_lines=4,
            show_categories=False,
            variant=AYTextBox.Variants.Default,
        )
        root.add_widget(self._text_box_no_cat, stretch=1)

        return root

    def open_category_dropdown(self) -> None:
        """Open the category combo box dropdown."""
        if self._text_box_with_cat.show_categories:
            combo = getattr(self._text_box_with_cat, "com_cat", None)
            if combo is not None:
                combo.showPopup()

    def set_markdown(self) -> None:
        """Set markdown content in both text boxes."""
        self._text_box_with_cat.set_markdown(
            "## Title\nSome **bold** and *italic* text.\n"
            "- [ ] Task one\n- [x] Task two\n"
        )
        self._text_box_no_cat.set_markdown(
            "Plain comment with `inline code`.\n"
        )

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.open_category_dropdown, self.set_markdown]


class TextEditorTest(WidgetTest):
    """Tests AYTextEditor standalone with various states."""

    size = (500, 250)
    tolerance = 0.0

    def build(self) -> QWidget:
        root = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=16,
            layout_spacing=12,
        )

        # Default editor
        row1 = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
            layout_spacing=4,
        )
        row1.add_widget(AYLabel("Default editor:"))
        self._editor_default = AYTextEditor(
            num_lines=4,
            user_list=[],
            variant=AYTextEditor.Variants.Default,
        )
        row1.add_widget(self._editor_default, stretch=1)
        root.add_widget(row1, stretch=1)

        # Read-only editor with markdown
        row2 = AYContainer(
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
            layout_spacing=4,
        )
        row2.add_widget(AYLabel("Read-only editor:"))
        self._editor_readonly = AYTextEditor(
            num_lines=4,
            read_only=True,
            user_list=[],
            variant=AYTextEditor.Variants.Default,
        )
        self._editor_readonly.set_markdown(
            "**Bold text** and *italic text*.\n`"
            "``python\nprint('hello')\n```\n"
        )
        row2.add_widget(self._editor_readonly, stretch=1)
        root.add_widget(row2, stretch=1)

        return root

    def set_text(self) -> None:
        """Set text in the default editor."""
        self._editor_default.set_markdown(
            "- [ ] Checklist item one\n"
            "- [ ] Checklist item two\n"
            "- [x] Completed item\n"
        )

    def set_bold(self) -> None:
        """Apply bold style to default editor."""
        self._editor_default.set_style("stl_bold")

    def set_code(self) -> None:
        """Apply code style to default editor."""
        self._editor_default.set_style("stl_code")

    def wait_loaded(self, qtbot) -> None:
        """Flush pending paint events."""
        from qtpy.QtWidgets import QApplication

        QApplication.processEvents()

    def steps(self):
        return [self.set_text, self.set_bold, self.set_code]
