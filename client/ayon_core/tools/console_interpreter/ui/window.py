import re
from typing import Optional

from qtpy import QtWidgets, QtGui, QtCore

from ayon_core import resources
from ayon_core.style import load_stylesheet
from ayon_core.tools.console_interpreter import (
    AbstractInterpreterController,
    InterpreterController,
)

from .utils import StdOEWrap
from .widgets import (
    PythonTabWidget,
    OutputTextWidget,
    EnhancedTabBar,
    TabNameDialog,
)

ANSI_ESCAPE = re.compile(
    r"(?:\x1B[@-_]|[\x80-\x9F])[0-?]*[ -/]*[@-~]"
)
AYON_ART = r"""

                    ▄██▄
         ▄███▄ ▀██▄ ▀██▀ ▄██▀ ▄██▀▀▀██▄    ▀███▄      █▄
        ▄▄ ▀██▄  ▀██▄  ▄██▀ ██▀      ▀██▄  ▄  ▀██▄    ███
       ▄██▀  ██▄   ▀ ▄▄ ▀  ██         ▄██  ███  ▀██▄  ███
      ▄██▀    ▀██▄   ██    ▀██▄      ▄██▀  ███    ▀██ ▀█▀
     ▄██▀      ▀██▄  ▀█      ▀██▄▄▄▄██▀    █▀      ▀██▄

     ·  · - =[ by YNPUT ]:[ http://ayon.ynput.io ]= - ·  ·

"""


