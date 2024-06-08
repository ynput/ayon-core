r"""

Iconic Font
===========

A lightweight module handling iconic fonts.

It is designed to provide a simple way for creating QIcons from glyphs.

From a user's viewpoint, the main entry point is the ``IconicFont`` class which
contains methods for loading new iconic fonts with their character map and
methods returning instances of ``QIcon``.

"""
import warnings

from typing import Dict, Optional, Union

from qtpy import QtCore, QtGui, QtWidgets

from .structures import IconOptions, Position
from .utils import get_char_mapping, get_icon_name_char, _get_font_name


class _Cache:
    instance = None


def get_instance():
    if _Cache.instance is None:
        _Cache.instance = IconicFont()
    return _Cache.instance


def get_icon(*args, **kwargs):
    return get_instance().get_icon(*args, **kwargs)


class CharIconPainter:
    """Char icon painter."""
    def paint(self, iconic, painter, rect, mode, state, options):
        """Main paint method."""
        self._paint_icon(iconic, painter, rect, mode, state, options)

    def _paint_icon(self, iconic, painter, rect, mode, state, options):
        """Paint a single icon."""
        painter.save()

        color = options.get_color_for_state(state, mode)
        char = options.get_char_for_state(state, mode)

        painter.setPen(QtGui.QColor(color))

        # A 16 pixel-high icon yields a font size of 14, which is pixel perfect
        # for font-awesome. 16 * 0.875 = 14
        # The reason why the glyph size is smaller than the icon size is to
        # account for font bearing.
        # draw_size = round(0.875 * rect.height() * options.scale_factor)

        draw_size = round(rect.height() * options.scale_factor)

        painter.setFont(iconic.get_font(draw_size))
        if options.offset is not None:
            rect = QtCore.QRect(rect)
            rect.translate(
                round(options.offset.x * rect.width()),
                round(options.offset.y * rect.height())
            )

        scale_x = -1 if options.hflip else 1
        scale_y = -1 if options.vflip else 1

        if options.vflip or options.hflip or options.rotate:
            x_center = rect.width() * 0.5
            y_center = rect.height() * 0.5
            painter.translate(x_center, y_center)

            transfrom = QtGui.QTransform()
            transfrom.scale(scale_x, scale_y)
            painter.setTransform(transfrom, True)

            if options.rotate:
                painter.rotate(options.rotate)
            painter.translate(-x_center, -y_center)

        painter.setOpacity(options.opacity)

        painter.drawText(rect, QtCore.Qt.AlignCenter, char)
        painter.restore()


class CharIconEngine(QtGui.QIconEngine):
    """Specialization of QIconEngine used to draw font-based icons."""

    def __init__(
        self,
        iconic: "IconicFont",
        painter: QtGui.QPainter,
        options: IconOptions
    ):
        super(CharIconEngine, self).__init__()
        self._iconic = iconic
        self._painter = painter
        self._options = options

    def paint(self, painter, rect, mode, state):
        self._painter.paint(
            self._iconic,
            painter,
            rect,
            mode,
            state,
            self._options
        )

    def pixmap(self, size, mode, state):
        pm = QtGui.QPixmap(size)
        pm.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(pm)
        self.paint(
            painter,
            QtCore.QRect(QtCore.QPoint(0, 0), size),
            mode,
            state
        )
        return pm


