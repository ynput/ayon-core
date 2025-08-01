from __future__ import annotations

import numbers
import uuid

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils.lib import format_version

from .products_model import (
    PRODUCT_ID_ROLE,
    VERSION_NAME_EDIT_ROLE,
    VERSION_ID_ROLE,
    PRODUCT_IN_SCENE_ROLE,
    ACTIVE_SITE_ICON_ROLE,
    REMOTE_SITE_ICON_ROLE,
    REPRESENTATIONS_COUNT_ROLE,
    SYNC_ACTIVE_SITE_AVAILABILITY,
    SYNC_REMOTE_SITE_AVAILABILITY,
)

COMBO_VERSION_ID_ROLE = QtCore.Qt.UserRole + 1
COMBO_TASK_ID_ROLE = QtCore.Qt.UserRole + 2
COMBO_STATUS_NAME_ROLE = QtCore.Qt.UserRole + 3
COMBO_VERSION_TAGS_ROLE = QtCore.Qt.UserRole + 4
COMBO_TASK_TAGS_ROLE = QtCore.Qt.UserRole + 5


class ComboVersionsModel(QtGui.QStandardItemModel):
    def __init__(self):
        super().__init__()
        self._items_by_id = {}

    def update_versions(self, version_items, task_tags_by_version_id):
        version_ids = {
            version_item.version_id
            for version_item in version_items
        }

        root_item = self.invisibleRootItem()
        to_remove = set(self._items_by_id.keys()) - set(version_ids)
        for item_id in to_remove:
            item = self._items_by_id.pop(item_id)
            root_item.removeRow(item.row())

        version_tags_by_version_id = {}
        for idx, version_item in enumerate(version_items):
            version_id = version_item.version_id

            item = self._items_by_id.get(version_id)
            if item is None:
                label = format_version(version_item.version)
                item = QtGui.QStandardItem(label)
                item.setData(version_id, QtCore.Qt.UserRole)
                self._items_by_id[version_id] = item
            version_tags = set(version_item.tags)
            task_tags = task_tags_by_version_id[version_id]
            item.setData(version_id, COMBO_VERSION_ID_ROLE)
            item.setData(version_item.status, COMBO_STATUS_NAME_ROLE)
            item.setData(version_item.task_id, COMBO_TASK_ID_ROLE)
            item.setData("|".join(version_tags), COMBO_VERSION_TAGS_ROLE)
            item.setData("|".join(task_tags), COMBO_TASK_TAGS_ROLE)
            version_tags_by_version_id[version_id] = set(version_item.tags)

            if item.row() != idx:
                root_item.insertRow(idx, item)


