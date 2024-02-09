# TODO remove - kept for kitsu addon which imported it
from qtpy import QtWidgets, QtCore, QtGui


class PressHoverButton(QtWidgets.QPushButton):
    """
    Deprecated:
        Use `openpype.tools.utils.PressHoverButton` instead.
    """
    _mouse_pressed = False
    _mouse_hovered = False
    change_state = QtCore.Signal(bool)

    def mousePressEvent(self, event):
        self._mouse_pressed = True
        self._mouse_hovered = True
        self.change_state.emit(self._mouse_hovered)
        super(PressHoverButton, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._mouse_pressed = False
        self._mouse_hovered = False
        self.change_state.emit(self._mouse_hovered)
        super(PressHoverButton, self).mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        under_mouse = self.rect().contains(mouse_pos)
        if under_mouse != self._mouse_hovered:
            self._mouse_hovered = under_mouse
            self.change_state.emit(self._mouse_hovered)

        super(PressHoverButton, self).mouseMoveEvent(event)
