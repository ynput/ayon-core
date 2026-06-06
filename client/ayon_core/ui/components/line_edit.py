"""AYLineEdit component module."""

from __future__ import annotations

from qtpy.QtCore import QRectF, QSize, Qt
from qtpy.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPalette, QPen
from qtpy.QtWidgets import (
    QLineEdit,
    QStyleOptionFrame,
    QWidget,
)

from ..style import get_ayon_style
from ..variants import QLineEditVariants
from .style_mixin import StyleMixin

from qtmaterialsymbols import get_icon  # type: ignore


class AYLineEdit(StyleMixin, QLineEdit):
    """Custom styled line edit component.

    Inherits from QLineEdit and uses the AYON style system for rendering.
    Paints its own background, border, and focus ring using ayon_style.json
    data, then calls super().paintEvent() to draw text, cursor, and
    selection on top.

    Args:
        parent: Parent widget.
        placeholder: Placeholder text to display when empty.
        variant: Visual style variant.
        name_id: Object name for identification.
    """

    Variants = QLineEditVariants

    def __init__(
        self,
        parent: QWidget | None = None,
        placeholder: str = "",
        variant: QLineEditVariants = QLineEditVariants.Default,
        name_id: str = "",
    ) -> None:
        super().__init__(parent)

        self._variant_str = variant.value
        self._pal: QPalette | None = None
        self._variant_styles = {}

        if placeholder:
            self.setPlaceholderText(placeholder)

        if name_id:
            self.setObjectName(name_id)

        # Suppress the native Qt frame so initStyleOption reports lineWidth=0
        self.setFrame(False)

        # Neutralise any ancestor stylesheet that would intercept
        # PE_PanelLineEdit via QStyleSheetStyle, making it visually transparent.
        self.setStyleSheet(
            "AYLineEdit { background: transparent; border: none; "
            "padding: 0px; selection-background-color: none; "
            "selection-color: none; }"
        )

        # Suppress macOS native focus ring (we draw our own)
        self.setAttribute(Qt.WidgetAttribute.WA_MacShowFocusRect, False)

        # Enable hover events so underMouse() is reliable during paintEvent
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

        self._apply_style_palette()

        #  this must be called after the palette has been set for it to stick.
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
                "QLineEdit", variant=self._variant_str, state=state
            )
            self._variant_styles[key].set_context(self)
        return self._variant_styles[key]

    def _apply_style_palette(self) -> None:
        """Push text / placeholder colors and padding from ayon_style.json."""
        style = self.variant_style()

        self._pal = self.palette()

        text_color = QColor(style.get("color", "#ffffff"))
        self._pal.setColor(QPalette.ColorRole.Text, text_color)
        self._pal.setColor(QPalette.ColorRole.BrightText, text_color)

        ph_color = QColor(style.get("placeholder-color", "#888888"))
        self._pal.setColor(QPalette.ColorRole.PlaceholderText, ph_color)

        self._pal.setColor(
            QPalette.ColorRole.Highlight,
            QColor(style.get("selection-background-color", "#4040dd")),
        )
        self._pal.setColor(
            QPalette.ColorRole.HighlightedText,
            QColor(style.get("selection-color", "#ffffff")),
        )

        # Transparent base so the background rect we draw is visible
        self._pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))

        self.setPalette(self._pal)

        # Apply padding as text margins (immune to QSS interception)
        padding = style.get("padding", [8, 4])
        pad_h = padding[0]
        pad_v = padding[1]
        icon_width = 0
        if style.get("icon"):
            icon_width = style.get("icon-size", 16) + style.get(
                "icon-padding", 8
            )
        self.setTextMargins(pad_h + icon_width, pad_v, pad_h, pad_v)

    def initStyleOption(self, option: QStyleOptionFrame) -> None:
        """Override the palette used by the style to paint the widget."""
        self.setPalette(self.ayon_palette)
        super().initStyleOption(option)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint background, border, and focus ring, then delegate text rendering.

        Draws the styled background rectangle and border first using QPainter
        directly (no style or stylesheet involvement), then calls
        super().paintEvent() which renders the text, cursor, and selection
        highlight on top.  Qt's PE_PanelLineEdit call inside that base
        implementation is intercepted by LineEditDrawer which returns
        immediately for AYLineEdit instances, so our background is preserved.
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

        bg_color = QColor(style.get("background-color", "#272d35"))
        border_color = QColor(style.get("border-color", "#41474d"))
        border_width = style.get("border-width", 1)
        border_radius = style.get("border-radius", 2)
        opacity = style.get("opacity", 1.0)

        focus_outline_width = style.get("focus-outline-width", 2)
        focus_outline_color = QColor(
            style.get("focus-outline-color", "#8fceff")
        )

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

        # icon
        icon_name = style.get("icon")
        if icon_name:
            icon_color = QColor(style.get("icon-color", "#888888"))
            icon_size = style.get("icon-size", 16)
            x = style.get("padding", [8, 4])[0]
            pixmap = get_icon(icon_name, color=icon_color).pixmap(
                icon_size, icon_size
            )
            y = (rect.height() - icon_size) / 2.0
            painter.drawPixmap(x, y, icon_size, icon_size, pixmap)

        # Border
        border_pen = QPen(border_color)
        border_pen.setWidthF(border_width)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(bg_rect, border_radius, border_radius)

        # Focus ring (drawn inset so it fits within the widget rect)
        if has_focus:
            half_fw = focus_outline_width / 2.0
            focus_rect = rect.adjusted(half_fw, half_fw, -half_fw, -half_fw)
            focus_pen = QPen(focus_outline_color)
            focus_pen.setWidthF(focus_outline_width)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(focus_rect, border_radius, border_radius)

        painter.end()

        # Let QLineEdit draw text, placeholder, cursor, and selection on top.
        # LineEditDrawer intercepts PE_PanelLineEdit for AYLineEdit and is a
        # no-op, so the background we just drew is preserved.
        super().paintEvent(event)

    def sizeHint(self) -> QSize:
        """Override sizeHint to account for padding."""
        size = super().sizeHint()
        style = self.variant_style()
        padding = style.get("padding", [8, 4])
        size.setWidth(size.width() + padding[0] * 2)
        size.setHeight(size.height() + padding[1] * 2)
        return size


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def _build() -> QWidget:
        container = AYContainer(
            variant=AYContainer.Variants.Low,
            layout=AYContainer.Layout.HBox,
            layout_margin=20,
            layout_spacing=20,
        )
        container.setMinimumWidth(300)

        disabled_edit = AYLineEdit(
            placeholder="Disabled",
        )
        disabled_edit.setEnabled(False)
        container.add_widget(disabled_edit)

        for variant in QLineEditVariants:
            line_edit = AYLineEdit(
                placeholder="Enter text here",
                variant=variant,
            )
            container.add_widget(line_edit)

        return container

    test(_build, style=Style.AyonStyleOverCSS)
