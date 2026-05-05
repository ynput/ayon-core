"""Small overlay widget with a columns-per-row slider for Loader grid view."""
from __future__ import annotations

from qtpy import QtWidgets, QtCore

from .products_grid_widget import DEFAULT_GRID_COLUMNS, GRID_COLUMNS_MAX, GRID_COLUMNS_MIN


class ScaleSliderOverlay(QtWidgets.QFrame):
    """Compact slider overlay for grid column count (bottom-right of products area)."""

    grid_columns_changed = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ScaleSliderOverlay")
        self.setFrameStyle(QtWidgets.QFrame.Shape.NoFrame)
        self._col_lo = GRID_COLUMNS_MIN
        self._col_hi = GRID_COLUMNS_MAX
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        label = QtWidgets.QLabel("Columns", self)
        label.setStyleSheet("font-size: 11px;")
        self._slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal, self)
        self._slider.setRange(self._col_lo, self._col_hi)
        self._slider.setValue(DEFAULT_GRID_COLUMNS)
        self._slider.setFixedWidth(80)
        self._slider.setToolTip(
            "Columns per row (left: fewer, larger tiles — right: more, smaller tiles)"
        )
        layout.addWidget(label, 0)
        layout.addWidget(self._slider, 0)
        self._slider.valueChanged.connect(self._on_slider_changed)

    def set_column_bounds(self, lo: int, hi: int) -> None:
        """Clamp slider range to what the current viewport can fit (may shrink when narrow)."""
        self._col_lo = max(1, int(lo))
        self._col_hi = max(self._col_lo, int(hi))
        self._slider.blockSignals(True)
        self._slider.setRange(self._col_lo, self._col_hi)
        v = int(self._slider.value())
        nv = max(self._col_lo, min(self._col_hi, v))
        self._slider.setValue(nv)
        self._slider.blockSignals(False)
        if nv != v:
            self.grid_columns_changed.emit(nv)

    def _on_slider_changed(self, value: int) -> None:
        v = max(self._col_lo, min(self._col_hi, int(value)))
        if v != int(value):
            self._slider.blockSignals(True)
            self._slider.setValue(v)
            self._slider.blockSignals(False)
        self.grid_columns_changed.emit(v)

    def get_grid_columns(self) -> int:
        return max(self._col_lo, min(self._col_hi, int(self._slider.value())))

    def set_grid_columns(self, cols: int) -> None:
        v = max(self._col_lo, min(self._col_hi, int(cols)))
        if self._slider.value() != v:
            self._slider.blockSignals(True)
            self._slider.setValue(v)
            self._slider.blockSignals(False)
