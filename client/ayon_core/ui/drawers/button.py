"""ButtonDrawer: custom painting for QPushButton."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from qtpy import QtCore, QtGui
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)
from qtpy.QtWidgets import (
    QPushButton,
    QStyle,
    QStyleOption,
    QStyleOptionButton,
    QWidget,
)

from ._utils import enum_to_str, style_font

if TYPE_CHECKING:
    from ..style import AYONStyle


class ButtonDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def _super(self):
        """Return proxy for calling QCommonStyle methods on style_inst."""
        from ..style import AYONStyle as _AYONStyle

        return super(_AYONStyle, self.style_inst)

    @property
    def base_class(self):
        return {"QPushButton": QPushButton}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButton,
                "QPushButton",
            ): [
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_PushButtonBevel,
                ),
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_PushButtonLabel,
                ),
            ],
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButtonBevel,
                "QPushButton",
            ): self.draw_push_button_bevel,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButtonLabel,
                "QPushButton",
            ): self.draw_push_button_label,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ContentsType,
                QStyle.ContentsType.CT_PushButton,
                "QPushButton",
            ): self.calculate_push_button_size,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_PushButtonContents,
                "QPushButton",
            ): self.sub_element_rect,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_PushButtonFocusRect,
                "QPushButton",
            ): self.sub_element_rect,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ButtonMargin,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_DefaultFrameWidth,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ButtonDefaultIndicator,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_FocusFrameVMargin,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_FocusFrameHMargin,
                "QPushButton",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ):
        if metric == QStyle.PixelMetric.PM_ButtonMargin:
            return 6
        elif metric == QStyle.PixelMetric.PM_DefaultFrameWidth:
            return 0
        elif metric == QStyle.PixelMetric.PM_ButtonDefaultIndicator:
            return 0
        elif metric == QStyle.PixelMetric.PM_FocusFrameVMargin:
            return 2
        elif metric == QStyle.PixelMetric.PM_FocusFrameHMargin:
            return 2

    def get_button_variant(self, widget: QWidget) -> str:
        """Extract button variant from widget properties."""
        if widget is None:
            return "surface"
        return getattr(widget, "_variant_str", "surface")

    def get_button_has_icon(self, widget: QWidget) -> bool:
        """Check if button has an icon."""
        if widget is None:
            return False

        # Method 1: Try has_icon property
        if hasattr(widget, "has_icon"):
            return widget.has_icon  # type: ignore

        # Method 2: Try Qt property
        has_icon_prop = widget.property("has_icon")
        if has_icon_prop is not None:
            return bool(has_icon_prop)

        # Method 3: Check the actual icon
        return bool(widget.icon() and not widget.icon().isNull())  # type: ignore

    def get_button_style(
        self, widget: QWidget, state: QStyle.StateFlag
    ) -> tuple[dict, str]:
        """Get the appropriate style dictionary for the widget's variant and
        state."""
        variant = self.get_button_variant(widget)

        wstate = "base"
        if not (state & QStyle.StateFlag.State_Enabled):
            wstate = "disabled"
        elif state & QStyle.StateFlag.State_Sunken:
            wstate = "pressed"
        elif state & QStyle.StateFlag.State_MouseOver and not (
            state & QStyle.StateFlag.State_On
        ):
            wstate = "hover"
        elif state & QStyle.StateFlag.State_On:
            wstate = "checked"

        style = self.model.get_style("QPushButton", variant, wstate)
        style.set_context(widget)

        return style, wstate

    def draw_push_button_bevel(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Draw the button background and frame with hover detection."""
        if not isinstance(option, QStyleOptionButton) or widget is None:
            return

        style, _ = self.get_button_style(widget, option.state)
        rect = option.rect

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw button background with hover awareness
        bg_color = style["background-color"]
        painter.setOpacity(style.get("opacity", 1.0))

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        border_radius = style.get("border-radius", 0)

        draw_icon_as_background = style.get("icon-as-background", False)
        clip_icon_to_radius = style.get("clip-icon-to-radius", False)

        if draw_icon_as_background:
            # draw the icon clipped by the same rounded rect
            painter.save()
            if clip_icon_to_radius:
                clip_path = QPainterPath()
                clip_path.addRoundedRect(rect, border_radius, border_radius)
                painter.setClipPath(clip_path)

            mode = QtGui.QIcon.Mode.Normal
            painter.drawRoundedRect(rect, border_radius, border_radius)
            option.icon.paint(
                painter,
                rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
            )

            if clip_icon_to_radius:
                painter.setClipping(False)

            pen = QPen(QColor(style.get("border-color")))
            pen.setWidth(int(style.get("border-width", 0)))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, border_radius, border_radius)
            painter.restore()
        else:
            painter.drawRoundedRect(rect, border_radius, border_radius)

        # Draw focus outline if needed
        if (
            option.state & QStyle.StateFlag.State_HasFocus
            and option.state  # type: ignore
            & QStyle.StateFlag.State_KeyboardFocusChange
        ):
            focus_color = style["focus-outline-color"]
            pen = QPen(
                QColor(focus_color), style.get("focus-outline-width", 0)
            )
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_rect = rect.adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(
                focus_rect, border_radius + 1, border_radius + 1
            )

        painter.restore()

    def draw_push_button_label(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Draw the button text and icon."""
        if not isinstance(option, QStyleOptionButton) or widget is None:
            return

        from qtpy.QtGui import QPalette

        style, wstate = self.get_button_style(widget, option.state)  # type: ignore
        variant = self.get_button_variant(widget)

        # Set up text color
        text_color = self.model.get_widget_color(
            "color",
            style,
            widget,
            widget.palette().color(QPalette.ColorRole.ButtonText),
        )
        if not (option.state & QStyle.StateFlag.State_Enabled):  # type: ignore
            # Apply some opacity to disabled text
            text_color.setAlpha(int(255 * 0.5))

        painter.save()
        painter.setPen(text_color)

        # Set up font
        painter.setFont(widget.font())

        # Get content rectangle
        content_rect = self.style_inst.subElementRect(
            QStyle.SubElement.SE_PushButtonContents, option, widget
        )

        # Optional per-widget alignment override (None → default centered layout)
        label_alignment = getattr(widget, "_label_alignment", None)

        # Draw icon if present
        if option.icon:  # type: ignore
            if option.text and not style.get("ignore-text", False):  # type: ignore
                icon_size = option.iconSize  # type: ignore
                icon_w = icon_size.width()
                icon_h = icon_size.height()
                _gap = 4

                # Draw icon with text color inheritance
                mode = QtGui.QIcon.Mode.Normal
                if not (
                    option.state & QStyle.StateFlag.State_Enabled  # type: ignore
                ):
                    mode = QtGui.QIcon.Mode.Disabled
                elif option.state & QStyle.StateFlag.State_Sunken:  # type: ignore
                    mode = QtGui.QIcon.Mode.Active

                if label_alignment is not None:
                    # Group layout: icon + text move together as a unit
                    h_align = (
                        label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask
                    )
                    text_w = painter.fontMetrics().horizontalAdvance(
                        option.text  # type: ignore
                    )
                    group_w = icon_w + _gap + text_w
                    if h_align == Qt.AlignmentFlag.AlignLeft:
                        group_x = content_rect.left()
                    elif h_align == Qt.AlignmentFlag.AlignRight:
                        group_x = content_rect.right() - group_w
                    else:
                        group_x = (
                            content_rect.left()
                            + (content_rect.width() - group_w) // 2
                        )
                    icon_rect = QRect(
                        group_x,
                        content_rect.center().y() - icon_h // 2,
                        icon_w,
                        icon_h,
                    )
                    text_rect = QRect(
                        icon_rect.right() + _gap,
                        content_rect.top(),
                        text_w,
                        content_rect.height(),
                    )
                    option.icon.paint(  # type: ignore
                        painter,
                        icon_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        mode,
                    )
                    painter.drawText(
                        text_rect,
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        option.text,  # type: ignore
                    )
                else:
                    # Icon + text: place icon on the left (default centered)
                    icon_rect = QRect(content_rect)
                    icon_rect.setSize(icon_size)
                    icon_rect.moveCenter(
                        QtCore.QPoint(
                            content_rect.left() + style["icon-padding"][0],
                            content_rect.center().y(),
                        )
                    )
                    option.icon.paint(  # type: ignore
                        painter,
                        icon_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        mode,
                    )
                    # Adjust text rectangle
                    text_rect = QRect(content_rect)
                    text_rect.setLeft(icon_rect.right() + _gap)
                    # Draw text
                    painter.drawText(
                        text_rect,
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        option.text,  # type: ignore
                    )
            elif variant not in ("thumbnail", "entity-card"):
                # Icon only
                mode = QtGui.QIcon.Mode.Normal
                if not (
                    option.state & QStyle.StateFlag.State_Enabled  # type: ignore
                ):
                    mode = QtGui.QIcon.Mode.Disabled
                elif option.state & QStyle.StateFlag.State_Sunken:  # type: ignore
                    mode = QtGui.QIcon.Mode.Active

                checkable = widget.isCheckable() if widget else False

                icon_state = (
                    (
                        QtGui.QIcon.State.On
                        if wstate == "hover"
                        else QtGui.QIcon.State.Off
                    )
                    if not checkable
                    else (
                        QtGui.QIcon.State.On
                        if option.state & QStyle.StateFlag.State_On
                        else QtGui.QIcon.State.Off
                    )
                )

                _icon_align = (
                    (label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask)
                    | Qt.AlignmentFlag.AlignVCenter
                    if label_alignment is not None
                    else Qt.AlignmentFlag.AlignCenter
                )
                option.icon.paint(  # type: ignore
                    painter,
                    content_rect,
                    _icon_align,
                    mode,
                    icon_state,
                )
        else:
            # Text only
            if option.text and not style.get("ignore-text", False):  # type: ignore
                _text_align = (
                    (label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask)
                    | Qt.AlignmentFlag.AlignVCenter
                    if label_alignment is not None
                    else Qt.AlignmentFlag.AlignCenter
                )
                painter.drawText(
                    content_rect,
                    _text_align,
                    option.text,  # type: ignore
                )

        painter.restore()

    def calculate_push_button_size(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QtCore.QSize,
        widget: QWidget | None,
    ) -> QtCore.QSize:
        """Calculate minimum size for push buttons with text, icons,
        and proper padding."""

        if not isinstance(option, QStyleOptionButton):
            # Fallback to parent if we don't have proper option data
            if option is not None:
                return self._super.sizeFromContents(
                    contents_type,
                    option,
                    contents_size,
                    widget,
                )
            else:
                # Return reasonable default for button if no option
                return QtCore.QSize(100, 30)

        # Set up font for text measurement
        style, _ = self.get_button_style(widget, option.state)  # type: ignore
        font = widget.font() if widget else style_font(style, widget)

        # Create font metrics for accurate text measurement
        font_metrics = QFontMetrics(font)

        # Determine if button has icon
        has_icon = (
            self.get_button_has_icon(widget)
            if widget
            else not option.icon.isNull()  # type: ignore
        )
        has_icon = not option.icon.isNull()

        # Determine appropriate padding
        if has_icon and not option.text:  # type: ignore
            # Icon-only button
            padding = style["icon-padding"]
        else:
            # Text button or icon+text button
            padding = style["text-padding"]

        # Calculate text dimensions
        text_width = 0
        text_height = 0
        if option.text and not style.get("ignore-text", False):  # type: ignore
            text_rect = font_metrics.boundingRect(option.text)  # type: ignore
            text_width = text_rect.width()
            text_height = text_rect.height()

        # Calculate icon dimensions
        icon_width = 0
        icon_height = 0
        if has_icon:
            icon_size = option.iconSize  # type: ignore
            icon_width = icon_size.width()
            icon_height = icon_size.height()

        # Calculate content dimensions
        content_width = 0
        content_height = 0

        if has_icon and option.text:  # type: ignore
            # Icon + text: icon on left, 4px spacing, then text
            content_width = icon_width + 4 + text_width
            content_height = max(icon_height, text_height)
        elif has_icon:
            # Icon only
            content_width = icon_width
            content_height = icon_height
        elif option.text:  # type: ignore
            # Text only
            content_width = text_width
            content_height = text_height

        # Add padding (vertical, horizontal)
        total_width = content_width + (
            2 * padding[1]
        )  # horizontal padding on both sides
        total_height = content_height + (
            2 * padding[0]
        )  # vertical padding on top and bottom

        # Ensure minimum button size (reasonable minimums)
        min_width = 16
        min_height = 16

        total_width = max(total_width, min_width)
        total_height = max(total_height, min_height)

        return QtCore.QSize(total_width, total_height)

    def sub_element_rect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget,
    ):
        if element == QStyle.SubElement.SE_PushButtonContents:
            style = self.model.get_style(
                "QPushButton", self.get_button_variant(widget)
            )
            style.set_context(widget)
            if option.icon:
                padding = (
                    style["icon-padding"]
                    if not widget.text()  # type: ignore
                    else style["text-padding"]
                )
            else:
                padding = style["text-padding"]

            return option.rect.adjusted(  # type: ignore
                padding[1], padding[0], -padding[1], -padding[0]
            )

        elif element == QStyle.SubElement.SE_PushButtonFocusRect:
            return option.rect.adjusted(-2, -2, 2, 2)  # type: ignore

        raise ValueError(f"Nothing returned ! -> {element}")
