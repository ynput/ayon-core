import uuid

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils.delegates import StatusDelegate

from .model import (
    ITEM_ID_ROLE,
    STATUS_NAME_ROLE,
    STATUS_SHORT_ROLE,
    STATUS_COLOR_ROLE,
    STATUS_ICON_ROLE,
)


class VersionOption:
    def __init__(
        self,
        version,
        label,
        status_name,
        status_short,
        status_color
    ):
        self.version = version
        self.label = label
        self.status_name = status_name
        self.status_short = status_short
        self.status_color = status_color


class SelectVersionModel(QtGui.QStandardItemModel):
    def data(self, index, role=None):
        if role is None:
            role = QtCore.Qt.DisplayRole

        index = self.index(index.row(), 0, index.parent())
        return super().data(index, role)


class SelectVersionComboBox(QtWidgets.QComboBox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        combo_model = SelectVersionModel(0, 2)

        self.setModel(combo_model)

        combo_view = QtWidgets.QTreeView(self)
        combo_view.setHeaderHidden(True)
        combo_view.setIndentation(0)

        self.setView(combo_view)

        header = combo_view.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)

        status_delegate = StatusDelegate(
            STATUS_NAME_ROLE,
            STATUS_SHORT_ROLE,
            STATUS_COLOR_ROLE,
            STATUS_ICON_ROLE,
        )
        combo_view.setItemDelegateForColumn(1, status_delegate)

        self._combo_model = combo_model
        self._combo_view = combo_view
        self._status_delegate = status_delegate
        self._items_by_id = {}

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        painter.drawComplexControl(QtWidgets.QStyle.CC_ComboBox, option)
        idx = self.currentIndex()
        status_name = self.itemData(idx, STATUS_NAME_ROLE)
        if status_name is None:
            painter.drawControl(QtWidgets.QStyle.CE_ComboBoxLabel, option)
            return

        painter.save()
        text_field_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            option,
            QtWidgets.QStyle.SC_ComboBoxEditField
        )
        adj_rect = text_field_rect.adjusted(1, 0, -1, 0)
        painter.drawText(
            adj_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            option.currentText
        )
        metrics = QtGui.QFontMetrics(self.font())
        text_width = metrics.width(option.currentText)
        x_offset = text_width + 2
        diff_width = adj_rect.width() - x_offset
        if diff_width <= 0:
            return

        status_rect = adj_rect.adjusted(x_offset + 2, 0, 0, 0)
        if diff_width < metrics.width(status_name):
            status_name = self.itemData(idx, STATUS_SHORT_ROLE)

        color = QtGui.QColor(self.itemData(idx, STATUS_COLOR_ROLE))

        pen = painter.pen()
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawText(
            status_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            status_name
        )

    def set_current_index(self, index):
        model = self._combo_view.model()
        if index > model.rowCount():
            return

        self.setCurrentIndex(index)

    def get_item_by_id(self, item_id):
        return self._items_by_id[item_id]

    def set_versions(self, version_options):
        self._items_by_id = {}
        model = self._combo_model
        root_item = model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        new_items = []
        for version_option in version_options:
            item_id = uuid.uuid4().hex
            item = QtGui.QStandardItem(version_option.label)
            item.setColumnCount(root_item.columnCount())
            item.setData(
                version_option.status_name, STATUS_NAME_ROLE
            )
            item.setData(
                version_option.status_short, STATUS_SHORT_ROLE
            )
            item.setData(
                version_option.status_color, STATUS_COLOR_ROLE
            )
            item.setData(item_id, ITEM_ID_ROLE)

            new_items.append(item)
            self._items_by_id[item_id] = version_option

        if new_items:
            root_item.appendRows(new_items)


class SelectVersionDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent=parent)

        self.setWindowTitle("Select version")

        label_widget = QtWidgets.QLabel("Set version number to", self)
        versions_combobox = SelectVersionComboBox(self)

        btns_widget = QtWidgets.QWidget(self)

        confirm_btn = QtWidgets.QPushButton("OK", btns_widget)
        cancel_btn = QtWidgets.QPushButton("Cancel", btns_widget)

        btns_layout = QtWidgets.QHBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addStretch(1)
        btns_layout.addWidget(confirm_btn, 0)
        btns_layout.addWidget(cancel_btn, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(label_widget, 0)
        main_layout.addWidget(versions_combobox, 0)
        main_layout.addWidget(btns_widget, 0)

        confirm_btn.clicked.connect(self._on_confirm)
        cancel_btn.clicked.connect(self._on_cancel)

        self._selected_item = None
        self._cancelled = False
        self._versions_combobox = versions_combobox

    def get_selected_item(self):
        if self._cancelled:
            return None
        return self._selected_item

    def set_versions(self, version_options):
        self._versions_combobox.set_versions(version_options)

    def select_index(self, index):
        self._versions_combobox.set_current_index(index)

    @classmethod
    def ask_for_version(cls, version_options, index=None, parent=None):
        dialog = cls(parent)
        dialog.set_versions(version_options)
        if index is not None:
            dialog.select_index(index)
        dialog.exec_()
        return dialog.get_selected_item()

    def _on_confirm(self):
        self._cancelled = False
        index = self._versions_combobox.currentIndex()
        item_id = self._versions_combobox.itemData(index, ITEM_ID_ROLE)
        self._selected_item = self._versions_combobox.get_item_by_id(item_id)
        self.accept()

    def _on_cancel(self):
        self._cancelled = True
        self.reject()
