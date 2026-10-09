"""checkbox"""

from __future__ import annotations

from qtpy.QtCore import QEasingCurve, QRect, QSize, QVariantAnimation
from qtpy.QtGui import QPainter, QPaintEvent
from qtpy.QtWidgets import QCheckBox, QSizePolicy, QStyle, QStyleOptionButton

from ..style_types import get_ayon_style
from ..variants import QCheckBoxVariants
from .style_mixin import StyleMixin


class AYCheckBox(StyleMixin, QCheckBox):
    """AYON styled checkbox widget.

    Overrides Qt's stylesheet painting with AYONStyle custom rendering.

    Args:
        *args: Positional arguments passed to QCheckBox.
        **kwargs: Keyword arguments passed to QCheckBox.
    """

    Variants = QCheckBoxVariants

    _TOGGLE_ANIMATION_DURATION = 120

    def __init__(
        self,
        *args,
        variant: Variants = Variants.Default,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._variant_str = variant.value
        self._style_dict = None
        self.setStyle(get_ayon_style())

        # 0.0 is fully unchecked, 1.0 is fully checked. Read by the
        # CheckboxDrawer to paint the sliding toggle.
        self._toggle_progress = 1.0 if self.isChecked() else 0.0
        self._toggle_anim = QVariantAnimation(self)
        self._toggle_anim.setDuration(self._TOGGLE_ANIMATION_DURATION)
        self._toggle_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._toggle_anim.valueChanged.connect(self._on_toggle_anim_changed)
        self.toggled.connect(self._on_toggled)

        if variant == AYCheckBox.Variants.Button:
            self.setFixedSize(self.sizeHint())

    @property
    def toggle_progress(self) -> float:
        """Animated toggle position, 0.0 (unchecked) to 1.0 (checked)."""
        return self._toggle_progress

    def is_animating(self) -> bool:
        """Whether the toggle slider is currently animating."""
        return self._toggle_anim.state() == QVariantAnimation.State.Running

    def _on_toggled(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        self._toggle_anim.stop()
        if not (self.isVisible() and self.isEnabled()):
            # Do not animate hidden or disabled checkboxes.
            self._toggle_progress = target
            self.update()
            return
        self._toggle_anim.setStartValue(self._toggle_progress)
        self._toggle_anim.setEndValue(target)
        self._toggle_anim.start()

    def _on_toggle_anim_changed(self, value: float) -> None:
        self._toggle_progress = float(value)
        self.update()

    @property
    def style_dict(self):
        if self._style_dict is None:
            self._style_dict = get_ayon_style().model.get_style(
                "QCheckBox", variant=self._variant_str
            )
            self._style_dict.set_context(self)
        return self._style_dict

    def initStyleOption(self, option: QStyleOptionButton) -> None:
        """Initialize the style option with the default implementation, then
        override any properties needed for our custom painting.

        Args:
            option: The style option to initialize.
        """
        super().initStyleOption(option)
        option.fontMetrics = self.fontMetrics()

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        """Render the checkbox using the AYON custom style.

        Args:
            arg__1: The paint event delivered by Qt.
        """
        p = QPainter(self)
        p.setFont(self.font())

        option = QStyleOptionButton()
        self.initStyleOption(option)
        _style = get_ayon_style()

        if not self.isEnabled():
            # Fade the whole checkbox, the toggle is painted with its
            # checked / unchecked colors only.
            disabled_style = _style.model.get_style(
                "QCheckBox", variant=self._variant_str, state="disabled"
            )
            p.setOpacity(disabled_style.get("opacity", 1.0))

        _expanding = self.sizePolicy().horizontalPolicy() in (
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        if _expanding:
            ind_w = _style.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, option, self
            )
            ind_h = _style.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorHeight, option, self
            )
            spacing = _style.pixelMetric(
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, self
            )
            cy = self.height() // 2

            ind_opt = QStyleOptionButton(option)
            ind_opt.rect = QRect(0, cy - ind_h // 2, ind_w, ind_h)
            _style.drawPrimitive(
                QStyle.PrimitiveElement.PE_IndicatorCheckBox, ind_opt, p, self
            )

            label_opt = QStyleOptionButton(option)
            label_opt.rect = QRect(
                ind_w + spacing,
                0,
                self.width() - ind_w - spacing,
                self.height(),
            )
            _style.drawControl(
                QStyle.ControlElement.CE_CheckBoxLabel, label_opt, p, self
            )
        else:
            _style.drawControl(
                QStyle.ControlElement.CE_CheckBox, option, p, self
            )

    def sizeHint(self) -> QSize:
        size = super().sizeHint()

        if self._variant_str == AYCheckBox.Variants.Button.value:
            h_pad, v_pad = self.style_dict.get("padding", [6, 6])
            size.setWidth(size.width() + h_pad * 2)
            size.setHeight(size.height() + v_pad * 2)
        else:
            # Recalculate width using the custom style's actual metrics
            option = QStyleOptionButton()
            self.initStyleOption(option)
            _style = get_ayon_style()
            ind_w = _style.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, option, self
            )
            spacing = _style.pixelMetric(
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, self
            )
            fm = self.fontMetrics()
            text_w = fm.horizontalAdvance(self.text())
            size.setWidth(ind_w + spacing + text_w)

        return size
