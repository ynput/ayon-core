from __future__ import annotations

import os
import uuid
from typing import Generator

import arrow
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import style
from ayon_core.lib import get_launcher_local_dir
from ayon_core.pipeline.publish import PublishReport
from ayon_core.resources import get_ayon_icon_filepath
from ayon_core.tools import resources
from ayon_core.tools.utils import (
    IconButton,
    paint_image_with_color
)

from ayon_core.tools.utils.delegates import PrettyTimeDelegate

if __package__:
    from .widgets import PublishReportViewerWidget
else:
    from widgets import PublishReportViewerWidget


ITEM_ID_ROLE = QtCore.Qt.UserRole + 1
ITEM_CREATED_AT_ROLE = QtCore.Qt.UserRole + 2


def get_reports_dir():
    """Root directory where publish reports are stored for next session.

    Returns:
        str: Path to directory where reports are stored.
    """

    report_dir = get_launcher_local_dir("publish_report_viewer")
    os.makedirs(report_dir, exist_ok=True)
    return report_dir


class PublishReportItem:
    """Report item representing one file in report directory."""

    def __init__(
        self,
        report: PublishReport | None,
        report_path: str | None,
    ) -> str:
        label_changed = False
        if report is None:
            created_at_obj = arrow.utcnow()
            report_id = uuid.uuid4().hex
        else:
            created_at_obj = arrow.get(report.created_at).to("local")
            label = report.label
            if not label:
                date_str = created_at_obj.strftime("%Y-%m-%d %H:%M:%S")
                report.label = date_str
                label_changed = True
            report_id = report.id

        self.report_id = report_id
        self.report_path = report_path
        self.report = report
        self.created_at = float(created_at_obj.float_timestamp)

        self._label_changed = label_changed

    @classmethod
    def from_filepath(
        cls, filepath: str, report_path: str | None = None
    ) -> "PublishReportItem":
        """Create report item from file path.

        Args:
            filepath (str): Path to report file.

        """
        report = None
        new_label = None
        try:
            report = PublishReport.from_filepath(filepath)
            if report_path is None:
                report_path = os.path.join(
                    get_reports_dir(), f"{report.id}.json"
                )
            label = report.label
            if not label:
                new_label = os.path.splitext(os.path.basename(filepath))[0]

        except Exception as exc:
            import traceback
            import sys
            traceback.print_exception(*sys.exc_info())
            print(f"Failed to load report from file: {filepath}. {exc}")

        obj = cls(report, report_path)
        if new_label:
            obj.label = new_label
        return obj

    @property
    def id(self):
        """Publish report id.

        Returns:
            str: Publish report id.

        """
        return self.report_id

    def get_label(self) -> str:
        """Publish report label.

        Returns:
            str: Publish report label showed in UI.

        """
        if self.report is None:
            return "!!! Failed to load !!!"
        return self.report.label

    def set_label(self, label: str) -> None:
        """Set publish report label.

        Args:
            label (str): New publish report label.

        """
        if self.report is None:
            return

        if self.report.label == label:
            return

        self.report.label = label
        self._label_changed = True

    label = property(get_label, set_label)

    def save(self):
        """Save publish report to file."""
        if self.report_path is None or self.report is None:
            return

        save = False
        if (
            self._label_changed
            or not os.path.exists(self.report_path)
        ):
            save = True

        if not save:
            return

        self.report.store_to_file(self.report_path)

        self._label_changed = False

    def remove_file(self) -> None:
        """Remove report file."""
        if self.report_path is None:
            return

        if os.path.exists(self.report_path):
            os.remove(self.report_path)


class PublisherReportHandler:
    """Class handling storing publish report items."""

    def __init__(self):
        self._reports_loaded = False
        self._reports_by_id: dict[str, PublishReportItem] = {}

    def reset(self):
        self._reports_loaded = False
        self._reports_by_id = {}

    def iter_reports(self) -> Generator[PublishReportItem, None, None]:
        self._load_reports()
        for report in self._reports_by_id.values():
            yield report

    def get_item_by_id(self, item_id: str) -> PublishReportItem | None:
        """Get report item by id.

        Args:
            item_id (str): Report item id.

        Returns:
            PublishReportItem | None: Report item or None if not found.
        """
        self._load_reports()
        return self._reports_by_id.get(item_id)

    def remove_report_item(self, item_id: str) -> None:
        """Remove report item by id.

        Remove from cache and also remove the file with the content.

        Args:
            item_id (str): Report item id.
        """

        item = self._reports_by_id.pop(item_id, None)
        if item is None:
            return

        try:
            item.remove_file()
        except Exception:
            pass

    def _load_reports(self) -> None:
        if self._reports_loaded:
            return

        reports_by_id = {}
        report_dir = get_reports_dir()
        for filename in os.listdir(report_dir):
            ext = os.path.splitext(filename)[-1]
            if ext == ".json":
                continue
            filepath = os.path.join(report_dir, filename)
            item = PublishReportItem.from_filepath(
                filepath, report_path=filepath
            )
            reports_by_id[item.id] = item

        self._reports_loaded = True
        self._reports_by_id = reports_by_id


