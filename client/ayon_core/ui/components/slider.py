"""AYSlider component module."""

from __future__ import annotations

from qtpy.QtCore import QRectF, Qt, Signal
from qtpy.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen, QPixmap
from qtpy.QtWidgets import QSlider, QWidget

from ..style_types import StyleDict, get_ayon_style
from ..variants import AYSliderVariants
from .container import AYContainer
from .label import AYLabel
from .style_mixin import StyleMixin


class AYSliderBar(StyleMixin, QSlider):
    """Custom-painted horizontal slider track and handle.

    Reads all visual properties (track height, handle size, colors, etc.)
    from ``ayon_style.json`` via the ``AYSlider`` variant block.  The native
    Qt style is still routed through ``AYONStyle`` (``setStyle``), but the
    visual painting is done entirely in ``paintEvent`` so there is no
    dependency on ``drawComplexControl(CC_Slider, ...)``.

    Args:
        parent: Parent widget.
        variant_str: Variant string key used to fetch the style dict.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        variant: AYSliderVariants = AYSliderVariants.Default,
    ) -> None:
        self._variant_str = variant.value
        self._style_data = StyleDict()
        super().__init__(Qt.Orientation.Horizontal, parent)

        # Remove all native decoration — we paint everything ourselves.
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

        _style = get_ayon_style()
        self.setStyle(_style)
        self._style_data = _style.model.get_styles(
            "AYSlider",
            variant=self._variant_str,
        )
        self._style_data.set_context(self)

    def _draw_slider(self, painter: QPainter, style: StyleDict) -> None:
        """Draw track, filled portion, and handle.

        Args:
            painter: QPainter instance (already configured).
            style: Style dictionary for the current state.
        """
        track_h = style.get("track-height", 4)
        track_radius = style.get("track-radius", 2)
        track_color = QColor(style.get("track-color", "#41474d"))
        filled_color = QColor(style.get("filled-color", "#8fceff"))
        handle_size = style.get("handle-size", 14)
        handle_color = QColor(style.get("handle-color", "#8fceff"))
        handle_border_color = QColor(
            style.get("handle-border-color", "#8fceff")
        )
        handle_border_width = style.get("handle-border-width", 0)

        w = self.width()
        h = self.height()

        # Horizontal padding so the handle centre can reach both ends.
        pad = 0
        track_y = (h - track_h) / 2.0
        track_rect = QRectF(pad, track_y, w - pad * 2, track_h)

        minimum = self.minimum()
        maximum = self.maximum()
        value = self.value()
        span = maximum - minimum
        ratio = (value - minimum) / span if span > 0 else 0.0

        filled_w = track_rect.width() * ratio
        filled_rect = QRectF(track_rect.x(), track_rect.y(), filled_w, track_h)

        # Empty track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_color))
        painter.drawRoundedRect(track_rect, track_radius, track_radius)

        # Filled portion (clip to left half of track)
        if filled_w > 0:
            painter.setBrush(QBrush(filled_color))
            painter.drawRoundedRect(filled_rect, track_radius, track_radius)

        # Handle
        h_size = handle_size / 2.0
        t_width = track_rect.width() - handle_size
        handle_x = track_rect.x() + h_size + t_width * ratio
        handle_y = h / 2.0
        handle_r = handle_size / 2.0
        handle_rect = QRectF(
            handle_x - handle_r,
            handle_y - handle_r,
            handle_size,
            handle_size,
        )

        if handle_border_width > 0:
            pen = QPen(handle_border_color)
            pen.setWidthF(handle_border_width)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(QBrush(handle_color))
        painter.drawEllipse(handle_rect)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint track, filled portion, and handle using QPainter directly.

        Args:
            event: The paint event (unused — we repaint the full widget).
        """
        is_disabled = not self.isEnabled()
        is_hover = self.underMouse()

        if is_disabled:
            state = "disabled"
        elif is_hover:
            state = "hover"
        else:
            state = "base"

        style = self._style_data[state]

        opacity = style.get("opacity", 1.0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if opacity < 1.0:
            buffer = QPixmap(self.size() * self.devicePixelRatioF())
            buffer.setDevicePixelRatio(self.devicePixelRatioF())
            buffer.fill(Qt.GlobalColor.transparent)

            bp = QPainter(buffer)
            bp.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_slider(bp, style)
            bp.end()

            painter.setOpacity(opacity)
            painter.drawPixmap(0, 0, buffer)
        else:
            self._draw_slider(painter, style)

        painter.end()


class AYSlider(AYContainer):
    """Composite slider widget: caption label + slider bar + value label.

    Layout (VBox root)::

        ┌─────────────────────────────────┐
        │ Caption label (optional)        │
        │ [========○──────────────] 220   │
        └─────────────────────────────────┘

    The numeric value display on the right is a read-only ``AYLabel`` that
    updates live as the slider moves.

    Args:
        parent: Parent widget.
        label: Caption text shown above the slider (hidden when empty).
        value: Initial integer value.
        minimum: Minimum integer value.
        maximum: Maximum integer value.
        step: Snapping step; values are always multiples of this.
        variant: Visual style variant.

    Signals:
        value_changed (int): Emitted whenever the slider value changes.
    """

    Variants = AYSliderVariants
    value_changed = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        label: str = "",
        value: int = 0,
        minimum: int = 0,
        maximum: int = 100,
        step: int = 1,
        variant: Variants = Variants.Default,
    ) -> None:
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants(variant.value),
            layout_spacing=5,
            layout_margin=0,
        )

        self._variant_str = variant.value
        self._style_data = get_ayon_style().model.get_styles(
            "AYSlider",
            variant=self._variant_str,
        )
        self._step = max(1, step)

        # --- Caption label ---------------------------------------------------
        self._caption: AYLabel | None = None
        if label:
            self._caption = AYLabel(
                label,
                text_color=self._style_data["base"].get(
                    "label-color", "#ffffff"
                ),
                bold=self._style_data["base"].get("label-font-weight", 600)
                > 500,
            )
            self.add_widget(self._caption)

        # --- Inner HBox row --------------------------------------------------
        row_spacing = self._style_data["base"].get("row-spacing", 6)
        self._row = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants(self._variant_str),
            layout_spacing=row_spacing,
            layout_margin=0,
        )

        # Slider bar
        self._bar = AYSliderBar(variant=AYSlider.Variants(self._variant_str))
        self._bar.setMinimum(minimum)
        self._bar.setMaximum(maximum)
        self._bar.setSingleStep(self._step)
        self._bar.setPageStep(self._step * 10)

        # Value label — initialise with the snapped initial value.
        snapped_initial = self._snap_unclamped(value, minimum, maximum)
        self._value_label = AYLabel(
            str(snapped_initial),
            variant=AYLabel.Variants.Default,
            text_color=self._style_data["base"].get("value-color", "#ffffff"),
        )
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        value_min_w = self._style_data["base"].get("value-min-width", 40)
        self._value_label.setMinimumWidth(value_min_w)

        self._row.add_widget(self._bar, stretch=1)
        self._row.add_widget(self._value_label, stretch=0)
        self.add_widget(self._row)

        # Connect before setValue so _on_bar_value_changed fires and keeps
        # the label in sync with the snapped value from the very first set.
        self._bar.valueChanged.connect(self._on_bar_value_changed)
        self._bar.setValue(snapped_initial)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _snap_unclamped(self, v: int, minimum: int, maximum: int) -> int:
        """Snap *v* to the nearest step and clamp to [minimum, maximum].

        This version accepts explicit range arguments so it can be called
        before ``self._bar`` has its range configured.

        Args:
            v: Raw integer value.
            minimum: Lower bound.
            maximum: Upper bound.

        Returns:
            Clamped and snapped integer value.
        """
        v = max(minimum, min(maximum, v))
        if self._step > 1:
            v = round(v / self._step) * self._step
            v = max(minimum, min(maximum, v))
        return v

    def _snap(self, v: int) -> int:
        """Snap *v* to the nearest multiple of ``_step`` within range.

        Args:
            v: Raw integer value.

        Returns:
            Clamped and snapped integer value.
        """
        return self._snap_unclamped(
            v, self._bar.minimum(), self._bar.maximum()
        )

    def _on_bar_value_changed(self, raw: int) -> None:
        """Snap the raw slider value, sync the label, emit the signal.

        Args:
            raw: The raw integer value emitted by ``QSlider.valueChanged``.
        """
        snapped = self._snap(raw)
        if snapped != raw:
            # Re-set without entering an infinite loop.
            self._bar.blockSignals(True)
            self._bar.setValue(snapped)
            self._bar.blockSignals(False)

        self._value_label.setText(str(snapped))
        self.value_changed.emit(snapped)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def value(self) -> int:
        """Return the current slider value.

        Returns:
            Current snapped integer value.
        """
        return self._snap(self._bar.value())

    def setValue(self, v: int) -> None:
        """Set the slider to *v* (clamped and snapped).

        Args:
            v: Target integer value.
        """
        self._bar.setValue(self._snap(v))

    def setRange(self, minimum: int, maximum: int) -> None:
        """Update the slider range.

        Args:
            minimum: New minimum value.
            maximum: New maximum value.
        """
        self._bar.setMinimum(minimum)
        self._bar.setMaximum(maximum)

    def setStep(self, step: int) -> None:
        """Change the snapping step.

        Args:
            step: New step size (must be >= 1).
        """
        self._step = max(1, step)
        self._bar.setSingleStep(self._step)
        self._bar.setPageStep(self._step * 10)
        # Re-snap current value to the new step.
        self._bar.setValue(self._snap(self._bar.value()))

    def setLabel(self, text: str) -> None:
        """Update the caption label text.

        Args:
            text: New caption string.
        """
        if self._caption is not None:
            self._caption.setText(text)
