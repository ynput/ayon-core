import numbers

import ayon_api

from ayon_core.pipeline import HeroVersionType
from ayon_core.tools.utils.models import TreeModel
from ayon_core.tools.utils.lib import format_version

from qtpy import QtWidgets, QtCore, QtGui


class VersionDelegate(QtWidgets.QStyledItemDelegate):
    """A delegate that display version integer formatted as version string."""

    version_changed = QtCore.Signal()
    first_run = False
    lock = False

    def __init__(self, controller, *args, **kwargs):
        self._controller = controller
        super(VersionDelegate, self).__init__(*args, **kwargs)

    def get_project_name(self):
        return self._controller.get_current_project_name()

    def displayText(self, value, locale):
        if isinstance(value, HeroVersionType):
            return format_version(value)
        if not isinstance(value, numbers.Integral):
            # For cases where no version is resolved like NOT FOUND cases
            # where a representation might not exist in current database
            return

        return format_version(value)

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
            return super(VersionDelegate, self).paint(painter, option, index)

        if option.widget:
            style = option.widget.style()
        else:
            style = QtWidgets.QApplication.style()

        style.drawControl(
            QtWidgets.QStyle.CE_ItemViewItem,
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
            QtWidgets.QStyle.SE_ItemViewItemText,
            option
        )
        text_margin = style.proxy().pixelMetric(
            QtWidgets.QStyle.PM_FocusFrameHMargin, option, option.widget
        ) + 1

        painter.drawText(
            text_rect.adjusted(text_margin, 0, - text_margin, 0),
            option.displayAlignment,
            text
        )

        painter.restore()

    def createEditor(self, parent, option, index):
        item = index.data(TreeModel.ItemRole)
        if item.get("isGroup") or item.get("isMerged"):
            return

        editor = QtWidgets.QComboBox(parent)

        def commit_data():
            if not self.first_run:
                self.commitData.emit(editor)  # Update model data
                self.version_changed.emit()   # Display model data
        editor.currentIndexChanged.connect(commit_data)

        self.first_run = True
        self.lock = False

        return editor

    def setEditorData(self, editor, index):
        if self.lock:
            # Only set editor data once per delegation
            return

        editor.clear()

        # Current value of the index
        item = index.data(TreeModel.ItemRole)
        value = index.data(QtCore.Qt.DisplayRole)

        project_name = self.get_project_name()
        # Add all available versions to the editor
        product_id = item["version_entity"]["productId"]
        version_entities = list(sorted(
            ayon_api.get_versions(
                project_name, product_ids={product_id}, active=True
            ),
            key=lambda item: abs(item["version"])
        ))

        selected = None
        items = []
        is_hero_version = value < 0
        for version_entity in version_entities:
            version = version_entity["version"]
            label = format_version(version)
            item = QtGui.QStandardItem(label)
            item.setData(version_entity, QtCore.Qt.UserRole)
            items.append(item)

            if (
                version == value
                or is_hero_version and version < 0
            ):
                selected = item

        # Reverse items so latest versions be upper
        items.reverse()
        for item in items:
            editor.model().appendRow(item)

        index = 0
        if selected:
            index = selected.row()

        # Will trigger index-change signal
        editor.setCurrentIndex(index)
        self.first_run = False
        self.lock = True

    def setModelData(self, editor, model, index):
        """Apply the integer version back in the model"""
        version = editor.itemData(editor.currentIndex())
        model.setData(index, version["name"])