class LoadedFilesModel(QtGui.QStandardItemModel):
    header_labels = ("Reports", "Created")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Column count must be set before setting header data
        self.setColumnCount(len(self.header_labels))
        for col, label in enumerate(self.header_labels):
            self.setHeaderData(col, QtCore.Qt.Horizontal, label)

        self._items_by_id = {}
        self._report_items_by_id = {}

        self._handler = PublisherReportHandler()

        self._loading_registry = False

    def refresh(self):
        root_item = self.invisibleRootItem()
        if root_item.rowCount() > 0:
            root_item.removeRows(0, root_item.rowCount())
        self._items_by_id = {}

        self._handler.reset()

        new_items = []
        for report_item in self._handler.iter_reports():
            item = self._create_item(report_item)
            self._items_by_id[report_item.id] = item
            new_items.append(item)

        if new_items:
            root_item = self.invisibleRootItem()
            root_item.appendRows(new_items)

    def data(self, index, role=None):
        if role is None:
            role = QtCore.Qt.DisplayRole

        col = index.column()
        if col == 1:
            if role in (
                QtCore.Qt.DisplayRole, QtCore.Qt.InitialSortOrderRole
            ):
                role = ITEM_CREATED_AT_ROLE

        if col != 0:
            index = self.index(index.row(), 0, index.parent())

        return super().data(index, role)

    def setData(self, index, value, role=None):
        if role is None:
            role = QtCore.Qt.EditRole

        if role == QtCore.Qt.EditRole:
            item_id = index.data(ITEM_ID_ROLE)
            report_item = self._handler.get_item_by_id(item_id)
            if report_item is not None:
                report_item.set_label(value)
                report_item.save()
                value = report_item.label

        return super().setData(index, value, role)

    def flags(self, index):
        # Allow editable flag only for first column
        if index.column() > 0:
            return QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
        return super().flags(index)

    def _create_item(self, report_item):
        if report_item.id in self._items_by_id:
            return None

        item = QtGui.QStandardItem(report_item.label)
        item.setColumnCount(self.columnCount())
        item.setData(report_item.id, ITEM_ID_ROLE)
        item.setData(report_item.created_at, ITEM_CREATED_AT_ROLE)

        return item

    def add_filepaths(self, filepaths):
        if not filepaths:
            return

        if isinstance(filepaths, str):
            filepaths = [filepaths]

        filtered_paths = []
        for filepath in filepaths:
            normalized_path = os.path.normpath(filepath)
            if (
                os.path.exists(normalized_path)
                and normalized_path not in filtered_paths
            ):
                filtered_paths.append(normalized_path)

        if not filtered_paths:
            return

        new_items = []
        for normalized_path in filtered_paths:
            report_item = PublishReportItem.from_filepath(normalized_path)
            if report_item is None:
                continue

            # Skip already added report items
            # QUESTION: Should we replace existing or skip the item?
            if report_item.id in self._items_by_id:
                continue

            item = self._create_item(report_item)
            if item is None:
                continue

            new_items.append(item)
            report_item.save()
            self._items_by_id[report_item.id] = item

        if new_items:
            root_item = self.invisibleRootItem()
            root_item.appendRows(new_items)

    def remove_item_by_id(self, item_id):
        self._handler.remove_report_item(item_id)

        item = self._items_by_id.pop(item_id, None)
        if item is not None:
            parent = self.invisibleRootItem()
            parent.removeRow(item.row())

    def get_report_by_id(self, item_id):
        report_item = self._report_items_by_id.get(item_id)
        if report_item:
            return report_item
        return None