class IconicFont(QtCore.QObject):
    """Main class for managing icons."""

    def __init__(self):
        super().__init__()
        self._painter = CharIconPainter()
        self._icon_cache = {}

    def get_charmap(self) -> Dict[str, int]:
        return get_char_mapping()

    def get_font(self, size: int) -> QtGui.QFont:
        """Return a QFont corresponding to the given size."""
        font = QtGui.QFont(_get_font_name())
        font.setPixelSize(round(size))
        return font

    def get_icon_with_options(self, options: IconOptions) -> QtGui.QIcon:
        """Return a QIcon object corresponding to the provided icon name."""
        if QtWidgets.QApplication.instance() is None:
            warnings.warn(
                "You need to have a running QApplication!"
            )
            return QtGui.QIcon()

        cache_key = options.identifier
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        output = self._icon_by_painter(self._painter, options)
        self._icon_cache[cache_key] = output
        return output

    def get_icon(
        self,
        icon_name: Optional[str] = None,
        color: Optional[Union[QtGui.QColor, str]] = None,
        opacity: Optional[float] = None,
        scale_factor: Optional[float] = None,
        offset: Optional[Position] = None,
        hflip: Optional[bool] = False,
        vflip: Optional[bool] = False,
        rotate: Optional[int] = 0,
        icon_name_normal: Optional[str] = None,
        icon_name_active: Optional[str] = None,
        icon_name_selected: Optional[str] = None,
        icon_name_disabled: Optional[str] = None,
        icon_name_on: Optional[str] = None,
        icon_name_off: Optional[str] = None,
        icon_name_on_normal: Optional[str] = None,
        icon_name_off_normal: Optional[str] = None,
        icon_name_on_active: Optional[str] = None,
        icon_name_off_active: Optional[str] = None,
        icon_name_on_selected: Optional[str] = None,
        icon_name_off_selected: Optional[str] = None,
        icon_name_on_disabled: Optional[str] = None,
        icon_name_off_disabled: Optional[str] = None,
        color_normal: Optional[Union[QtGui.QColor, str]] = None,
        color_active: Optional[Union[QtGui.QColor, str]] = None,
        color_selected: Optional[Union[QtGui.QColor, str]] = None,
        color_disabled: Optional[Union[QtGui.QColor, str]] = None,
        color_on: Optional[Union[QtGui.QColor, str]] = None,
        color_off: Optional[Union[QtGui.QColor, str]] = None,
        color_on_normal: Optional[Union[QtGui.QColor, str]] = None,
        color_off_normal: Optional[Union[QtGui.QColor, str]] = None,
        color_on_active: Optional[Union[QtGui.QColor, str]] = None,
        color_off_active: Optional[Union[QtGui.QColor, str]] = None,
        color_on_selected: Optional[Union[QtGui.QColor, str]] = None,
        color_off_selected: Optional[Union[QtGui.QColor, str]] = None,
        color_on_disabled: Optional[Union[QtGui.QColor, str]] = None,
        color_off_disabled: Optional[Union[QtGui.QColor, str]] = None,
    ) -> QtGui.QIcon:
        """Return a QIcon object corresponding to the provided icon name."""
        if QtWidgets.QApplication.instance() is None:
            warnings.warn(
                "You need to have a running QApplication!"
            )
            return QtGui.QIcon()

        options = IconOptions.from_data(
            icon_name=icon_name,
            color=color,
            opacity=opacity,
            scale_factor=scale_factor,
            offset=offset,
            hflip=hflip,
            vflip=vflip,
            rotate=rotate,
            icon_name_normal=icon_name_normal,
            icon_name_active=icon_name_active,
            icon_name_selected=icon_name_selected,
            icon_name_disabled=icon_name_disabled,
            icon_name_on=icon_name_on,
            icon_name_off=icon_name_off,
            icon_name_on_normal=icon_name_on_normal,
            icon_name_off_normal=icon_name_off_normal,
            icon_name_on_active=icon_name_on_active,
            icon_name_off_active=icon_name_off_active,
            icon_name_on_selected=icon_name_on_selected,
            icon_name_off_selected=icon_name_off_selected,
            icon_name_on_disabled=icon_name_on_disabled,
            icon_name_off_disabled=icon_name_off_disabled,
            color_normal=color_normal,
            color_active=color_active,
            color_selected=color_selected,
            color_disabled=color_disabled,
            color_on=color_on,
            color_off=color_off,
            color_on_normal=color_on_normal,
            color_off_normal=color_off_normal,
            color_on_active=color_on_active,
            color_off_active=color_off_active,
            color_on_selected=color_on_selected,
            color_off_selected=color_off_selected,
            color_on_disabled=color_on_disabled,
            color_off_disabled=color_off_disabled,
        )
        cache_key = options.identifier
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        return self.get_icon_with_options(options)

    def _icon_by_painter(self, painter, options):
        """Return the icon corresponding to the given painter."""
        engine = CharIconEngine(self, painter, options)
        return QtGui.QIcon(engine)
