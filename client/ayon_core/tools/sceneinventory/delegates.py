from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.tools.utils import get_qt_icon

from .model import (
    VERSION_LABEL_ROLE,
    CONTAINER_VERSION_LOCKED_ROLE,
    CONTAINER_VERSION_PARTIALLY_LOCKED,
    InventoryModel,
)


class VersionDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""
    _locked_icon = None
    _partially_locked_icon = None

    def paint(self, painter, option, index):
        fg_color = index.data(QtCore.Qt.ForegroundRole)
        if fg_color:
            if isinstance(fg_color, QtGui.QBrush):
                fg_color = fg_color.color()
            elif isinstance(fg_color, QtGui.QColor):
                pass
            else:
                fg_color = None

        lock_state = index.data(CONTAINER_VERSION_LOCKED_ROLE)

        # Nothing custom to draw over the default rendering.
        if not fg_color and not lock_state:
            return super().paint(painter, option, index)

        if option.widget:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()

        style.drawControl(
            QtWidgets.QStyle.CE_ItemViewItem,
            option,
            painter,
            option.widget
        )

        painter.save()

        text_rect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText,
            option
        )
        text_margin = style.proxy().pixelMetric(
            QtWidgets.QStyle.PM_FocusFrameHMargin, option, option.widget
        ) + 1

        text_rect_f = text_rect.adjusted(
            text_margin, 0, - text_margin, 0
        )

        font = index.data(QtCore.Qt.FontRole)
        if isinstance(font, QtGui.QFont):
            painter.setFont(font)

        if not fg_color:
            role = (
                QtGui.QPalette.HighlightedText
                if option.state & QtWidgets.QStyle.State_Selected
                else QtGui.QPalette.Text
            )
            fg_color = option.palette.color(role)

        pen = painter.pen()
        pen.setColor(fg_color)
        painter.setPen(pen)

        text = index.data(VERSION_LABEL_ROLE)
        painter.drawText(
            text_rect_f,
            option.displayAlignment,
            text
        )

        if lock_state:
            if lock_state == CONTAINER_VERSION_PARTIALLY_LOCKED:
                icon = self._get_partially_locked_icon()
            else:
                icon = self._get_locked_icon()
            size = max(text_rect_f.height() // 2, 16)
            margin = (text_rect_f.height() - size) // 2

            icon_rect = QtCore.QRect(
                text_rect_f.right() - size,
                text_rect_f.top() + margin,
                size,
                size
            )
            icon.paint(painter, icon_rect)

        painter.restore()

    def _get_locked_icon(cls):
        if cls._locked_icon is None:
            cls._locked_icon = get_qt_icon(
                MaterialSymbolsIcon("lock", color="white")
            )
        return cls._locked_icon

    def _get_partially_locked_icon(cls):
        if cls._partially_locked_icon is None:
            cls._partially_locked_icon = get_qt_icon(
                MaterialSymbolsIcon(
                    "lock_open",
                    color=InventoryModel.GRAYOUT_COLOR.name()
                )
            )
        return cls._partially_locked_icon
