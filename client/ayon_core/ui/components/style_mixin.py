from __future__ import annotations

from qtpy.QtGui import QFont, QFontMetrics, QPalette


class StyleMixin:
    """Mixin class for overriding QWidget's font, fontMetrics, and palette methods.

    This mixin provides reliable overrides for style-related methods that should
    return the custom style values instead of the default QWidget values.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_font: QFont = QFont()
        self._style_palette: QPalette = QPalette()

    # Overrides for QWidget methods to return custom style values

    def font(self) -> QFont:
        """Override to return the custom style font."""
        return QFont(self._style_font)

    def fontMetrics(self) -> QFontMetrics:
        """Override to return the custom style font metrics."""
        return QFontMetrics(self._style_font)

    def palette(self) -> QPalette:
        """Override to return the custom style palette."""
        return QPalette(self._style_palette)

    def setFont(self, font: QFont) -> None:
        """Override to set the custom style font."""
        if hasattr(super(), "set_font"):
            super().set_font(font)
        else:
            self._style_font = font
        super().setFont(self._style_font)

    def setPalette(self, palette: QPalette) -> None:
        """Override to set the custom style palette."""
        if hasattr(super(), "set_palette"):
            super().set_palette(palette)
        else:
            self._style_palette = palette
        super().setPalette(self._style_palette)
