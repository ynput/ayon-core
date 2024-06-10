import time
from datetime import datetime
import logging

from qtpy import QtWidgets, QtGui, QtCore

log = logging.getLogger(__name__)


def pretty_date(t, now=None, strftime="%b %d %Y %H:%M"):
    """Parse datetime to readable timestamp

    Within first ten seconds:
        - "just now",
    Within first minute ago:
        - "%S seconds ago"
    Within one hour ago:
        - "%M minutes ago".
    Within one day ago:
        - "%H:%M hours ago"
    Else:
        "%Y-%m-%d %H:%M:%S"

    """

    assert isinstance(t, datetime)
    if now is None:
        now = datetime.now()
    assert isinstance(now, datetime)
    diff = now - t

    second_diff = diff.seconds
    day_diff = diff.days

    # future (consider as just now)
    if day_diff < 0:
        return "just now"

    # history
    if day_diff == 0:
        if second_diff < 10:
            return "just now"
        if second_diff < 60:
            return str(second_diff) + " seconds ago"
        if second_diff < 120:
            return "a minute ago"
        if second_diff < 3600:
            return str(second_diff // 60) + " minutes ago"
        if second_diff < 86400:
            minutes = (second_diff % 3600) // 60
            hours = second_diff // 3600
            return "{0}:{1:02d} hours ago".format(hours, minutes)

    return t.strftime(strftime)


def pretty_timestamp(t, now=None):
    """Parse timestamp to user readable format

    >>> pretty_timestamp("20170614T151122Z", now="20170614T151123Z")
    'just now'

    >>> pretty_timestamp("20170614T151122Z", now="20170614T171222Z")
    '2:01 hours ago'

    Args:
        t (str): The time string to parse.
        now (str, optional)

    Returns:
        str: human readable "recent" date.

    """

    if now is not None:
        try:
            now = time.strptime(now, "%Y%m%dT%H%M%SZ")
            now = datetime.fromtimestamp(time.mktime(now))
        except ValueError as e:
            log.warning("Can't parse 'now' time format: {0} {1}".format(t, e))
            return None

    if isinstance(t, float):
        dt = datetime.fromtimestamp(t)
    else:
        # Parse the time format as if it is `str` result from
        # `pyblish.lib.time()` which usually is stored in Avalon database.
        try:
            t = time.strptime(t, "%Y%m%dT%H%M%SZ")
        except ValueError as e:
            log.warning("Can't parse time format: {0} {1}".format(t, e))
            return None
        dt = datetime.fromtimestamp(time.mktime(t))

    # prettify
    return pretty_date(dt, now=now)


class PrettyTimeDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that displays a timestamp as a pretty date.

    This displays dates like `pretty_date`.

    """

    def displayText(self, value, locale):
        if value is not None:
            return pretty_timestamp(value)


class StatusDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate showing status name and short name."""
    def __init__(
        self,
        status_name_role,
        status_short_name_role,
        status_color_role,
        status_icon_role,
        *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.status_name_role = status_name_role
        self.status_short_name_role = status_short_name_role
        self.status_color_role = status_color_role
        self.status_icon_role = status_icon_role

    def paint(self, painter, option, index):
        if option.widget:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()

        self.initStyleOption(option, index)

        mode = QtGui.QIcon.Normal
        if not (option.state & QtWidgets.QStyle.State_Enabled):
            mode = QtGui.QIcon.Disabled
        elif option.state & QtWidgets.QStyle.State_Selected:
            mode = QtGui.QIcon.Selected
        state = QtGui.QIcon.Off
        if option.state & QtWidgets.QStyle.State_Open:
            state = QtGui.QIcon.On
        icon = self._get_status_icon(index)
        option.features |= QtWidgets.QStyleOptionViewItem.HasDecoration
        option.icon = icon
        act_size = icon.actualSize(option.decorationSize, mode, state)
        option.decorationSize = QtCore.QSize(
            min(option.decorationSize.width(), act_size.width()),
            min(option.decorationSize.height(), act_size.height())
        )

        text = self._get_status_name(index)
        if text:
            option.features |= QtWidgets.QStyleOptionViewItem.HasDisplay
            option.text = text

        painter.save()
        painter.setClipRect(option.rect)

        icon_rect = style.subElementRect(
            QtWidgets.QCommonStyle.SE_ItemViewItemDecoration,
            option,
            option.widget
        )
        text_rect = style.subElementRect(
            QtWidgets.QCommonStyle.SE_ItemViewItemText,
            option,
            option.widget
        )

        # Draw background
        style.drawPrimitive(
            QtWidgets.QCommonStyle.PE_PanelItemViewItem,
            option,
            painter,
            option.widget
        )

        # Draw icon
        option.icon.paint(
            painter,
            icon_rect,
            option.decorationAlignment,
            mode,
            state
        )
        fm = QtGui.QFontMetrics(option.font)
        if text_rect.width() < fm.width(text):
            text = self._get_status_short_name(index)
            if text_rect.width() < fm.width(text):
                text = ""

        fg_color = self._get_status_color(index)
        pen = painter.pen()
        pen.setColor(fg_color)
        painter.setPen(pen)

        painter.drawText(
            text_rect,
            option.displayAlignment,
            text
        )

        if option.state & QtWidgets.QStyle.State_HasFocus:
            focus_opt = QtWidgets.QStyleOptionFocusRect()
            focus_opt.state = option.state
            focus_opt.direction = option.direction
            focus_opt.rect = option.rect
            focus_opt.fontMetrics = option.fontMetrics
            focus_opt.palette = option.palette

            focus_opt.rect = style.subElementRect(
                QtWidgets.QCommonStyle.SE_ItemViewItemFocusRect,
                option,
                option.widget
            )
            focus_opt.state |= (
                QtWidgets.QStyle.State_KeyboardFocusChange
                | QtWidgets.QStyle.State_Item
            )
            focus_opt.backgroundColor = option.palette.color(
                (
                    QtGui.QPalette.Normal
                    if option.state & QtWidgets.QStyle.State_Enabled
                    else QtGui.QPalette.Disabled
                ),
                (
                    QtGui.QPalette.Highlight
                    if option.state & QtWidgets.QStyle.State_Selected
                    else QtGui.QPalette.Window
                )
            )
            style.drawPrimitive(
                QtWidgets.QCommonStyle.PE_FrameFocusRect,
                focus_opt,
                painter,
                option.widget
            )

        painter.restore()

    def _get_status_name(self, index):
        return index.data(self.status_name_role)

    def _get_status_short_name(self, index):
        return index.data(self.status_short_name_role)

    def _get_status_color(self, index):
        return QtGui.QColor(index.data(self.status_color_role))

    def _get_status_icon(self, index):
        icon = None
        if self.status_icon_role is not None:
            icon = index.data(self.status_icon_role)
        if icon is None:
            return QtGui.QIcon()
        return icon
