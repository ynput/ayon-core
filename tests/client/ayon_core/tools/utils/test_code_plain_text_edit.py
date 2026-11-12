"""Tests for 'CodePlainTextEdit' and the 'TextDef' syntax in UI."""
from __future__ import annotations

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib.attribute_definitions import TextDef
from ayon_core.tools.attribute_defs.widgets import TextAttrWidget
from ayon_core.tools.utils import (
    CodePlainTextEdit,
    PlaceholderPlainTextEdit,
)
from ayon_core.tools.utils.syntax_highlight import (
    SyntaxHighlighter,
    create_syntax_highlighter,
)


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


def _press(widget, key, modifiers=QtCore.Qt.NoModifier):
    event = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)
    widget.keyPressEvent(event)


def test_create_syntax_highlighter(qapp):
    document = QtGui.QTextDocument()
    highlighter = create_syntax_highlighter(document, "python")
    assert isinstance(highlighter, SyntaxHighlighter)


def test_create_syntax_highlighter_unknown_syntax(qapp):
    document = QtGui.QTextDocument()
    assert create_syntax_highlighter(document, "not-a-syntax") is None


def test_set_syntax(qapp):
    widget = CodePlainTextEdit()
    assert widget.set_syntax("python")
    assert not widget.set_syntax("not-a-syntax")
    assert not widget.set_syntax(None)


def test_tab_indents_with_spaces(qapp):
    widget = CodePlainTextEdit(syntax="python")
    _press(widget, QtCore.Qt.Key_Tab)
    assert widget.toPlainText() == " " * CodePlainTextEdit.indent


def test_backtab_unindents_line(qapp):
    widget = CodePlainTextEdit()
    widget.setPlainText("        print()")
    _press(widget, QtCore.Qt.Key_Backtab, QtCore.Qt.ShiftModifier)
    assert widget.toPlainText() == "    print()"


def test_text_attr_widget_uses_code_edit_with_syntax(qapp):
    attr_def = TextDef(
        "script", multiline=True, syntax="python", default="print()"
    )
    widget = TextAttrWidget(attr_def, None)
    assert isinstance(widget._input_widget, CodePlainTextEdit)
    assert widget.current_value() == "print()"


def test_text_attr_widget_without_syntax(qapp):
    widget = TextAttrWidget(TextDef("script", multiline=True), None)
    input_widget = widget._input_widget
    assert isinstance(input_widget, PlaceholderPlainTextEdit)
    assert not isinstance(input_widget, CodePlainTextEdit)
