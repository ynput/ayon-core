from qtpy import QtWidgets, QtCore, QtGui

from .model import VERSION_LABEL_ROLE


class VersionDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""
    def paint(self, painter, option, index):
        fg_color = index.data(QtCore.Qt.ForegroundRole)
        if fg_color:
            if isinstance(fg_color, QtGui.QBrush):
                fg_color = fg_color.color()
            elif isinstance(fg_color, QtGui.QColor):
                pass
            else:
                fg_color = None

        icon_data = index.data(QtCore.Qt.DecorationRole)
        if icon_data is not None:
            mode = QtGui.QIcon.Normal
            option.decorationSize = QtCore.QSize(16, 16)
            r = QtCore.QRect(QtCore.QPoint(), option.decorationSize)
            r.moveCenter(option.rect.center())
            r.setRight(option.rect.right() - 3)
            state = QtGui.QIcon.On if option.state & QtWidgets.QStyle.State_Open else QtGui.QIcon.Off
            icon_data.paint(painter, r, QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, mode, state)

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

        painter.drawText(
            text_rect.adjusted(text_margin, 0, - text_margin, 0),
            option.displayAlignment,
            text
        )

        painter.restore()
