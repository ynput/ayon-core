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

from packaging.version import parse
from typing import Dict, Optional, Union

from qtpy import QtCore, QtGui, QtWidgets, QT_VERSION

from .structures import IconOptions, Position
from .utils import get_char_mapping, _get_font_name_filled, _get_font_name


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

    def __init__(self):
        qt_version = parse(QT_VERSION)
        self._use_path = parse("6.0") < qt_version < parse("6.6")
        self._glyph_path_cache = {}

    def paint(self, iconic, painter, rect, mode, state, options):
        """Main paint method."""
        self._paint_icon(iconic, painter, rect, mode, state, options)

    def _paint_icon(self, iconic, painter, rect, mode, state, options):
        """Paint a single icon."""
        painter.save()
        painter.setClipRect(rect)

        color = options.get_color_for_state(state, mode)
        char = options.get_char_for_state(state, mode)

        draw_size = round(rect.height() * options.scale_factor)

        font = iconic.get_font(
            draw_size,
            options.get_fill_for_state(state, mode)
        )

        if options.offset is not None:
            rect = QtCore.QRect(rect)
            rect.translate(
                round(options.offset.x * rect.width()),
                round(options.offset.y * rect.height())
            )

        scale_x = -1 if options.hflip else 1
        scale_y = -1 if options.vflip else 1

        if options.vflip or options.hflip or options.rotate:
            center = rect.center()
            painter.translate(center)

            transfrom = QtGui.QTransform()
            transfrom.scale(scale_x, scale_y)
            painter.setTransform(transfrom, True)

            if options.rotate:
                painter.rotate(options.rotate)
            painter.translate(-center)

        painter.setOpacity(options.opacity)

        if self._use_path:
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            path = self._get_glyph_path(font, char)
            if not path.isEmpty():
                metrics = QtGui.QFontMetricsF(font)
                bounds = metrics.boundingRect(rect, QtCore.Qt.AlignCenter, char)

                # Bounds width returns zero in Qt 6.5.4 (in e.g. Silhouette)
                offset_x = bounds.x()
                if bounds.width() == 0:
                    pixel_size = font.pixelSize()
                    offset_x = rect.x() + ((rect.width() - pixel_size) // 2)
                painter.translate(
                    offset_x, bounds.bottom() - metrics.descent()
                )
                painter.fillPath(path, QtGui.QColor(color))
        else:
            painter.setFont(font)
            painter.setPen(QtGui.QColor(color))
            painter.drawText(rect, QtCore.Qt.AlignCenter, char)

        painter.restore()

    def _get_glyph_path(
        self, font: QtGui.QFont, char: str
    ) -> QtGui.QPainterPath:
        """Get the outline path for a single glyph.

        Args:
            font (QtGui.QFont): The font to use for the glyph.
            char (str): The character to get the path for.

        """
        if not char:
            return QtGui.QPainterPath()

        cache_key = (font.family(), font.pixelSize(), char)
        path = self._glyph_path_cache.get(cache_key)
        if path is not None:
            return path

        raw_font = QtGui.QRawFont.fromFont(font)
        if not raw_font.isValid():
            return QtGui.QPainterPath()

        glyph_indexes = raw_font.glyphIndexesForString(char)
        glyph_index = next(iter(glyph_indexes), None)
        if glyph_index is None:
            return QtGui.QPainterPath()
        path = raw_font.pathForGlyph(glyph_index)
        self._glyph_path_cache[cache_key] = path
        return path


class CharIconEngine(QtGui.QIconEngine):
    """Specialization of QIconEngine used to draw font-based icons."""

    def __init__(
        self,
        iconic: "IconicFont",
        painter: QtGui.QPainter,
        options: IconOptions
    ):
        super().__init__()
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

    def get_font(self, size: int, filled: bool) -> QtGui.QFont:
        """Return a QFont corresponding to the given size."""
        if filled:
            font = QtGui.QFont(_get_font_name_filled())
        else:
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
        hflip: bool = False,
        vflip: bool = False,
        rotate: int = 0,
        fill: bool = True,
        **kwargs
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
            fill=fill,
            **kwargs
        )
        cache_key = options.identifier
        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]
        return self.get_icon_with_options(options)

    def _icon_by_painter(self, painter, options):
        """Return the icon corresponding to the given painter."""
        engine = CharIconEngine(self, painter, options)
        return QtGui.QIcon(engine)
