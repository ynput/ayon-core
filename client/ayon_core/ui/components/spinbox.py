"""AYSpinBox component module."""

from __future__ import annotations

from qtpy.QtCore import QRect, QRectF, QSize, Qt
from qtpy.QtGui import (
    QBrush, QColor, QPainter, QPaintEvent, QPalette, QPen, QIcon
)
from qtpy.QtWidgets import (
    QAbstractSpinBox,
    QSpinBox,
    QStyleOptionSpinBox,
    QWidget,
    QStyle,
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
        opt = QStyleOptionSpinBox()
        self.initStyleOption(opt)

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
        # NOTE A lot of styling of this component is wrong. The spinbox input
        #   should be drawn using internal QLineEdit, which has its own
        #   styling.
        #   The button does not respect "real" button dimensions. The
        #   arrows are defined by internal logic of QSpinBox and style, we
        #   can't just define where it is drawn we also have to handle mouse
        #   hit collisions. That can be affected only by QStyle.

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
        arrow_color = QColor(style.get("arrow-color", "#D3D8DE"))
        # button_width = style.get("button-width", 16)
        # padding = style.get("padding", [4, 4])

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(opacity)
        painter.setFont(self.font())

        rect = QRectF(self.rect())

        if has_focus:
            half_bw = focus_outline_width * 0.5
            border_color = focus_outline_color
        else:
            half_bw = border_width * 0.5
            border_color = border_color

        # Background
        bg_rect = rect.adjusted(half_bw, half_bw, -half_bw, -half_bw)
        border_pen = QPen(border_color)
        border_pen.setWidthF(border_width)
        painter.setPen(border_pen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(bg_rect, border_radius, border_radius)

        # Draw buttons and arrows
        self._draw_buttons(
            painter,
            rect,
            opt,
            border_color,
            arrow_color,
            border_width,
            is_disabled,
        )

        painter.end()

    def _draw_buttons(
        self,
        painter: QPainter,
        rect: QRectF,
        opt: QStyleOptionSpinBox,
        border_color: QColor,
        arrow_color: QColor,
        border_width: float,
        is_disabled: bool,
    ) -> None:
        """Draw the up and down arrow buttons."""
        if opt.buttonSymbols == QAbstractSpinBox.NoButtons:
            return

        # Button container rect (right side of the widget)
        style = self.style()
        up_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxUp,
            self
        )
        down_rect = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox,
            opt,
            QStyle.SubControl.SC_SpinBoxDown,
            self
        )
        button_x = int(rect.right() - up_rect.width())

        # Draw vertical separator line
        painter.setPen(QPen(border_color, border_width))
        painter.drawLine(
            button_x, int(rect.top() + border_width) + 1,
            button_x, int(rect.bottom() - border_width) - 1
        )

        # Draw horizontal separator between buttons
        mid = int(rect.height() * 0.5)
        painter.drawLine(
            button_x, mid, int(rect.right()) - 1, mid
        )

        # Draw arrows using Material Symbols icons
        arrow_size = min(12, up_rect.height(), down_rect.height())

        up_icon_rect = QRect(0, 0, arrow_size, arrow_size)
        down_icon_rect = QRect(0, 0, arrow_size, arrow_size)

        up_icon_rect.moveCenter(up_rect.center())
        down_icon_rect.moveCenter(down_rect.center())

        if (
            opt.subControls & QStyle.SubControl.SC_SpinBoxUp
            and opt.activeSubControls == QStyle.SubControl.SC_SpinBoxUp
        ):
            up_icon_rect.moveTop(up_icon_rect.top() - 1)

        if (
            opt.subControls & QStyle.SubControl.SC_SpinBoxDown
            and opt.activeSubControls == QStyle.SubControl.SC_SpinBoxDown
        ):
            down_icon_rect.moveTop(down_icon_rect.top() + 1)

        # Up arrow
        up_icon: QIcon = get_icon(
            "arrow_drop_up",
            color=arrow_color if not is_disabled else "#5b6779"
        )
        up_icon.paint(painter, up_icon_rect)

        # Down arrow
        down_icon: QIcon = get_icon(
            "arrow_drop_down",
            color=arrow_color if not is_disabled else "#5b6779"
        )
        down_icon.paint(painter, down_icon_rect)

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