class LoadedFilesView(QtWidgets.QTreeView):
    selection_changed = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setEditTriggers(
            QtWidgets.QAbstractItemView.EditKeyPressed
            | QtWidgets.QAbstractItemView.SelectedClicked
            | QtWidgets.QAbstractItemView.DoubleClicked
        )
        self.setIndentation(0)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)

        model = LoadedFilesModel()
        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(model)
        self.setModel(proxy_model)

        time_delegate = PrettyTimeDelegate()
        self.setItemDelegateForColumn(1, time_delegate)

        self.sortByColumn(1, QtCore.Qt.AscendingOrder)

        remove_btn = IconButton(self)
        remove_icon_path = resources.get_icon_path("delete")
        loaded_remove_image = QtGui.QImage(remove_icon_path)
        pix = paint_image_with_color(loaded_remove_image, QtCore.Qt.white)
        icon = QtGui.QIcon(pix)
        remove_btn.setIcon(icon)

        model.rowsInserted.connect(self._on_rows_inserted)
        remove_btn.clicked.connect(self._on_remove_clicked)
        self.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )

        self._model = model
        self._proxy_model = proxy_model
        self._time_delegate = time_delegate
        self._remove_btn = remove_btn

    def showEvent(self, event):
        super().showEvent(event)
        self._model.refresh()
        header = self.header()
        header.resizeSections(QtWidgets.QHeaderView.ResizeToContents)
        self._update_remove_btn()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_remove_btn()

    def add_filepaths(self, filepaths):
        self._model.add_filepaths(filepaths)
        self._fill_selection()

    def remove_item_by_id(self, item_id):
        self._model.remove_item_by_id(item_id)
        self._fill_selection()

    def get_current_report(self):
        index = self.currentIndex()
        item_id = index.data(ITEM_ID_ROLE)
        return self._model.get_report_by_id(item_id)

    def refresh(self):
        self._model.refresh()
        self._fill_selection()

    def _update_remove_btn(self):
        viewport = self.viewport()
        height = viewport.height() + self.header().height()
        pos_x = viewport.width() - self._remove_btn.width() - 5
        pos_y = height - self._remove_btn.height() - 5
        self._remove_btn.move(max(0, pos_x), max(0, pos_y))

    def _on_rows_inserted(self):
        header = self.header()
        header.resizeSections(QtWidgets.QHeaderView.ResizeToContents)
        self._update_remove_btn()

    def _on_selection_change(self):
        self.selection_changed.emit()

    def _on_remove_clicked(self):
        index = self.currentIndex()
        item_id = index.data(ITEM_ID_ROLE)
        self.remove_item_by_id(item_id)

    def _fill_selection(self):
        index = self.currentIndex()
        if index.isValid():
            return

        model = self.model()
        index = model.index(0, 0)
        if index.isValid():
            self.setCurrentIndex(index)


class LoadedFilesWidget(QtWidgets.QWidget):
    report_changed = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)

        self.setAcceptDrops(True)

        view = LoadedFilesView(self)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view, 1)

        view.selection_changed.connect(self._on_report_change)

        self._view = view

    def dragEnterEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()

    def dragLeaveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            filepaths = []
            for url in mime_data.urls():
                filepath = url.toLocalFile()
                if os.path.exists(filepath):
                    filepaths.append(filepath)
            self._add_filepaths(filepaths)
        event.accept()

    def refresh(self):
        self._view.refresh()

    def get_current_report(self):
        return self._view.get_current_report()

    def _on_report_change(self):
        self.report_changed.emit()

    def _add_filepaths(self, filepaths):
        self._view.add_filepaths(filepaths)


class PublishReportViewerWindow(QtWidgets.QWidget):
    default_width = 1200
    default_height = 600

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Publish report viewer")
        icon = QtGui.QIcon(get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        body = QtWidgets.QSplitter(self)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        body.setOrientation(QtCore.Qt.Horizontal)

        loaded_files_widget = LoadedFilesWidget(body)
        main_widget = PublishReportViewerWidget(body)

        body.addWidget(loaded_files_widget)
        body.addWidget(main_widget)
        body.setStretchFactor(0, 70)
        body.setStretchFactor(1, 65)

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(body, 1)

        loaded_files_widget.report_changed.connect(self._on_report_change)

        self._loaded_files_widget = loaded_files_widget
        self._main_widget = main_widget

        self.resize(self.default_width, self.default_height)
        self.setStyleSheet(style.load_stylesheet())

    def refresh(self):
        self._loaded_files_widget.refresh()

    def set_report(self, report_data):
        self._main_widget.set_report(report_data)

    def _on_report_change(self):
        report = self._loaded_files_widget.get_current_report()
        self.set_report(report)
