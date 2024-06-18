import uuid

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import get_qt_icon
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
        status_color,
        status_icon,
    ):
        self.version = version
        self.label = label
        self.status_name = status_name
        self.status_short = status_short
        self.status_color = status_color
        self.status_icon = status_icon


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
        self._status_visible = True

    def paintEvent(self, event):
        if not self._status_visible:
            return super().paintEvent(event)

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

        status_icon = self.itemData(idx, STATUS_ICON_ROLE)
        content_field_rect = self.style().subControlRect(
            QtWidgets.QStyle.CC_ComboBox,
            option,
            QtWidgets.QStyle.SC_ComboBoxEditField
        ).adjusted(1, 0, -1, 0)

        metrics = option.fontMetrics
        version_text_width = metrics.width(option.currentText) + 2
        version_text_rect = QtCore.QRect(content_field_rect)
        version_text_rect.setWidth(version_text_width)

        painter.drawText(
            version_text_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            option.currentText
        )

        status_text_rect = QtCore.QRect(content_field_rect)
        status_text_rect.setLeft(version_text_rect.right() + 2)
        if status_icon is not None and not status_icon.isNull():
            icon_rect = QtCore.QRect(status_text_rect)
            diff = icon_rect.height() - metrics.height()
            if diff < 0:
                diff = 0
            top_offset = diff // 2
            bottom_offset = diff - top_offset
            icon_rect.adjust(0, top_offset, 0, -bottom_offset)
            icon_rect.setWidth(metrics.height())
            status_icon.paint(
                painter,
                icon_rect,
                QtCore.Qt.AlignCenter,
                QtGui.QIcon.Normal,
                QtGui.QIcon.On
            )
            status_text_rect.setLeft(icon_rect.right() + 2)

        if status_text_rect.width() <= 0:
            return

        if status_text_rect.width() < metrics.width(status_name):
            status_name = self.itemData(idx, STATUS_SHORT_ROLE)
            if status_text_rect.width() < metrics.width(status_name):
                status_name = ""

        color = QtGui.QColor(self.itemData(idx, STATUS_COLOR_ROLE))

        pen = painter.pen()
        pen.setColor(color)
        painter.setPen(pen)
        painter.drawText(
            status_text_rect,
            QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
            status_name
        )

    def set_current_index(self, index):
        model = self._combo_view.model()
        if index > model.rowCount():
            return

        self.setCurrentIndex(index)

    def set_status_visible(self, visible):
        header = self._combo_view.header()
        header.setSectionHidden(1, not visible)
        self._status_visible = visible
        self.update()

    def get_item_by_id(self, item_id):
        return self._items_by_id[item_id]

    def set_versions(self, version_options):
        self._items_by_id = {}
        model = self._combo_model
        root_item = model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        new_items = []
        icons_by_name = {}
        for version_option in version_options:
            icon = icons_by_name.get(version_option.status_icon)
            if icon is None:
                icon = get_qt_icon({
                    "type": "material-symbols",
                    "name": version_option.status_icon,
                    "color": version_option.status_color
                })
                icons_by_name[version_option.status_icon] = icon

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
            item.setData(icon, STATUS_ICON_ROLE)
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

    def set_status_visible(self, visible):
        self._versions_combobox.set_status_visible(visible)

    @classmethod
    def ask_for_version(
        cls, version_options, index=None, show_statuses=True, parent=None
    ):
        dialog = cls(parent)
        dialog.set_versions(version_options)
        dialog.set_status_visible(show_statuses)
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
