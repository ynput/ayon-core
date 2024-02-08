import numbers

from ayon_core.client import (
    get_versions,
    get_hero_versions,
)
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
            return format_version(value, True)
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
        if item["version_document"]["type"] != "hero_version":
            assert isinstance(value, numbers.Integral), (
                "Version is not integer"
            )

        project_name = self.get_project_name()
        # Add all available versions to the editor
        parent_id = item["version_document"]["parent"]
        version_docs = [
            version_doc
            for version_doc in sorted(
                get_versions(project_name, subset_ids=[parent_id]),
                key=lambda item: item["name"]
            )
            if version_doc["data"].get("active", True)
        ]

        hero_versions = list(
            get_hero_versions(
                project_name,
                subset_ids=[parent_id],
                fields=["name", "data.tags", "version_id"]
            )
        )
        hero_version_doc = None
        if hero_versions:
            hero_version_doc = hero_versions[0]

        doc_for_hero_version = None

        selected = None
        items = []
        for version_doc in version_docs:
            version_tags = version_doc["data"].get("tags") or []
            if "deleted" in version_tags:
                continue

            if (
                hero_version_doc
                and doc_for_hero_version is None
                and hero_version_doc["version_id"] == version_doc["_id"]
            ):
                doc_for_hero_version = version_doc

            label = format_version(version_doc["name"])
            item = QtGui.QStandardItem(label)
            item.setData(version_doc, QtCore.Qt.UserRole)
            items.append(item)

            if version_doc["name"] == value:
                selected = item

        if hero_version_doc and doc_for_hero_version:
            version_name = doc_for_hero_version["name"]
            label = format_version(version_name, True)
            if isinstance(value, HeroVersionType):
                index = len(version_docs)
            hero_version_doc["name"] = HeroVersionType(version_name)

            item = QtGui.QStandardItem(label)
            item.setData(hero_version_doc, QtCore.Qt.UserRole)
            items.append(item)

        # Reverse items so latest versions be upper
        items = list(reversed(items))
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
