"""Skeleton loader overlay for item views.

Paints placeholder rows with a shimmer highlight sweeping across them,
signalling that content is being loaded.
"""

from __future__ import annotations

from qtpy.QtCore import (
    QEasingCurve,
    QEvent,
    QObject,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    QVariantAnimation,
)
from qtpy.QtGui import QColor, QLinearGradient, QPainter, QPaintEvent
from qtpy.QtWidgets import QAbstractScrollArea, QWidget

from ..style_types import get_ayon_style
from ..variants import QTreeViewVariants

# Indentation level and text width (fraction) of placeholder rows. The
#   pattern repeats, it only has to look like a plausible hierarchy.
_ROW_PATTERN = (
    (0, 0.55),
    (1, 0.45),
    (1, 0.62),
    (2, 0.38),
    (2, 0.5),
    (2, 0.32),
    (1, 0.58),
    (0, 0.4),
    (1, 0.52),
    (2, 0.44),
    (1, 0.36),
    (0, 0.6),
)


class AYSkeletonLoader(QWidget):
    """Animated skeleton placeholder overlaid on top of a view.

    The overlay covers the viewport of the target widget (or the widget
    itself) and follows its geometry. It is transparent for mouse events.

    To avoid flashing for loads which finish almost immediately the
    skeleton appears only after ``show_delay`` milliseconds, and fades
    out when loading finishes.

    Args:
        target: Widget to cover, usually an item view.
        variant: Tree view style variant used to pick colors and sizes.
        show_delay: Delay in milliseconds before the skeleton appears.
    """

    _SHIMMER_DURATION = 1500
    _FADE_DURATION = 150

    def __init__(
        self,
        target: QWidget,
        variant: QTreeViewVariants = QTreeViewVariants.Low,
        show_delay: int = 80,
    ) -> None:
        super().__init__(target)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._target = target
        self._variant = variant.value
        self._loading = False
        self._phase = 0.0
        self._opacity = 0.0

        style = get_ayon_style().model
        tv_style = style.get_style("QTreeView", self._variant)
        hover_style = style.get_style("QTreeView", self._variant, "hover")
        self._background = QColor(
            tv_style.get("background-color", "#1c2026")
        )
        self._row_height = int(tv_style.get("item-height", 24))
        self._indent = int(tv_style.get("indent", 22))
        base = QColor(hover_style.get("background-color", "#2c313a"))
        self._base_color = base
        self._highlight_color = base.lighter(165)

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(show_delay)
        self._show_timer.timeout.connect(self._start)

        self._shimmer_anim = QVariantAnimation(self)
        self._shimmer_anim.setStartValue(0.0)
        self._shimmer_anim.setEndValue(1.0)
        self._shimmer_anim.setDuration(self._SHIMMER_DURATION)
        self._shimmer_anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._shimmer_anim.setLoopCount(-1)
        self._shimmer_anim.valueChanged.connect(self._on_phase_changed)

        self._fade_anim = QVariantAnimation(self)
        self._fade_anim.setDuration(self._FADE_DURATION)
        self._fade_anim.valueChanged.connect(self._on_opacity_changed)
        self._fade_anim.finished.connect(self._on_fade_finished)

        self._geometry_source().installEventFilter(self)
        self.hide()

    def is_loading(self) -> bool:
        return self._loading

    def set_loading(self, loading: bool) -> None:
        """Show or hide the skeleton.

        Args:
            loading: Whether content is being loaded.
        """
        if loading == self._loading:
            return
        self._loading = loading
        if loading:
            if not self.isVisible():
                self._show_timer.start()
            else:
                self._fade_to(1.0)
            return

        self._show_timer.stop()
        if self.isVisible():
            self._fade_to(0.0)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self._geometry_source() and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._update_geometry()
        return super().eventFilter(obj, event)

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(self._opacity)
        rect = self.rect()
        # Hide anything the view paints underneath (e.g. stale rows)
        painter.fillRect(rect, self._background)

        width = rect.width()
        band = max(width * 0.5, 120.0)
        # Sweep diagonally from just left of the widget to its right edge
        start_x = -band + self._phase * (width + band)
        gradient = QLinearGradient(
            QPointF(start_x, 0.0),
            QPointF(start_x + band, band * 0.35),
        )
        gradient.setColorAt(0.0, self._base_color)
        gradient.setColorAt(0.5, self._highlight_color)
        gradient.setColorAt(1.0, self._base_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)

        row_height = self._row_height
        icon_size = min(14, row_height - 8)
        bar_height = max(6, row_height // 3)
        row_count = rect.height() // row_height + 1
        fade_rows = max(row_count, 1)
        for row in range(row_count):
            level, text_ratio = _ROW_PATTERN[row % len(_ROW_PATTERN)]
            # Rows further down fade out gradually
            painter.setOpacity(
                self._opacity * max(0.25, 1.0 - (row / fade_rows) * 0.75)
            )
            top = row * row_height
            x = 6 + (level + 1) * self._indent
            icon_rect = QRectF(
                x,
                top + (row_height - icon_size) / 2,
                icon_size,
                icon_size,
            )
            painter.drawRoundedRect(icon_rect, 3, 3)
            text_x = icon_rect.right() + 6
            available = width - text_x - 8
            if available <= 0:
                continue
            text_rect = QRectF(
                text_x,
                top + (row_height - bar_height) / 2,
                available * text_ratio,
                bar_height,
            )
            painter.drawRoundedRect(
                text_rect, bar_height / 2, bar_height / 2
            )
        painter.end()

    def _geometry_source(self) -> QWidget:
        if isinstance(self._target, QAbstractScrollArea):
            return self._target.viewport()
        return self._target

    def _update_geometry(self) -> None:
        source = self._geometry_source()
        if source is self._target:
            self.setGeometry(self._target.rect())
        else:
            self.setGeometry(source.geometry())

    def _start(self) -> None:
        if not self._loading:
            return
        self._update_geometry()
        self._phase = 0.0
        self._opacity = 0.0
        self.show()
        self.raise_()
        self._shimmer_anim.start()
        self._fade_to(1.0)

    def _fade_to(self, value: float) -> None:
        self._fade_anim.stop()
        self._fade_anim.setStartValue(self._opacity)
        self._fade_anim.setEndValue(value)
        self._fade_anim.start()

    def _on_phase_changed(self, value: float) -> None:
        self._phase = float(value)
        self.update()

    def _on_opacity_changed(self, value: float) -> None:
        self._opacity = float(value)
        self.update()

    def _on_fade_finished(self) -> None:
        if self._loading:
            return
        self._shimmer_anim.stop()
        self.hide()
