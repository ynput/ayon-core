from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qtmaterialsymbols import get_icon
from qtpy.QtCore import (
    QRect,
    Qt,
)
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
)
from qtpy.QtWidgets import (
    QHeaderView,
    QWidget,
)

from ..style_types import StyleData
from .style_mixin import StyleMixin
from .table_model import PaginatedTableModel


@dataclass
class AYHeaderStyleOption:
    color: QColor
    bg_color: QColor
    border_color: QColor
    border_width: int
    padding: tuple[int, int]
    sort_indicator_icon: str | None
    sort_indicator_color: QColor
    sort_indicator_icon_size: int

    @classmethod
    def from_style(cls, style_dict: dict[str, Any]) -> AYHeaderStyleOption:
        """Create a AYHeaderStyleOption instance from a style dictionary.

        Args:
            style_dict: Dictionary containing style properties.

        """
        padding = style_dict.get("padding", [4, 8])
        v_pad = h_pad = int(padding[0])
        if len(padding) > 1:
            h_pad = int(padding[1])
        return cls(
            color=QColor(style_dict.get("color", "#c1c7ce")),
            bg_color=QColor(style_dict.get("background-color", "#272d35")),
            border_color=QColor(style_dict.get("border-color", "#41474d")),
            border_width=style_dict.get("border-width", 1),
            padding=(v_pad, h_pad),
            sort_indicator_icon=style_dict.get("sort-indicator-icon"),
            sort_indicator_color=QColor(
                style_dict.get("sort-indicator-color", "#ffffff")
            ),
            sort_indicator_icon_size=style_dict.get(
                "sort-indicator-size", 16
            ),
        )


class AYHeaderView(StyleMixin, QHeaderView):
    def __init__(
        self,
        orientation: Qt.Orientation,
        parent: QWidget | None = None,
        style_model: StyleData | None = None,
        variant: str = "default",
    ) -> None:
        super().__init__(orientation, parent)
        self._style_model = style_model
        self._variant_str = variant
        # Keys of columns the user has flagged as *pinned* (kept at the
        # left in the visual order).  Phase 1 only roundtrips this set;
        # visual freeze rendering is added in Phase 3.
        self._pinned_keys: set[str] = set()

        # Set default height
        header_style = self._style_model.get_style(
            "AYHeaderView", self._variant_str
        )
        height = header_style.get("height", 36)
        self.setFixedHeight(height)

    def pinned_keys(self) -> set[str]:
        """Return a copy of the set of pinned column keys.

        Returns:
            A new ``set[str]`` so callers can mutate the result freely.
        """
        return set(self._pinned_keys)

    def set_pinned_keys(self, keys: set[str]) -> None:
        """Replace the set of pinned column keys.

        Args:
            keys: New set of pinned keys.  A defensive copy is taken.
        """
        self._pinned_keys = set(keys)

    def paintSection(
        self,
        painter: QPainter,
        rect: QRect,
        logical_index: int,
    ) -> None:
        """Paint a single header section directly with QPainter.

        Falls back to the base implementation when no style model is
        available.

        Args:
            painter: The painter to draw with.
            rect: The bounding rectangle for this section.
            logical_index: The logical index of the section.
        """
        if self._style_model is None:
            super().paintSection(painter, rect, logical_index)
            return

        header_style = self._style_model.get_style(
            "AYHeaderView", self._variant_str
        )
        option = AYHeaderStyleOption.from_style(header_style)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipRect(rect)

        # Draw cell background and border
        painter.setBrush(QBrush(option.bg_color))
        painter.setPen(
            QPen(option.border_color, option.border_width)
        )
        painter.drawRect(rect)

        # Label text
        font = self.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setPen(option.color)
        painter.setFont(font)

        model = self.model()
        if model is not None:
            label = model.headerData(
                logical_index,
                self.orientation(),
                Qt.ItemDataRole.DisplayRole,
            )
            if label is not None:
                content_rect = self._get_content_rect(rect, option)
                painter.drawText(
                    content_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    str(label),
                )

        # Sort indicator
        if (
            self.isSortIndicatorShown()
            and self.sortIndicatorSection() == logical_index
        ):
            self._paint_sort_indicator(
                painter,
                rect,
                logical_index,
                option
            )

        painter.restore()

    def _get_content_rect(
        self, rect: QRect, option: AYHeaderStyleOption
    ) -> QRect:
        v_pad, h_pad = option.padding
        return rect.adjusted(h_pad, v_pad, -h_pad, -v_pad)

    def _paint_sort_indicator(
        self,
        painter: QPainter,
        rect: QRect,
        logical_index: int,
        option: AYHeaderStyleOption,
    ) -> None:
        content_rect = self._get_content_rect(rect, option)
        is_sortable = True
        model = self.model()
        if (
            isinstance(model, PaginatedTableModel)
            and 0 <= logical_index < len(model.columns)
        ):
            is_sortable = model.columns[logical_index].sortable

        if not is_sortable:
            painter.restore()
            return

        _v_pad, h_pad = option.padding
        order = self.sortIndicatorOrder()
        icon_name = option.sort_indicator_icon
        if not icon_name:
            arrow = "▲" if order == Qt.SortOrder.AscendingOrder else "▼"
            painter.drawText(
                content_rect,
                Qt.AlignmentFlag.AlignVCenter
                | Qt.AlignmentFlag.AlignRight,
                arrow,
            )
            return

        icon = get_icon(
            icon_name,
            color=option.sort_indicator_color,
        )
        size = option.sort_indicator_icon_size
        margin = int((rect.height() - size) * 0.5)
        pixmap = icon.pixmap(size, size)
        target = rect.adjusted(
            max(rect.width() - (size + h_pad), 0),
            margin,
            -h_pad,
            -margin,
        )

        if order == Qt.SortOrder.AscendingOrder:
            painter.save()
            center = target.center()
            painter.translate(center)
            painter.rotate(180)
            painter.translate(-center)
            painter.drawPixmap(target, pixmap)
            painter.restore()
        else:
            painter.drawPixmap(target, pixmap)
