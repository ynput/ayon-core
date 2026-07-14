"""AYSpinBox component module."""

from __future__ import annotations

from qtpy.QtCore import QRectF, QSize, Qt
from qtpy.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPalette, QPen
from qtpy.QtWidgets import (
    QSpinBox,
    QStyleOptionSpinBox,
    QWidget,
)

from ..style_types import get_ayon_style
from ..variants import QSpinBoxVariants
from .style_mixin import StyleMixin

from qtmaterialsymbols import get_icon  # type: ignore


class AYSpinBox(StyleMixin, QSpinBox):
    """Custom styled spin box component.

    Inherits from QSpinBox and uses the AYON style system for rendering.
    Paints its own background, border, focus ring, and arrow buttons using
    ayon_style.json data.

    Args:
        parent: Parent widget.
        variant: Visual style variant.
        name_id: Object name for identification.
        minimum: Minimum value.
        maximum: Maximum value.
        value: Initial value.
    """

    Variants = QSpinBoxVariants

    def __init__(
        self,
        parent: QWidget | None = None,
        variant: QSpinBoxVariants = QSpinBoxVariants.Default,
        name_id: str = "",
        minimum: int = 0,
        maximum: int = 99,
        value: int = 0,
    ) -> None:
        super().__init__(parent)

        self._variant_str = variant.value
        self._pal: QPalette | None = None
        self._variant_styles = {}

        if name_id:
            self.setObjectName(name_id)

        # Set range and value
        self.setMinimum(minimum)
        self.setMaximum(maximum)
        self.setValue(value)

        # Suppress the native Qt frame
        self.setFrame(False)

        # Suppress macOS native focus ring (we draw our own)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)

        # Enable hover events
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._apply_style_palette()

        self.setStyle(get_ayon_style())

    @property
    def ayon_palette(self) -> QPalette:
        """Return the palette used for this widget."""
        if self._pal is None:
            self._apply_style_palette()
        return self._pal

    def variant_style(self, state=None) -> dict:
        """Return the style dict for the current variant."""
        key = (self._variant_str, state)
        if key not in self._variant_styles:
            model = get_ayon_style().model
            self._variant_styles[key] = model.get_style(
                "QSpinBox", variant=self._variant_str, state=state
            )
            self._variant_styles[key].set_context(self)
        return self._variant_styles[key]

    def _apply_style_palette(self) -> None:
        """Push text colors and padding from ayon_style.json."""
        style = self.variant_style()

        self._pal = self.palette()

        text_color = QColor(style.get("color", "#D3D8DE"))
        self._pal.setColor(QPalette.ColorRole.Text, text_color)
        self._pal.setColor(QPalette.ColorRole.BrightText, text_color)

        self._pal.setColor(
            QPalette.ColorRole.Highlight,
            QColor(style.get("selection-background-color", "#5CADDD")),
        )
        self._pal.setColor(
            QPalette.ColorRole.HighlightedText,
            QColor(style.get("selection-color", "#ffffff")),
        )

        # Transparent base so the background rect we draw is visible
        self._pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))

        self.setPalette(self._pal)

    def initStyleOption(self, option: QStyleOptionSpinBox) -> None:
        """Override the palette used by the style to paint the widget."""
        self.setPalette(self.ayon_palette)
        super().initStyleOption(option)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint background, border, focus ring, and arrow buttons.

        Draws the styled background rectangle, border, and custom arrow
        buttons using QPainter directly, then calls super().paintEvent()
        which renders the text, cursor, and selection on top.
        """

        is_disabled = not self.isEnabled()
        is_hover = self.underMouse()
        has_focus = self.hasFocus()

        if is_disabled:
            state = "disabled"
        elif is_hover and not has_focus:
            state = "hover"
        else:
            state = "base"

        style = self.variant_style(state)

        bg_color = QColor(style.get("background-color", "#21252B"))
        border_color = QColor(style.get("border-color", "#373D48"))
        border_width = style.get("border-width", 1)
        border_radius = style.get("border-radius", 3)
        opacity = style.get("opacity", 1.0)

        focus_outline_width = style.get("focus-outline-width", 2)
        focus_outline_color = QColor(
            style.get("focus-outline-color", "#5CADDD")
        )

        # Button styling
        button_bg_color = QColor(style.get("button-background-color", "transparent"))
        button_border_color = QColor(style.get("button-border-color", "#373D48"))
        button_hover_bg_color = QColor(style.get("button-hover-background-color", "#5c636f"))
        arrow_color = QColor(style.get("arrow-color", "#D3D8DE"))
        button_width = style.get("button-width", 16)
        padding = style.get("padding", [4, 4])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(opacity)
        painter.setFont(self.font())

        rect = QRectF(self.rect())
        half_bw = border_width / 2.0

        # Background
        bg_rect = rect.adjusted(half_bw, half_bw, -half_bw, -half_bw)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(bg_rect, border_radius, border_radius)

        # Border
        border_pen = QPen(border_color)
        border_pen.setWidthF(border_width)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bg_rect, border_radius, border_radius)

        # Focus ring
        if has_focus:
            half_fw = focus_outline_width / 2.0
            focus_rect = rect.adjusted(half_fw, half_fw, -half_fw, -half_fw)
            focus_pen = QPen(focus_outline_color)
            focus_pen.setWidthF(focus_outline_width)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(focus_rect, border_radius, border_radius)

        # Draw buttons and arrows
        self._draw_buttons(
            painter,
            rect,
            button_width,
            button_bg_color,
            button_border_color,
            button_hover_bg_color,
            arrow_color,
            border_width,
            is_disabled,
            is_hover,
        )

        # Draw the text value manually with proper positioning
        text_rect = QRectF(
            rect.left() + padding[0],
            rect.top(),
            rect.width() - button_width - padding[0] * 2,
            rect.height()
        )
        painter.setPen(QColor(style.get("color", "#D3D8DE")) if not is_disabled else QColor("#5b6779"))
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.text()
        )

        painter.end()

    def _draw_buttons(
        self,
        painter: QPainter,
        rect: QRectF,
        button_width: int,
        button_bg_color: QColor,
        button_border_color: QColor,
        button_hover_bg_color: QColor,
        arrow_color: QColor,
        border_width: float,
        is_disabled: bool,
        is_hover: bool,
    ) -> None:
        """Draw the up and down arrow buttons."""
        # Button container rect (right side of the widget)
        button_x = rect.right() - button_width
        
        # Up button rect (top half)
        up_rect = QRectF(
            button_x, rect.top(), button_width, rect.height() / 2
        )
        
        # Down button rect (bottom half)
        down_rect = QRectF(
            button_x, rect.top() + rect.height() / 2, button_width, rect.height() / 2
        )

        # Check which button is under mouse
        mouse_pos = self.mapFromGlobal(self.cursor().pos())
        up_hovered = up_rect.contains(mouse_pos) and is_hover and not is_disabled
        down_hovered = down_rect.contains(mouse_pos) and is_hover and not is_disabled

        # Draw vertical separator line
        painter.setPen(QPen(button_border_color, border_width))
        painter.drawLine(
            int(button_x), int(rect.top() + border_width),
            int(button_x), int(rect.bottom() - border_width)
        )

        # Draw horizontal separator between buttons
        painter.drawLine(
            int(button_x), int(up_rect.bottom()),
            int(rect.right()), int(up_rect.bottom())
        )

        # Draw button backgrounds on hover
        painter.setPen(Qt.PenStyle.NoPen)
        if up_hovered:
            painter.setBrush(QBrush(button_hover_bg_color))
            painter.drawRect(up_rect)
        
        if down_hovered:
            painter.setBrush(QBrush(button_hover_bg_color))
            painter.drawRect(down_rect)

        # Draw arrows using Material Symbols icons
        arrow_size = 12
        
        # Up arrow
        up_icon = get_icon("arrow_drop_up", color=arrow_color if not is_disabled else "#5b6779")
        up_pixmap = up_icon.pixmap(arrow_size, arrow_size)
        up_x = button_x + (button_width - arrow_size) / 2
        up_y = up_rect.top() + (up_rect.height() - arrow_size) / 2
        painter.drawPixmap(int(up_x), int(up_y), arrow_size, arrow_size, up_pixmap)

        # Down arrow
        down_icon = get_icon("arrow_drop_down", color=arrow_color if not is_disabled else "#5b6779")
        down_pixmap = down_icon.pixmap(arrow_size, arrow_size)
        down_x = button_x + (button_width - arrow_size) / 2
        down_y = down_rect.top() + (down_rect.height() - arrow_size) / 2
        painter.drawPixmap(int(down_x), int(down_y), arrow_size, arrow_size, down_pixmap)

    def sizeHint(self) -> QSize:
        """Override sizeHint to account for padding and buttons."""
        size = super().sizeHint()
        style = self.variant_style()
        padding = style.get("padding", [4, 4])
        button_width = style.get("button-width", 18)
        
        # Add horizontal padding and button width
        size.setWidth(size.width() + padding[0] * 2 + button_width)
        # Ensure minimum height with vertical padding
        size.setHeight(max(size.height() + padding[1] * 2, 28))
        return size


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer
    from .label import AYLabel
    from .layouts import AYVBoxLayout

    def _build() -> QWidget:
        container = AYContainer(
            variant=AYContainer.Variants.Low,
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=20,
        )
        container.setMinimumWidth(400)

        # Disabled spin box
        disabled_layout = AYVBoxLayout(spacing=4)
        disabled_layout.addWidget(AYLabel("Disabled:"))
        disabled_spin = AYSpinBox(minimum=1, maximum=100, value=50)
        disabled_spin.setEnabled(False)
        disabled_layout.addWidget(disabled_spin)
        container.add_layout(disabled_layout)

        # Default spin box
        default_layout = AYVBoxLayout(spacing=4)
        default_layout.addWidget(AYLabel("Default:"))
        default_spin = AYSpinBox(minimum=1, maximum=9999, value=1)
        default_layout.addWidget(default_spin)
        container.add_layout(default_layout)

        # Spin box with different range
        range_layout = AYVBoxLayout(spacing=4)
        range_layout.addWidget(AYLabel("Range 0-10:"))
        range_spin = AYSpinBox(minimum=0, maximum=10, value=5)
        range_layout.addWidget(range_spin)
        container.add_layout(range_layout)

        return container

    test(_build, style=Style.AyonStyle)
