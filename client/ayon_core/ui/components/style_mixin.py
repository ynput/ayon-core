from __future__ import annotations

from typing import Sequence

from qtpy.QtCore import Qt
from qtpy.QtGui import QColor, QFont, QFontMetrics, QPalette


class StyleMixin:
    """Mixin class for overriding QWidget's font, fontMetrics, and palette
    methods.

    This mixin provides reliable overrides for style-related methods that should
    return the custom style values instead of the default QWidget values.

    Fonts:
    - `font()` method returns a QFont instance based on the AYON style.
    - `setFont()` does not set the font but propagates our style's font.
    - NOTE: To actually change a widget's font, use / implement the `set_font()`
    method.
    - `fontMetrics()` method returns a QFontMetrics instance based the current
    style font.

    Palettes:
    - `palette()` method returns a QPalette instance based on the AYON style.
    - `setPalette()` does not set the palette but propagates our style's
    palette.
    - NOTE: To actually change a widget's palette, use / implement the
    `set_palette()` method.
    """

    def __init__(self, *args, **kwargs):
        from ..style import get_ayon_style

        super().__init__(*args, **kwargs)

        # Initialize with our style's default font and palette.
        _style = get_ayon_style()
        self._style_font: QFont = _style.model.base_font
        self._style_palette: QPalette = _style.model.base_palette

    def font(self) -> QFont:
        """Override to return our custom style font and circumvent the
        stylesheets."""
        return QFont(self._style_font)

    def fontMetrics(self) -> QFontMetrics:
        """Override to return our custom style font metrics and circumvent the
        stylesheets."""
        return QFontMetrics(self._style_font)

    def palette(self) -> QPalette:
        """Override to return our custom style palette and circumvent the
        stylesheets."""
        return QPalette(self._style_palette)

    def setFont(self, font: QFont | str | Sequence[str]) -> None:
        """Override to prevent the stylesheet from overriding our style's
        font."""
        if hasattr(super(), "setFont"):
            super().setFont(self._style_font)  # type: ignore

    def setPalette(self, palette: QPalette | Qt.GlobalColor | QColor) -> None:
        """Override to prevent the stylesheet from overriding our style's
        palette."""
        if hasattr(super(), "setPalette"):
            super().setPalette(self._style_palette)  # type: ignore

    def set_font(self, font: QFont) -> None:
        """Set the custom style font.
        This is a default implementation that will be superseded by widgets
        that implement their own `set_font()` method."""
        if hasattr(super(), "set_font"):
            super().set_font(font)  # type: ignore
        else:
            self._style_font = font
        self.setFont(self._style_font)

    def set_palette(self, palette: QPalette) -> None:
        """Set the custom style palette.
        This is a default implementation that will be superseded by widgets
        that implement their own `set_palette()` method."""
        if hasattr(super(), "set_palette"):
            super().set_palette(palette)  # type: ignore
        else:
            self._style_palette = palette
        self.setPalette(self._style_palette)