class ComboVersionsFilterModel(QtCore.QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._status_filter = None
        self._task_ids_filter = None
        self._version_tags_filter = None
        self._task_tags_filter = None

    def filterAcceptsRow(self, row, parent):
        index = None
        if self._status_filter is not None:
            if not self._status_filter:
                return False
            if index is None:
                index = self.sourceModel().index(row, 0, parent)
            status = index.data(COMBO_STATUS_NAME_ROLE)
            if status not in self._status_filter:
                return False

        if self._task_ids_filter:
            if index is None:
                index = self.sourceModel().index(row, 0, parent)
            task_id = index.data(COMBO_TASK_ID_ROLE)
            if task_id not in self._task_ids_filter:
                return False

        if self._version_tags_filter is not None:
            if not self._version_tags_filter:
                return False

            if index is None:
                model = self.sourceModel()
                index = model.index(row, 0, parent)
            version_tags_s = index.data(COMBO_TASK_TAGS_ROLE)
            version_tags = set()
            if version_tags_s:
                version_tags = set(version_tags_s.split("|"))

            if not version_tags & self._version_tags_filter:
                return False

        if self._task_tags_filter is not None:
            if not self._task_tags_filter:
                return False

            if index is None:
                model = self.sourceModel()
                index = model.index(row, 0, parent)
            task_tags_s = index.data(COMBO_TASK_TAGS_ROLE)
            task_tags = set()
            if task_tags_s:
                task_tags = set(task_tags_s.split("|"))
            if not (task_tags & self._task_tags_filter):
                return False

        return True

    def set_tasks_filter(self, task_ids):
        if self._task_ids_filter == task_ids:
            return
        self._task_ids_filter = task_ids
        self.invalidateFilter()

    def set_task_tags_filter(self, tags):
        if self._task_tags_filter == tags:
            return
        self._task_tags_filter = tags
        self.invalidateFilter()

    def set_statuses_filter(self, status_names):
        if self._status_filter == status_names:
            return
        self._status_filter = status_names
        self.invalidateFilter()

    def set_version_tags_filter(self, tags):
        if self._version_tags_filter == tags:
            return
        self._version_tags_filter = tags
        self.invalidateFilter()


class VersionComboBox(QtWidgets.QComboBox):
    value_changed = QtCore.Signal(str, str)

    def __init__(self, product_id, parent):
        super().__init__(parent)

        versions_model = ComboVersionsModel()
        proxy_model = ComboVersionsFilterModel()
        proxy_model.setSourceModel(versions_model)

        self.setModel(proxy_model)

        self._product_id = product_id
        self._items_by_id = {}

        self._current_id = None

        self._versions_model = versions_model
        self._proxy_model = proxy_model

        self.currentIndexChanged.connect(self._on_index_change)

    def get_product_id(self):
        return self._product_id

    def set_tasks_filter(self, task_ids):
        self._proxy_model.set_tasks_filter(task_ids)
        if self.count() == 0:
            return
        if self.currentIndex() != 0:
            self.setCurrentIndex(0)

    def set_task_tags_filter(self, tags):
        self._proxy_model.set_task_tags_filter(tags)
        if self.count() == 0:
            return
        if self.currentIndex() != 0:
            self.setCurrentIndex(0)

    def set_statuses_filter(self, status_names):
        self._proxy_model.set_statuses_filter(status_names)
        if self.count() == 0:
            return
        if self.currentIndex() != 0:
            self.setCurrentIndex(0)

    def set_version_tags_filter(self, tags):
        self._proxy_model.set_version_tags_filter(tags)
        if self.count() == 0:
            return
        if self.currentIndex() != 0:
            self.setCurrentIndex(0)

    def all_versions_filtered_out(self):
        if self._items_by_id:
            return self.count() == 0
        return False

    def update_versions(
        self,
        version_items,
        current_version_id,
        task_tags_by_version_id,
    ):
        self.blockSignals(True)
        version_items = list(version_items)
        version_ids = [
            version_item.version_id
            for version_item in version_items
        ]
        if current_version_id not in version_ids and version_ids:
            current_version_id = version_ids[0]
        self._current_id = current_version_id

        self._versions_model.update_versions(
            version_items, task_tags_by_version_id
        )

        index = version_ids.index(current_version_id)
        if self.currentIndex() != index:
            self.setCurrentIndex(index)
        self.blockSignals(False)

    def _on_index_change(self):
        idx = self.currentIndex()
        value = self.itemData(idx)
        if value == self._current_id:
            return
        self._current_id = value
        self.value_changed.emit(self._product_id, value)


class VersionDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""

    version_changed = QtCore.Signal(str, str)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._editor_by_id: dict[str, VersionComboBox] = {}
        self._task_ids_filter = None
        self._statuses_filter = None
        self._version_tags_filter = None
        self._task_tags_filter = None

    def displayText(self, value, locale):
        if not isinstance(value, numbers.Integral):
            return "N/A"
        return format_version(value)

    def set_tasks_filter(self, task_ids):
        self._task_ids_filter = set(task_ids)
        for widget in self._editor_by_id.values():
            widget.set_tasks_filter(task_ids)

    def set_statuses_filter(self, status_names):
        if status_names is not None:
            status_names = set(status_names)
        self._statuses_filter = status_names
        for widget in self._editor_by_id.values():
            widget.set_statuses_filter(status_names)

    def set_version_tags_filter(self, tags):
        if tags is not None:
            tags = set(tags)
        self._version_tags_filter = tags
        for widget in self._editor_by_id.values():
            widget.set_version_tags_filter(tags)

    def set_task_tags_filter(self, tags):
        if tags is not None:
            tags = set(tags)
        self._task_tags_filter = tags
        for widget in self._editor_by_id.values():
            widget.set_task_tags_filter(tags)

    def paint(self, painter, option, index):
        fg_color = index.data(QtCore.Qt.ForegroundRole)
        if fg_color:
            if isinstance(fg_color, QtGui.QBrush):
                fg_color = fg_color.color()
            elif isinstance(fg_color, QtGui.QColor):
                pass
            else:
                fg_color = None

        if not fg_color:
            return super().paint(painter, option, index)

        if option.widget:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()

        style.drawControl(
            QtWidgets.QCommonStyle.CE_ItemViewItem,
            option,
            painter,
            option.widget
        )

        painter.save()

        text = self.displayText(
            index.data(QtCore.Qt.DisplayRole), option.locale
        )
        pen = painter.pen()
        pen.setColor(fg_color)
        painter.setPen(pen)

        text_rect = style.subElementRect(
            QtWidgets.QCommonStyle.SE_ItemViewItemText,
            option
        )
        text_margin = style.proxy().pixelMetric(
            QtWidgets.QCommonStyle.PM_FocusFrameHMargin,
            option,
            option.widget
        ) + 1

        painter.drawText(
            text_rect.adjusted(text_margin, 0, - text_margin, 0),
            option.displayAlignment,
            text
        )

        painter.restore()

    def createEditor(self, parent, option, index):
        product_id = index.data(PRODUCT_ID_ROLE)
        if not product_id:
            return

        item_id = uuid.uuid4().hex

        editor = VersionComboBox(product_id, parent)
        editor.setProperty("itemId", item_id)
        editor.setFocusPolicy(QtCore.Qt.NoFocus)

        editor.value_changed.connect(self._on_editor_change)
        editor.destroyed.connect(self._on_destroy)

        self._editor_by_id[item_id] = editor

        return editor

    def setEditorData(self, editor, index):
        editor.clear()

        # Current value of the index
        product_id = index.data(PRODUCT_ID_ROLE)
        version_id = index.data(VERSION_ID_ROLE)
        model = index.model()
        while hasattr(model, "sourceModel"):
            model = model.sourceModel()
        versions = model.get_version_items_by_product_id(product_id)
        task_tags_by_version_id = {
            version_item.version_id: model.get_task_tags_by_id(
                version_item.task_id
            )
            for version_item in versions
        }

        editor.update_versions(versions, version_id, task_tags_by_version_id)
        editor.set_tasks_filter(self._task_ids_filter)
        editor.set_task_tags_filter(self._task_tags_filter)
        editor.set_statuses_filter(self._statuses_filter)

    def setModelData(self, editor, model, index):
        """Apply the integer version back in the model"""

        version_id = editor.itemData(editor.currentIndex())
        model.setData(index, version_id, VERSION_NAME_EDIT_ROLE)

    def _on_editor_change(self, product_id, version_id):
        self.version_changed.emit(product_id, version_id)

    def _on_destroy(self, obj):
        item_id = obj.property("itemId")
        self._editor_by_id.pop(item_id, None)


class LoadedInSceneDelegate(QtWidgets.QStyledItemDelegate):
    """Delegate for Loaded in Scene state columns.

    Shows "Yes" or "No" for 1 or 0 values, or "N/A" for other values.
    Colorizes green or dark grey based on values.
    """

    def __init__(self, *args, **kwargs):
        super(LoadedInSceneDelegate, self).__init__(*args, **kwargs)
        self._colors = {
            1: QtGui.QColor(80, 170, 80),
            0: QtGui.QColor(90, 90, 90),
        }
        self._default_color = QtGui.QColor(90, 90, 90)

    def displayText(self, value, locale):
        if value == 0:
            return "No"
        elif value == 1:
            return "Yes"
        return "N/A"

    def initStyleOption(self, option, index):
        super(LoadedInSceneDelegate, self).initStyleOption(option, index)

        # Colorize based on value
        value = index.data(PRODUCT_IN_SCENE_ROLE)
        color = self._colors.get(value, self._default_color)
        option.palette.setBrush(QtGui.QPalette.Text, color)


class SiteSyncDelegate(QtWidgets.QStyledItemDelegate):
    """Paints icons and downloaded representation ration for both sites."""

    def paint(self, painter, option, index):
        super(SiteSyncDelegate, self).paint(painter, option, index)
        option = QtWidgets.QStyleOptionViewItem(option)
        option.showDecorationSelected = True

        active_icon = index.data(ACTIVE_SITE_ICON_ROLE)
        remote_icon = index.data(REMOTE_SITE_ICON_ROLE)

        availability_active = "{}/{}".format(
            index.data(SYNC_ACTIVE_SITE_AVAILABILITY),
            index.data(REPRESENTATIONS_COUNT_ROLE)
        )
        availability_remote = "{}/{}".format(
            index.data(SYNC_REMOTE_SITE_AVAILABILITY),
            index.data(REPRESENTATIONS_COUNT_ROLE)
        )

        if availability_active is None or availability_remote is None:
            return

        items_to_draw = [
            (value, icon)
            for value, icon in (
                (availability_active, active_icon),
                (availability_remote, remote_icon),
            )
            if icon
        ]
        if not items_to_draw:
            return

        icon_size = QtCore.QSize(24, 24)
        padding = 10
        pos_x = option.rect.x()

        item_width = int(option.rect.width() / len(items_to_draw))
        if item_width < 1:
            item_width = 0

        for value, icon in items_to_draw:
            item_rect = QtCore.QRect(
                pos_x,
                option.rect.y(),
                item_width,
                option.rect.height()
            )
            # Prepare pos_x for next item
            pos_x = item_rect.x() + item_rect.width()

            pixmap = icon.pixmap(icon.actualSize(icon_size))
            point = QtCore.QPoint(
                item_rect.x() + padding,
                item_rect.y() + ((item_rect.height() - pixmap.height()) * 0.5)
            )
            painter.drawPixmap(point, pixmap)

            icon_offset = icon_size.width() + (padding * 2)
            text_rect = QtCore.QRect(item_rect)
            text_rect.setLeft(text_rect.left() + icon_offset)
            if text_rect.width() < 1:
                continue

            painter.drawText(
                text_rect,
                option.displayAlignment,
                value
            )

    def displayText(self, value, locale):
        pass
