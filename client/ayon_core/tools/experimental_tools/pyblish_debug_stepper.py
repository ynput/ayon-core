"""
Brought from https://gist.github.com/BigRoy/1972822065e38f8fae7521078e44eca2
Code Credits: [BigRoy](https://github.com/BigRoy)

Requirement:
    It requires pyblish version >= 1.8.12

How it works:
    This tool makes use of pyblish event `pluginProcessed` to:
        1. Pause the publishing.
        2. Collect some info about the plugin.
        3. Show that info to the tool's window.
        4. Continue publishing on clicking `step` button.

How to use it:
    1. Launch the tool from AYON experimental tools window.
    2. Launch the publisher tool and click validate.
    3. Click Step to run plugins one by one.

Note :
    Pyblish debugger also works when triggering the validation or
      publishing from code.
    Here's an example about validating from code:
    https://github.com/MustafaJafar/ayon-recipes/blob/main/validate_from_code.py

"""

import copy
import json
from qtpy import QtWidgets, QtCore, QtGui

import pyblish.api
from ayon_core import style

TAB = 4* "&nbsp;"
HEADER_SIZE = "15px"

KEY_COLOR = QtGui.QColor("#ffffff")
NEW_KEY_COLOR = QtGui.QColor("#00ff00")
VALUE_TYPE_COLOR = QtGui.QColor("#ffbbbb")
NEW_VALUE_TYPE_COLOR = QtGui.QColor("#ff4444")
VALUE_COLOR = QtGui.QColor("#777799")
NEW_VALUE_COLOR = QtGui.QColor("#DDDDCC")
CHANGED_VALUE_COLOR = QtGui.QColor("#CCFFCC")

MAX_VALUE_STR_LEN = 100


def failsafe_deepcopy(data):
    """Allow skipping the deepcopy for unsupported types"""
    try:
        return copy.deepcopy(data)
    except TypeError:
        if isinstance(data, dict):
            return {
                key: failsafe_deepcopy(value)
                for key, value in data.items()
            }
        elif isinstance(data, list):
            return data.copy()
    return data


class DictChangesModel(QtGui.QStandardItemModel):
    # TODO: Replace this with a QAbstractItemModel
    def __init__(self, *args, **kwargs):
        super(DictChangesModel, self).__init__(*args, **kwargs)
        self._data = {}

        columns = ["Key", "Type", "Value"]
        self.setColumnCount(len(columns))
        for i, label in enumerate(columns):
            self.setHeaderData(i, QtCore.Qt.Horizontal, label)

    def _update_recursive(self, data, parent, previous_data):
        for key, value in data.items():

            # Find existing item or add new row
            parent_index = parent.index()
            for row in range(self.rowCount(parent_index)):
                # Update existing item if it exists
                index = self.index(row, 0, parent_index)
                if index.data() == key:
                    item = self.itemFromIndex(index)
                    type_item = self.itemFromIndex(self.index(row, 1, parent_index))  # noqa
                    value_item = self.itemFromIndex(self.index(row, 2, parent_index))  # noqa
                    break
            else:
                item = QtGui.QStandardItem(key)
                type_item = QtGui.QStandardItem()
                value_item = QtGui.QStandardItem()
                parent.appendRow([item, type_item, value_item])

            # Key
            key_color = NEW_KEY_COLOR if key not in previous_data else KEY_COLOR  # noqa
            item.setData(key_color, QtCore.Qt.ForegroundRole)

            # Type
            type_str = type(value).__name__
            type_color = VALUE_TYPE_COLOR
            if (
                key in previous_data
                and type(previous_data[key]).__name__ != type_str
            ):
                type_color = NEW_VALUE_TYPE_COLOR

            type_item.setText(type_str)
            type_item.setData(type_color, QtCore.Qt.ForegroundRole)

            # Value
            value_changed = False
            if key not in previous_data or previous_data[key] != value:
                value_changed = True
            value_color = NEW_VALUE_COLOR if value_changed else VALUE_COLOR

            value_item.setData(value_color, QtCore.Qt.ForegroundRole)
            if value_changed:
                value_str = str(value)
                if len(value_str) > MAX_VALUE_STR_LEN:
                    value_str = value_str[:MAX_VALUE_STR_LEN] + "..."
                value_item.setText(value_str)

                # Preferably this is deferred to only when the data gets
                # requested since this formatting can be slow for very large
                # data sets like project settings and system settings
                # This will also be MUCH faster if we don't clear the
                # items on each update but only updated/add/remove changed
                # items so that this also runs much less often
                value_item.setData(
                    json.dumps(value, default=str, indent=4),
                    QtCore.Qt.ToolTipRole
                )

            if isinstance(value, dict):
                previous_value = previous_data.get(key, {})
                if previous_data.get(key) != value:
                    # Update children if the value is not the same as before
                    self._update_recursive(value,
                                           parent=item,
                                           previous_data=previous_value)
                else:
                    # TODO: Ensure all children are updated to be not marked
                    #  as 'changed' in the most optimal way possible
                    self._update_recursive(value,
                                           parent=item,
                                           previous_data=previous_value)

        self._data = data

    def update(self, data):
        parent = self.invisibleRootItem()

        data = failsafe_deepcopy(data)
        previous_data = self._data
        self._update_recursive(data, parent, previous_data)
        self._data = data  # store previous data for next update


