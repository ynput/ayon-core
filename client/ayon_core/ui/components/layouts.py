from __future__ import annotations

from typing import Optional

from qtpy import QtWidgets
from qtpy.QtCore import QPoint, QRect, QSize, Qt

from ..utils import clear_layout


class AYHBoxLayout(QtWidgets.QHBoxLayout):
    def __init__(self, *args, margin: int = 4, spacing: int = 4):
        super().__init__(*args)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def clear(self):
        clear_layout(self)


class AYVBoxLayout(QtWidgets.QVBoxLayout):
    def __init__(self, *args, margin: int = 4, spacing: int = 4):
        super().__init__(*args)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def clear(self):
        clear_layout(self)


class AYGridLayout(QtWidgets.QGridLayout):
    def __init__(self, *args, margin: int = 4, spacing: int = 4):
        super().__init__(*args)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def clear(self):
        clear_layout(self)


class AYFlowLayout(QtWidgets.QLayout):
    """Flow layout that wraps widgets horizontally, then vertically.

    This layout arranges widgets in a left-to-right flow, wrapping to the
    next line when the width is exceeded, similar to how text flows in a
    paragraph.
    """

    def __init__(self, parent=None, margin: int = 4, spacing: int = 4):
        super().__init__(parent)
        self._item_list = []
        self._h_spacing = spacing
        self._v_spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        """Add an item to the layout."""
        self._item_list.append(item)

    def horizontalSpacing(self) -> int:
        """Get the horizontal spacing between items."""
        if self._h_spacing >= 0:
            return self._h_spacing
        return self._smart_spacing(QtWidgets.QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self) -> int:
        """Get the vertical spacing between items."""
        if self._v_spacing >= 0:
            return self._v_spacing
        return self._smart_spacing(QtWidgets.QStyle.PM_LayoutVerticalSpacing)

    def count(self) -> int:
        """Return the number of items in the layout."""
        return len(self._item_list)

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        """Get the item at the specified index."""
        if 0 <= index < len(self._item_list):
            return self._item_list[index]
        return None

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:  # type: ignore
        """Remove and return the item at the specified index."""
        if 0 <= index < len(self._item_list):
            return self._item_list.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        """Return the expanding directions for this layout."""
        return Qt.Orientations(0)

    def hasHeightForWidth(self) -> bool:
        """Return True to indicate height depends on width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate the height required for the given width."""
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:
        """Set the geometry of the layout."""
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QSize:
        """Return the preferred size of the layout."""
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        """Calculate and return the minimum size for the layout."""
        size = QSize()
        for item in self._item_list:
            size = size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """Perform the layout calculation and positioning.

        Args:
            rect: The rectangle to lay out items within.
            test_only: If True, only calculate height without setting
                geometry.

        Returns:
            The height required for the layout.
        """
        left, top, right, bottom = (
            self.contentsMargins().left(),
            self.contentsMargins().top(),
            self.contentsMargins().right(),
            self.contentsMargins().bottom(),
        )
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._item_list:
            widget = item.widget()
            space_x = self.horizontalSpacing()
            if space_x == -1:
                space_x = widget.style().layoutSpacing(
                    QtWidgets.QSizePolicy.PushButton,
                    QtWidgets.QSizePolicy.PushButton,
                    Qt.Horizontal,
                )

            space_y = self.verticalSpacing()
            if space_y == -1:
                space_y = widget.style().layoutSpacing(
                    QtWidgets.QSizePolicy.PushButton,
                    QtWidgets.QSizePolicy.PushButton,
                    Qt.Vertical,
                )

            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom

    def _smart_spacing(self, pm: int) -> int:
        """Get smart spacing from the parent widget's style.

        Args:
            pm: The pixel metric to query.

        Returns:
            The spacing value, or -1 if unavailable.
        """
        parent = self.parent()
        if parent is None:
            return -1
        if parent.isWidgetType():
            return parent.style().pixelMetric(pm, None, parent)
        return parent.spacing()

    def clear(self):
        clear_layout(self)


class AYFormLayout(QtWidgets.QFormLayout):
    def __init__(
        self,
        *args,
        margin: int = 4,
        spacing: tuple[int, int] = (4, 4),
    ):
        super().__init__(*args)
        self.setContentsMargins(margin, margin, margin, margin)
        self.setHorizontalSpacing(spacing[0])
        self.setVerticalSpacing(spacing[1])

    def clear(self):
        clear_layout(self)
