import os
import sys

from qtpy import QtCore, QtGui, QtWidgets

from .iconic_font import get_instance

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
VIEW_COLUMNS = 5
AUTO_SEARCH_TIMEOUT = 500


def load_stylesheet():
    path = os.path.join(CURRENT_DIR, "stylesheet.qss")
    with open(path, "r") as stream:
        content = stream.read()
    return content


class IconModel(QtCore.QStringListModel):
    def __init__(self, icon_color):
        super().__init__()
        self._icon_color = icon_color

    def flags(self, index):
        return QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable

    def set_icon_color(self, color):
        self._icon_color = color
        # TODO This does not trigger a repaint

    def data(self, index, role):
        if role == QtCore.Qt.DecorationRole:
            value = self.data(index, role=QtCore.Qt.DisplayRole)
            instance = get_instance()
            return instance.get_icon(value, color=self._icon_color)
        return super().data(index, role)


class IconBrowser(QtWidgets.QMainWindow):
    """
    A small browser window that allows the user to search through all icons from
    the available version of QtAwesome.  You can also copy the name and python
    code for the currently selected icon.
    """

    def __init__(self):
        super().__init__()
        self.setMinimumSize(630, 420)
        self.setWindowTitle("Material Symbols Browser")

        # Prepare icons data
        instance = get_instance()
        font_maps = instance.get_charmap()

        icon_names = list(font_maps)

        center_widget = QtWidgets.QWidget(self)

        # Filtering inputs
        header_widget = QtWidgets.QWidget(center_widget)

        filter_input = QtWidgets.QLineEdit(header_widget)
        filter_input.setPlaceholderText("Filter by name...")

        copy_btn = QtWidgets.QPushButton("< no selection >", header_widget)
        copy_btn.setToolTip("Copy name")

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(filter_input, 2)
        header_layout.addWidget(copy_btn, 1)

        # Icons view
        icons_view = IconListView(center_widget)
        icons_view.setUniformItemSizes(True)
        icons_view.setResizeMode(QtWidgets.QListView.Adjust)
        icons_view.setViewMode(QtWidgets.QListView.IconMode)
        icons_view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        model = IconModel(QtGui.QColor("#444746"))
        model.setStringList(sorted(icon_names))

        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(model)
        proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

        icons_view.setModel(proxy_model)

        center_layout = QtWidgets.QVBoxLayout(center_widget)
        center_layout.setContentsMargins(15, 15, 15, 15)
        center_layout.setSpacing(5)
        center_layout.addWidget(header_widget, 0)
        center_layout.addWidget(icons_view, 1)

        self.setCentralWidget(center_widget)

        filter_timer = QtCore.QTimer(self)
        filter_timer.setSingleShot(True)
        filter_timer.setInterval(AUTO_SEARCH_TIMEOUT)

        filter_input.textChanged.connect(self._on_filter_change)
        filter_input.returnPressed.connect(self._on_filter_confirm)
        icons_view.doubleClicked.connect(self._copy_icon_name)
        icons_view.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        copy_btn.clicked.connect(self._copy_icon_name)
        filter_timer.timeout.connect(self._update_filter)

        QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key_Return),
            self,
            self._copy_icon_name,
        )
        QtWidgets.QShortcut(
            QtGui.QKeySequence("Ctrl+F"),
            self,
            filter_input.setFocus,
        )

        self._copy_btn = copy_btn
        self._filter_input = filter_input
        self._icons_view = icons_view
        self._model = model
        self._proxy_model = proxy_model
        self._filter_timer = filter_timer

    def showEvent(self, event):
        super().showEvent(event)
        self._filter_input.setFocus()
        self.setStyleSheet(load_stylesheet())

    def _update_filter(self):
        regex = ""
        search_term = self._filter_input.text()
        if search_term:
            regex = f".*{search_term}.*$"

        self._proxy_model.setFilterRegularExpression(regex)

    def _on_selection_change(self, _new_selection, _old_selection):
        indexes = self._icons_view.selectedIndexes()
        if not indexes:
            self._copy_btn.setText("< nothing >")
            return

        index = indexes[0]
        icon_name = index.data()
        self._copy_btn.setText(icon_name)

    def _on_filter_change(self):
        self._filter_timer.start()

    def _on_filter_confirm(self):
        self._filter_timer.stop()
        self._update_filter()

    def _copy_icon_name(self):
        indexes = self._icons_view.selectedIndexes()
        for index in indexes:
            clipboard = QtWidgets.QApplication.instance().clipboard()
            clipboard.setText(index.data())
            break


class IconListView(QtWidgets.QListView):
    """
    A QListView that scales it's grid size to ensure the same number of
    columns are always drawn.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.set_icon_size(54)

    def set_icon_size(self, size):
        """
        Set the icon size for the icons in the view.
        """
        grid_size = (size / 8.0) * 12.0
        self.setGridSize(QtCore.QSize(grid_size, grid_size))
        self.setIconSize(QtCore.QSize(size, size))


def run():
    """
    Start the IconBrowser and block until the process exits.
    """
    app = QtWidgets.QApplication([])

    browser = IconBrowser()
    browser.show()

    sys.exit(app.exec_())