class DebugUI(QtWidgets.QDialog):

    def __init__(self, parent=None):
        super(DebugUI, self).__init__(parent=parent)
        self.setStyleSheet(style.load_stylesheet())

        self._set_window_title()
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.CustomizeWindowHint
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowStaysOnTopHint
        )

        layout = QtWidgets.QVBoxLayout(self)
        text_edit = QtWidgets.QTextEdit()
        text_edit.setFixedHeight(65)
        font = QtGui.QFont("NONEXISTENTFONT")
        font.setStyleHint(QtGui.QFont.TypeWriter)
        text_edit.setFont(font)
        text_edit.setLineWrapMode(QtWidgets.QTextEdit.NoWrap)

        step = QtWidgets.QPushButton("Step")
        step.setEnabled(False)

        model = DictChangesModel()
        proxy = QtCore.QSortFilterProxyModel()
        proxy.setRecursiveFilteringEnabled(True)
        proxy.setSourceModel(model)
        view = QtWidgets.QTreeView()
        view.setModel(proxy)
        view.setSortingEnabled(True)

        filter_field = QtWidgets.QLineEdit()
        filter_field.setPlaceholderText("Filter keys...")
        filter_field.textChanged.connect(proxy.setFilterFixedString)

        layout.addWidget(text_edit)
        layout.addWidget(filter_field)
        layout.addWidget(view)
        layout.addWidget(step)

        step.clicked.connect(self.on_step)

        self._pause = False
        self.model = model
        self.filter = filter_field
        self.proxy = proxy
        self.view = view
        self.text = text_edit
        self.step = step
        self.resize(700, 500)

        self._previous_data = {}

    def _set_window_title(self, plugin=None):
        title = "Pyblish Debug Stepper"
        if plugin is not None:
            plugin_label = plugin.label or plugin.__name__
            title += f" | {plugin_label}"
        self.setWindowTitle(title)

    def pause(self, state):
        self._pause = state
        self.step.setEnabled(state)

    def on_step(self):
        self.pause(False)

    def showEvent(self, event):
        print("Registering callback..")
        pyblish.api.register_callback("pluginProcessed",
                                      self.on_plugin_processed)

    def hideEvent(self, event):
        self.pause(False)
        print("Deregistering callback..")
        pyblish.api.deregister_callback("pluginProcessed",
                                        self.on_plugin_processed)

    def on_plugin_processed(self, result):
        self.pause(True)

        self._set_window_title(plugin=result["plugin"])

        print(10*"<", result["plugin"].__name__, 10*">")

        plugin_order = result["plugin"].order
        plugin_name = result["plugin"].__name__
        duration = result['duration']
        plugin_instance = result["instance"]
        context = result["context"]

        msg = ""
        msg += f"Order: {plugin_order}<br>"
        msg += f"Plugin: {plugin_name}"
        if plugin_instance is not None:
            msg += f" -> instance: {plugin_instance}"
        msg += "<br>"
        msg += f"Duration: {duration} ms<br>"
        self.text.setHtml(msg)

        data = {
            "context": context.data
        }
        for instance in context:
            data[instance.name] = instance.data
        self.model.update(data)

        app = QtWidgets.QApplication.instance()
        while self._pause:
            # Allow user interaction with the UI
            app.processEvents()
