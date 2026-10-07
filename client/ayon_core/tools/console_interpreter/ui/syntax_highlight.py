from __future__ import annotations

import os

from qtpy import QtGui
import pygments.lexers
import pygments.styles
import pygments.token
from pygments.util import ClassNotFound

from .code_style import AYONCodeStyle


class PythonSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document, style_name: str = ""):
        self.lexer = pygments.lexers.PythonLexer()
        self.style = AYONCodeStyle

        # Allow to override style by environment variable
        override_style_name = os.getenv("AYON_CONSOLE_INTERPRETER_STYLE")
        if override_style_name:

            try:
                style = pygments.styles.get_style_by_name(override_style_name)
            except ClassNotFound:
                all_styles = ", ".join(pygments.styles.get_all_styles())
                raise ValueError(
                    f"'{override_style_name}' not found. "
                    f"Installed styles: {all_styles}."
                )
            else:
                self.style = style

        self.formats = self.style_to_formats(self.style)

        # init after validating and loading the style
        super().__init__(document)

    def highlightBlock(self, text: str | None) -> None:
        if text is None:
            return

        index = 0
        for token, value in self.lexer.get_tokens(text):
            length = len(value)
            if fmt := self.formats.get(token):
                self.setFormat(index, length, fmt)

            index += length

    def _format_for_token(self, token):
        if token is None:
            return None
        if token in self.formats:
            return self.formats[token]
        if token.parent:
            return self._format_for_token(token.parent)
        return None

    def style_to_formats(
        self,
        style: pygments.styles.Style
    ) -> dict[pygments.token.Token, QtGui.QTextCharFormat]:
        """Convert a Pygments style to a dictionary of Qt formats.

        Args:
            style: The Pygments style to convert.

        Returns:
            token_format = QTextCharFormat for each token in the style.

        """
        formats = {}
        for token, _ in style.styles.items():

            token_style = style.style_for_token(token)
            if not token_style:
                continue

            token_format = QtGui.QTextCharFormat()
            if color := token_style.get("color"):
                color = f"#{color}"
                token_format.setForeground(QtGui.QColor(color))
            if token_style.get("bold"):
                token_format.setFontWeight(QtGui.QFont.Bold)
            if token_style.get("italic"):
                token_format.setFontItalic(True)
            if token_style.get("underline"):
                token_format.setFontUnderline(True)

            formats[token] = token_format

        return formats
