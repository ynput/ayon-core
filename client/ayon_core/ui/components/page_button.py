"""AYPageButton component module.

Provides a full-width navigation/settings row button with the layout::

    [icon]  Label text ........................  Value text  >

The left cluster (icon + label) is pinned left; the right cluster
(value + chevron) is pinned right.  A flexible gap fills the space
between them.  Default size policy is ``Expanding × Fixed``.
"""

from __future__ import annotations

import logging
import os

from qtmaterialsymbols import get_icon  # type: ignore
from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QFontMetrics

from ..color_utils import compute_color_for_contrast
from ..style_types import get_ayon_style
from ..variants import AYPageButtonVariants, QPushButtonVariants
from .buttons import AYButton

logger = logging.getLogger(__name__)


class AYPageButton(AYButton):
    """Full-width navigation/settings page button.

    Renders a single-row entry with a left cluster (optional icon +
    label text) pinned to the left and a right cluster (value text +
    chevron) pinned to the right.  A flexible gap fills the remaining
    horizontal space.

    The visual style is driven by the ``"AYPageButton"`` block in
    ``ayon_style.json``.  All painting is done in a custom
    ``paintEvent``; the Qt button bevel is not used.

    Args:
        label: Text displayed in the left cluster.
        value: Secondary text displayed in the right cluster (before the
            chevron).  Pass an empty string to hide it.
        variant: Visual variant.  Only ``Default`` is defined.
        icon: Material Symbol icon name for the left icon (optional).
        icon_size: Pixel size of the left icon.
        chevron_icon: Material Symbol name for the right-hand chevron.
        chevron_size: Pixel size of the chevron icon.
        tooltip: Tooltip text.
        name_id: ``objectName`` for QSS targeting.
        **kwargs: Forwarded to ``AYButton`` / ``QPushButton``.

    Signals:
        clicked (bool): Inherited from ``QPushButton``.

    Example::

        btn = AYPageButton(
            label="Featured version",
            value="Done",
            icon="star",
        )
        btn.clicked.connect(lambda: print("navigating …"))
    """

    Variants = AYPageButtonVariants

    def __init__(
        self,
        label: str = "",
        value: str = "",
        *,
        variant: AYPageButtonVariants = AYPageButtonVariants.Default,
        icon: str | None = None,
        icon_size: int = 16,
        chevron_icon: str = "chevron_right",
        chevron_size: int = 16,
        tooltip: str = "",
        name_id: str = "",
        **kwargs,
    ) -> None:
        """Initialize an AYPageButton.

        Args:
            label: Left-cluster label text.
            value: Right-cluster value text (optional).
            variant: Visual variant (only ``Default`` available).
            icon: Material Symbol name for the left icon.
            icon_size: Pixel size for the left icon.
            chevron_icon: Material Symbol name for the chevron.
            chevron_size: Pixel size for the chevron icon.
            tooltip: Tooltip string shown on hover.
            name_id: Widget ``objectName`` for QSS targeting.
            **kwargs: Extra keyword arguments forwarded to
                ``AYButton.__init__``.
        """
        self._value: str = value
        self._chevron_size: int = chevron_size
        self._icon_qicon: QtGui.QIcon | None = None
        self._chevron_qicon: QtGui.QIcon | None = None
        self._force_hover: bool = False

        # Call AYButton with a valid QPushButton variant but no icon so
        # AYButton doesn't call set_icon() (which would use the wrong
        # style data).  We manage both icons ourselves below.
        super().__init__(
            label,
            variant=QPushButtonVariants.Surface,
            icon=None,
            icon_size=icon_size,
            tooltip=tooltip,
            name_id=name_id,
            **kwargs,
        )

        # --- Override style data with AYPageButton-specific block ------
        self._style_data = get_ayon_style().model.get_styles(
            "AYPageButton", variant.value
        )
        self._style_data.set_context(self)

        # Recompute icon colors from the AYPageButton palette
        icon_color_str = self._style_data["base"].get("icon-color", "#ffffff")
        self._icon_color = QColor(icon_color_str)

        hover_bg_str = (
            self._style_data["base"]
            .get("hover", {})
            .get("background-color", "#000000")
        )
        self._icon_hover_color = self._icon_color
        if isinstance(hover_bg_str, str) and self._icon_color.isValid():
            self._icon_hover_color = compute_color_for_contrast(
                QColor(hover_bg_str).toTuple(),
                self._icon_color.toTuple(),
                min_contrast_ratio=7,
            )

        # Build left icon QIcon
        if icon:
            self._icon = icon
            self._icon_qicon = get_icon(
                icon_name_off=icon,
                color_off=self._icon_color,
                icon_name_on=icon,
                color_on=self._icon_hover_color,
            )

        # Build chevron QIcon
        chevron_color_str = self._style_data["base"].get(
            "chevron-color", "#aaaaaa"
        )
        chevron_color = QColor(chevron_color_str)
        chevron_hover_color = chevron_color
        if isinstance(hover_bg_str, str) and chevron_color.isValid():
            chevron_hover_color = compute_color_for_contrast(
                QColor(hover_bg_str).toTuple(),
                chevron_color.toTuple(),
                min_contrast_ratio=4.5,
            )
        self._chevron_qicon = get_icon(
            icon_name_off=chevron_icon,
            color_off=chevron_color,
            icon_name_on=chevron_icon,
            color_on=chevron_hover_color,
        )

        # Force Expanding × Fixed regardless of JSON fixed-width setting
        self.setFixedHeight(self._style_data["base"].get("height", 44))
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def value(self) -> str:
        """Return the current right-cluster value text.

        Returns:
            The value string set at construction or via ``set_value``.
        """
        return self._value

    def set_value(self, text: str) -> None:
        """Update the right-cluster value text and repaint.

        Args:
            text: New value string (empty string hides the value field).
        """
        self._value = text
        self.update()

    def set_label(self, text: str) -> None:
        """Update the left-cluster label text and repaint.

        Args:
            text: New label string.
        """
        self.setText(text)
        self.update()

    def set_force_hover(self, value: bool) -> None:
        """Force (or release) the hover appearance for snapshot tests.

        Args:
            value: ``True`` to paint as if hovered; ``False`` to restore
                normal appearance.
        """
        self._force_hover = value
        self.update()

    # ------------------------------------------------------------------ #
    # Sizing                                                             #
    # ------------------------------------------------------------------ #

    def sizeHint(self) -> QtCore.QSize:
        """Return the preferred size of the widget.

        Returns:
            A ``QSize`` with the preferred width and height.
        """
        size = super().sizeHint()
        size.setHeight(self._style_data["base"].get("height", 24))
        return size

    def rect(self) -> QtCore.QRect:
        if not hasattr(super(), "_rect_set"):
            # FIXME: a bit of a hack to set the height of the button
            #        needs to be fixed in AYButton.
            h = self._style_data["base"].get("height", 24)
            self.setFixedHeight(h)
            setattr(self, "_rect_set", True)
        rect = super().rect()
        return rect

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    def _is_hovered(self) -> bool:
        """Return ``True`` when the widget is in a hover state.

        Returns:
            ``True`` if the cursor is over the widget or
            ``_force_hover`` is set.
        """
        return self.underMouse() or self._force_hover

    def _current_state_key(self) -> str:
        """Return the active style-state key for the current widget state.

        Returns:
            One of ``"disabled"``, ``"pressed"``, ``"hover"``, or
            ``""`` (base/normal).
        """
        if not self.isEnabled():
            return "disabled"
        if self.isDown():
            return "pressed"
        if self._is_hovered():
            return "hover"
        return "base"

    def _get_current_style(self) -> dict:
        """Return a merged style dict for the current widget state.

        Starts with all base (non-state) values from ``_style_data``
        and overlays the active state sub-dict on top.

        Returns:
            A plain ``dict`` mapping style keys to resolved values.
        """
        # Overlay active state overrides
        state_key = self._current_state_key()
        return self._style_data[state_key]

    # ------------------------------------------------------------------ #
    # Painting                                                             #
    # ------------------------------------------------------------------ #

    def paintEvent(  # noqa: N802
        self, arg__1: QtGui.QPaintEvent
    ) -> None:
        """Render the full-width page button.

        Draws background, left cluster (icon + label), and right cluster
        (value + chevron) using ``QPainter`` directly.  No Qt bevel or
        ``QStyle.drawControl`` is used.

        Args:
            event: The paint event (unused — the full widget is redrawn).
        """
        style = self._get_current_style()

        padding = style.get("padding", [12, 10])
        if isinstance(padding, list) and len(padding) >= 1:
            pad_h = padding[0]
        else:
            pad_h = 12

        icon_gap = style.get("icon-gap", 8)
        value_gap = style.get("value-gap", 8)
        border_radius = style.get("border-radius", 4)
        opacity = style.get("opacity", 1.0)

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setOpacity(opacity)

        rect = self.rect()

        # --- Background --------------------------------------------------
        bg_raw = style.get("background-color", "transparent")
        if isinstance(bg_raw, str) and bg_raw != "transparent":
            bg = QColor(bg_raw)
            if bg.isValid() and bg.alpha() > 0:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QtGui.QBrush(bg))
                p.drawRoundedRect(
                    QtCore.QRectF(rect), border_radius, border_radius
                )

        # Content rect inset by horizontal padding
        content_left = rect.left() + pad_h
        content_right = rect.right() - pad_h
        center_y = rect.top() + rect.height() // 2

        # --- Right cluster: chevron then value text ----------------------
        right_cursor = content_right

        # Chevron
        if self._chevron_qicon is not None:
            cs = self._chevron_size
            chevron_rect = QtCore.QRect(
                right_cursor - cs,
                center_y - cs // 2,
                cs,
                cs,
            )
            is_hover = self._is_hovered() and self.isEnabled()
            icon_state = (
                QtGui.QIcon.State.On if is_hover else QtGui.QIcon.State.Off
            )
            self._chevron_qicon.paint(
                p,
                chevron_rect,
                Qt.AlignmentFlag.AlignCenter,
                QtGui.QIcon.Mode.Normal,
                icon_state,
            )
            right_cursor = chevron_rect.left() - value_gap

        # Value text (fixed width, right-aligned)
        if self._value:
            value_color_raw = style.get("value-color", "#909090")
            p.setPen(QColor(value_color_raw))
            p.setFont(self.font())
            fm: QFontMetrics = self.fontMetrics()
            value_w = fm.horizontalAdvance(self._value)
            value_rect = QtCore.QRect(
                right_cursor - value_w,
                rect.top(),
                value_w,
                rect.height(),
            )
            p.drawText(
                value_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                self._value,
            )
            right_cursor = value_rect.left() - value_gap

        # --- Left cluster: icon then label text --------------------------
        left_cursor = content_left

        # Left icon
        if self._icon_qicon is not None:
            sz = self._icon_size
            icon_rect = QtCore.QRect(
                left_cursor,
                center_y - sz // 2,
                sz,
                sz,
            )
            is_hover = self._is_hovered() and self.isEnabled()
            icon_state = (
                QtGui.QIcon.State.On if is_hover else QtGui.QIcon.State.Off
            )
            self._icon_qicon.paint(
                p,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                QtGui.QIcon.Mode.Normal,
                icon_state,
            )
            left_cursor = icon_rect.right() + icon_gap

        # Label text (elided if too narrow)
        label = self.text()
        if label:
            label_color_raw = style.get(
                "color",
                style.get("color", "#ffffff"),
            )
            p.setPen(QColor(label_color_raw))
            p.setFont(self.font())
            fm = self.fontMetrics()
            available_w = max(0, right_cursor - left_cursor)
            elided = fm.elidedText(
                label, Qt.TextElideMode.ElideRight, available_w
            )
            label_rect = QtCore.QRect(
                left_cursor,
                rect.top(),
                available_w,
                rect.height(),
            )
            p.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                elided,
            )

        p.end()


# TEST =======================================================================


if __name__ == "__main__":
    from ..tester import Style, test
    from .container import AYContainer

    def _build_test():
        container = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.High,
            layout_spacing=2,
            layout_margin=12,
        )

        rows = [
            # (label, value, icon)
            ("Featured version", "Done", "star"),
            ("Settings", "", "settings"),
            (
                (
                    "A very long label that should be elided when the window "
                    "is narrow"
                ),
                "Value",
                "info",
            ),
            ("No icon, with value", "Some text", None),
            ("No value, no icon", "", None),
        ]

        for label, value, icon in rows:
            btn = AYPageButton(
                label=label,
                value=value,
                icon=icon,
                tooltip=f"{label!r} button",
            )
            container.add_widget(btn)

        # Disabled example
        disabled_btn = AYPageButton(
            label="Disabled entry",
            value="N/A",
            icon="block",
        )
        disabled_btn.setEnabled(False)
        container.add_widget(disabled_btn)

        container.addStretch(1)
        return container

    os.environ["QT_SCALE_FACTOR"] = "1"
    test(_build_test, style=Style.AYONStyleOverCSS)
