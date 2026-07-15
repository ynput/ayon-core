from qtpy import QtWidgets, QtCore
from ayon_core.ui.components.tree_view import TreeViewItemDelegate
from ayon_core.tools.utils.delegates import pretty_timestamp

class WorkfilesDelegate(TreeViewItemDelegate):
    """Unified delegate for the workfiles tree view.

    Column 0: workfile name with middle-elide.
    Column 2: pretty-printed timestamp (falls back to ``"N/A"``).
    """

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.column() == 0:
            option.textElideMode = QtCore.Qt.ElideMiddle
        elif index.column() == 2:
            # Column 2 exposes timestamp through DisplayRole in WorkfilesModel.
            raw = index.data(QtCore.Qt.DisplayRole)
            if raw is not None:
                pretty = pretty_timestamp(raw)
                if pretty is not None:
                    option.text = pretty
                    return
            option.text = "N/A"

class BaseOverlayFrame(QtWidgets.QFrame):
    """Base frame for overlay widgets.

    Has implemented automated resize and event filtering.
    """

    def __init__(self, parent):
        super(BaseOverlayFrame, self).__init__(parent)
        self.setObjectName("OverlayFrame")

        self._parent = parent

    def setVisible(self, visible):
        super(BaseOverlayFrame, self).setVisible(visible)
        if visible:
            self._parent.installEventFilter(self)
            self.resize(self._parent.size())
        else:
            self._parent.removeEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize:
            self.resize(obj.size())

        return super(BaseOverlayFrame, self).eventFilter(obj, event)
