from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon

from .model import VERSION_LABEL_ROLE, CONTAINER_VERSION_LOCKED_ROLE


class VersionDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""
    _locked_icon = None

    def paint(self, painter, option, index):
        fg_color = index.data(QtCore.Qt.ForegroundRole)
        if fg_color:
            if isinstance(fg_color, QtGui.QBrush):
                fg_color = fg_color.color()
            elif isinstance(fg_color, QtGui.QColor):
                pass
            else:
                fg_color = None

        if not fg_color:
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

        text = index.data(VERSION_LABEL_ROLE)
        pen = painter.pen()
        pen.setColor(fg_color)
        painter.setPen(pen)

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

        painter.drawText(
            text_rect_f,
            option.displayAlignment,
            text
        )
        if index.data(CONTAINER_VERSION_LOCKED_ROLE) is True:
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
            cls._locked_icon = get_qt_icon({
                "type": "material-symbols",
                "name": "lock",
                "color": "white",
            })
        return cls._locked_icon
