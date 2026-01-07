from ayon_core.tools.flickcharm import FlickCharm

from qtpy import QtWidgets, QtCore, QtGui


class DeselectableTreeView(QtWidgets.QTreeView):
    """A tree view that deselects on clicking on an empty area in the view"""

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if not index.isValid():
            # clear the selection
            self.clearSelection()
            # clear the current index
            self.setCurrentIndex(QtCore.QModelIndex())

        elif (
            self.selectionModel().isSelected(index)
            and len(self.selectionModel().selectedRows()) == 1
            and event.modifiers() == QtCore.Qt.NoModifier
        ):
            event.setModifiers(QtCore.Qt.ControlModifier)

        super().mousePressEvent(event)


class TreeView(QtWidgets.QTreeView):
    """Ultimate TreeView with flick charm and double click signals.

    Tree view have deselectable mode, which allows to deselect items by
    clicking on item area without any items.

    Todos:
        Add refresh animation.
    """

    double_clicked = QtCore.Signal(QtGui.QMouseEvent)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deselectable = False

        self._flick_charm_activated = False
        self._flick_charm = FlickCharm(parent=self)
        self._before_flick_scroll_mode = None

    def is_deselectable(self):
        return self._deselectable

    def set_deselectable(self, deselectable):
        self._deselectable = deselectable

    deselectable = property(is_deselectable, set_deselectable)

    def mousePressEvent(self, event):
        if self._deselectable:
            index = self.indexAt(event.pos())
            if not index.isValid():
                # clear the selection
                self.clearSelection()
                # clear the current index
                self.setCurrentIndex(QtCore.QModelIndex())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(event)

        return super().mouseDoubleClickEvent(event)

    def activate_flick_charm(self):
        if self._flick_charm_activated:
            return
        self._flick_charm_activated = True
        self._before_flick_scroll_mode = self.verticalScrollMode()
        self._flick_charm.activateOn(self)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

    def deactivate_flick_charm(self):
        if not self._flick_charm_activated:
            return
        self._flick_charm_activated = False
        self._flick_charm.deactivateFrom(self)
        if self._before_flick_scroll_mode is not None:
            self.setVerticalScrollMode(self._before_flick_scroll_mode)


class ListView(QtWidgets.QListView):
    """A tree view that deselects on clicking on an empty area in the view"""
    double_clicked = QtCore.Signal(QtGui.QMouseEvent)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deselectable = False

        self._flick_charm_activated = False
        self._flick_charm = FlickCharm(parent=self)
        self._before_flick_scroll_mode = None

    def is_deselectable(self):
        return self._deselectable

    def set_deselectable(self, deselectable):
        self._deselectable = deselectable

    deselectable = property(is_deselectable, set_deselectable)

    def mousePressEvent(self, event):
        if self._deselectable:
            index = self.indexAt(event.pos())
            if not index.isValid():
                # clear the selection
                self.clearSelection()
                # clear the current index
                self.setCurrentIndex(QtCore.QModelIndex())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(event)

        return super().mouseDoubleClickEvent(event)

    def activate_flick_charm(self):
        if self._flick_charm_activated:
            return
        self._flick_charm_activated = True
        self._before_flick_scroll_mode = self.verticalScrollMode()
        self._flick_charm.activateOn(self)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

    def deactivate_flick_charm(self):
        if not self._flick_charm_activated:
            return
        self._flick_charm_activated = False
        self._flick_charm.deactivateFrom(self)
        if self._before_flick_scroll_mode is not None:
            self.setVerticalScrollMode(self._before_flick_scroll_mode)