class ConsoleInterpreterWindow(QtWidgets.QWidget):
    default_width = 1000
    default_height = 600

    def __init__(
        self,
        controller: Optional[AbstractInterpreterController] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("AYON Console")
        self.setWindowIcon(QtGui.QIcon(resources.get_ayon_icon_filepath()))

        if controller is None:
            controller = InterpreterController()

        output_widget = OutputTextWidget(self)
        output_widget.setObjectName("PythonInterpreterOutput")
        output_widget.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)
        output_widget.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)

        tab_widget = QtWidgets.QTabWidget(self)
        tab_bar = EnhancedTabBar(tab_widget)
        tab_widget.setTabBar(tab_bar)
        tab_widget.setTabsClosable(False)
        tab_widget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        widgets_splitter = QtWidgets.QSplitter(self)
        widgets_splitter.setOrientation(QtCore.Qt.Vertical)
        widgets_splitter.addWidget(output_widget)
        widgets_splitter.addWidget(tab_widget)
        widgets_splitter.setStretchFactor(0, 1)
        widgets_splitter.setStretchFactor(1, 1)
        height = int(self.default_height / 2)
        widgets_splitter.setSizes([height, self.default_height - height])

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(widgets_splitter)

        line_check_timer = QtCore.QTimer()
        line_check_timer.setInterval(200)

        line_check_timer.timeout.connect(self._on_timer_timeout)
        tab_bar.right_clicked.connect(self._on_tab_right_click)
        tab_bar.double_clicked.connect(self._on_tab_double_click)
        tab_bar.mid_clicked.connect(self._on_tab_mid_click)
        tab_widget.tabCloseRequested.connect(self._on_tab_close_req)

        self._tabs = []

        self._stdout_err_wrapper = StdOEWrap()

        self._widgets_splitter = widgets_splitter
        self._output_widget = output_widget
        self._tab_widget = tab_widget
        self._line_check_timer = line_check_timer

        self._append_lines([AYON_ART])

        self._first_show = True
        self._controller = controller

    def showEvent(self, event):
        self._line_check_timer.start()
        super().showEvent(event)
        # First show setup
        if self._first_show:
            self._first_show = False
            self._on_first_show()

        if self._tab_widget.count() < 1:
            self.add_tab("Python")

        self._output_widget.scroll_to_bottom()

    def closeEvent(self, event):
        self._save_registry()
        super().closeEvent(event)
        self._line_check_timer.stop()

    def add_tab(self, tab_name, index=None):
        widget = PythonTabWidget(self)
        widget.before_execute.connect(self._on_before_execute)
        widget.add_tab_requested.connect(self._on_add_requested)
        if index is None:
            if self._tab_widget.count() > 0:
                index = self._tab_widget.currentIndex() + 1
            else:
                index = 0

        self._tabs.append(widget)
        self._tab_widget.insertTab(index, widget, tab_name)
        self._tab_widget.setCurrentIndex(index)

        if self._tab_widget.count() > 1:
            self._tab_widget.setTabsClosable(True)
        widget.setFocus()
        return widget

    def _on_first_show(self):
        config = self._controller.get_config()
        width = config.width
        height = config.height
        if width is None or width < 200:
            width = self.default_width
        if height is None or height < 200:
            height = self.default_height

        for tab_item in config.tabs:
            widget = self.add_tab(tab_item.name)
            widget.set_code(tab_item.code)

        self.resize(width, height)
        # Change stylesheet
        self.setStyleSheet(load_stylesheet())
        # Check if splitter sizes are set
        splitters_count = len(self._widgets_splitter.sizes())
        if len(config.splitter_sizes) == splitters_count:
            self._widgets_splitter.setSizes(config.splitter_sizes)

    def _save_registry(self):
        tabs = []
        for tab_idx in range(self._tab_widget.count()):
            widget = self._tab_widget.widget(tab_idx)
            tabs.append({
                "name": self._tab_widget.tabText(tab_idx),
                "code": widget.get_code()
            })

        self._controller.save_config(
            self.width(),
            self.height(),
            self._widgets_splitter.sizes(),
            tabs
        )

    def _on_tab_right_click(self, global_point):
        point = self._tab_widget.mapFromGlobal(global_point)
        tab_bar = self._tab_widget.tabBar()
        tab_idx = tab_bar.tabAt(point)
        last_index = tab_bar.count() - 1
        if tab_idx < 0 or tab_idx > last_index:
            return

        menu = QtWidgets.QMenu(self._tab_widget)

        add_tab_action = QtWidgets.QAction("Add tab...", menu)
        add_tab_action.setToolTip("Add new tab")

        rename_tab_action = QtWidgets.QAction("Rename...", menu)
        rename_tab_action.setToolTip("Rename tab")

        duplicate_tab_action = QtWidgets.QAction("Duplicate...", menu)
        duplicate_tab_action.setToolTip("Duplicate code to new tab")

        close_tab_action = QtWidgets.QAction("Close", menu)
        close_tab_action.setToolTip("Close tab and lose content")
        close_tab_action.setEnabled(self._tab_widget.tabsClosable())

        menu.addAction(add_tab_action)
        menu.addAction(rename_tab_action)
        menu.addAction(duplicate_tab_action)
        menu.addAction(close_tab_action)

        result = menu.exec_(global_point)
        if result is None:
            return

        if result is rename_tab_action:
            self._rename_tab_req(tab_idx)

        elif result is add_tab_action:
            self._on_add_requested()

        elif result is duplicate_tab_action:
            self._duplicate_requested(tab_idx)

        elif result is close_tab_action:
            self._on_tab_close_req(tab_idx)

    def _rename_tab_req(self, tab_idx):
        dialog = TabNameDialog(self)
        dialog.set_tab_name(self._tab_widget.tabText(tab_idx))
        dialog.exec_()
        tab_name = dialog.result()
        if tab_name:
            self._tab_widget.setTabText(tab_idx, tab_name)

    def _duplicate_requested(self, tab_idx=None):
        if tab_idx is None:
            tab_idx = self._tab_widget.currentIndex()

        src_widget = self._tab_widget.widget(tab_idx)
        dst_widget = self._add_tab()
        if dst_widget is None:
            return
        dst_widget.set_code(src_widget.get_code())

    def _on_tab_mid_click(self, global_point):
        point = self._tab_widget.mapFromGlobal(global_point)
        tab_bar = self._tab_widget.tabBar()
        tab_idx = tab_bar.tabAt(point)
        last_index = tab_bar.count() - 1
        if tab_idx < 0 or tab_idx > last_index:
            return

        self._on_tab_close_req(tab_idx)

    def _on_tab_double_click(self, global_point):
        point = self._tab_widget.mapFromGlobal(global_point)
        tab_bar = self._tab_widget.tabBar()
        tab_idx = tab_bar.tabAt(point)
        last_index = tab_bar.count() - 1
        if tab_idx < 0 or tab_idx > last_index:
            return

        self._rename_tab_req(tab_idx)

    def _on_tab_close_req(self, tab_index):
        if self._tab_widget.count() == 1:
            return

        widget = self._tab_widget.widget(tab_index)
        if widget in self._tabs:
            self._tabs.remove(widget)
        self._tab_widget.removeTab(tab_index)

        if self._tab_widget.count() == 1:
            self._tab_widget.setTabsClosable(False)

    def _append_lines(self, lines):
        at_max = self._output_widget.vertical_scroll_at_max()
        tmp_cursor = QtGui.QTextCursor(self._output_widget.document())
        tmp_cursor.movePosition(QtGui.QTextCursor.End)
        for line in lines:
            tmp_cursor.insertText(line)

        if at_max:
            self._output_widget.scroll_to_bottom()

    def _on_timer_timeout(self):
        if self._stdout_err_wrapper.lines:
            lines = []
            while self._stdout_err_wrapper.lines:
                line = self._stdout_err_wrapper.lines.popleft()
                lines.append(ANSI_ESCAPE.sub("", line))
            self._append_lines(lines)

    def _on_add_requested(self):
        self._add_tab()

    def _add_tab(self):
        dialog = TabNameDialog(self)
        dialog.exec_()
        tab_name = dialog.result()
        if tab_name:
            return self.add_tab(tab_name)

        return None

    def _on_before_execute(self, code_text):
        at_max = self._output_widget.vertical_scroll_at_max()
        document = self._output_widget.document()
        tmp_cursor = QtGui.QTextCursor(document)
        tmp_cursor.movePosition(QtGui.QTextCursor.End)
        tmp_cursor.insertText("{}\nExecuting command:\n".format(20 * "-"))

        code_block_format = QtGui.QTextFrameFormat()
        code_block_format.setBackground(QtGui.QColor(27, 27, 27))
        code_block_format.setPadding(4)

        tmp_cursor.insertFrame(code_block_format)
        char_format = tmp_cursor.charFormat()
        char_format.setForeground(
            QtGui.QBrush(QtGui.QColor(114, 224, 198))
        )
        tmp_cursor.setCharFormat(char_format)
        tmp_cursor.insertText(code_text)

        # Create new cursor
        tmp_cursor = QtGui.QTextCursor(document)
        tmp_cursor.movePosition(QtGui.QTextCursor.End)
        tmp_cursor.insertText("{}\n".format(20 * "-"))

        if at_max:
            self._output_widget.scroll_to_bottom()
