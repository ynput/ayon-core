from math import ceil
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.utils import NiceCheckbox, ElideLabel

# from ayon_core.tools.utils import DeselectableTreeView
from .constants import (
    ITEM_ID_ROLE,
    ITEM_IS_GROUP_ROLE
)
from .delegates import GroupItemDelegate
from .model import (
    InstancesModel,
    InstanceProxyModel,
    PluginsModel,
    PluginProxyModel
)
from .report_items import PublishReport

FILEPATH_ROLE = QtCore.Qt.UserRole + 1
TRACEBACK_ROLE = QtCore.Qt.UserRole + 2
IS_DETAIL_ITEM_ROLE = QtCore.Qt.UserRole + 3


class PluginLoadReportModel(QtGui.QStandardItemModel):
    def __init__(self):
        super().__init__()
        self._traceback_by_filepath = {}
        self._items_by_filepath = {}
        self._is_active = True
        self._need_refresh = False

    def set_active(self, is_active):
        if self._is_active is is_active:
            return
        self._is_active = is_active
        self._update_items()

    def set_report(self, report):
        self._need_refresh = True
        if report is None:
            self._traceback_by_filepath.clear()
            self._update_items()
            return

        filepaths = set(report.crashed_plugin_paths.keys())
        to_remove = set(self._traceback_by_filepath) - filepaths
        for filepath in filepaths:
            self._traceback_by_filepath[filepath] = (
                report.crashed_plugin_paths[filepath]
            )

        for filepath in to_remove:
            self._traceback_by_filepath.pop(filepath)
        self._update_items()

    def _update_items(self):
        if not self._is_active or not self._need_refresh:
            return
        parent = self.invisibleRootItem()
        if not self._traceback_by_filepath:
            parent.removeRows(0, parent.rowCount())
            return

        new_items = []
        new_items_by_filepath = {}
        to_remove = (
            set(self._items_by_filepath) - set(self._traceback_by_filepath)
        )
        for filepath in self._traceback_by_filepath:
            if filepath in self._items_by_filepath:
                continue
            item = QtGui.QStandardItem(filepath)
            new_items.append(item)
            new_items_by_filepath[filepath] = item
            self._items_by_filepath[filepath] = item

        if new_items:
            parent.appendRows(new_items)

        for filepath, item in new_items_by_filepath.items():
            traceback_txt = self._traceback_by_filepath[filepath]
            detail_item = QtGui.QStandardItem()
            detail_item.setData(filepath, FILEPATH_ROLE)
            detail_item.setData(traceback_txt, TRACEBACK_ROLE)
            detail_item.setData(True, IS_DETAIL_ITEM_ROLE)
            item.appendRow(detail_item)

        for filepath in to_remove:
            item = self._items_by_filepath.pop(filepath)
            parent.removeRow(item.row())


class DetailWidget(QtWidgets.QTextEdit):
    def __init__(self, text, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.setReadOnly(True)
        self.setHtml(text)
        self.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)
        self.setWordWrapMode(
            QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere
        )

    def sizeHint(self):
        content_margins = (
            self.contentsMargins().top()
            + self.contentsMargins().bottom()
        )
        size = self.document().documentLayout().documentSize().toSize()
        size.setHeight(size.height() + content_margins)
        return size


class PluginLoadReportWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        view = QtWidgets.QTreeView(self)
        view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        view.setTextElideMode(QtCore.Qt.ElideLeft)
        view.setHeaderHidden(True)
        view.setAlternatingRowColors(True)
        view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

        model = PluginLoadReportModel()
        view.setModel(model)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view, 1)

        view.expanded.connect(self._on_expand)

        self._view = view
        self._model = model
        self._widgets_by_filepath = {}

    def set_active(self, is_active):
        self._model.set_active(is_active)

    def set_report(self, report):
        self._widgets_by_filepath = {}
        self._model.set_report(report)

    def showEvent(self, event):
        super().showEvent(event)
        self._update_widgets_size_hints()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_widgets_size_hints()

    def _on_expand(self, index):
        for row in range(self._model.rowCount(index)):
            child_index = self._model.index(row, index.column(), index)
            self._create_widget(child_index)

    def _update_widgets_size_hints(self):
        for item in self._widgets_by_filepath.values():
            widget, index = item
            if not widget.isVisible():
                continue
            self._model.setData(
                index, widget.sizeHint(), QtCore.Qt.SizeHintRole
            )

    def _create_widget(self, index):
        if not index.data(IS_DETAIL_ITEM_ROLE):
            return

        filepath = index.data(FILEPATH_ROLE)
        if filepath in self._widgets_by_filepath:
            return

        traceback_txt = index.data(TRACEBACK_ROLE)
        detail_text = (
            "<b>Filepath:</b><br/>"
            "{}<br/><br/>"
            "<b>Traceback:</b><br/>"
            "{}"
        ).format(filepath, traceback_txt.replace("\n", "<br/>"))
        widget = DetailWidget(detail_text, self)
        self._view.setIndexWidget(index, widget)
        self._widgets_by_filepath[filepath] = (widget, index)


class ZoomPlainText(QtWidgets.QPlainTextEdit):
    min_point_size = 1.0
    max_point_size = 200.0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        anim_timer = QtCore.QTimer()
        anim_timer.setInterval(20)

        anim_timer.timeout.connect(self._scaling_callback)

        self._anim_timer = anim_timer
        self._scheduled_scalings = 0
        self._point_size = None

    def wheelEvent(self, event):
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers != QtCore.Qt.ControlModifier:
            super().wheelEvent(event)
            return

        if hasattr(event, "angleDelta"):
            delta = event.angleDelta().y()
        else:
            delta = event.delta()
        degrees = float(delta) / 8
        steps = int(ceil(degrees / 5))
        self._scheduled_scalings += steps
        if (self._scheduled_scalings * steps < 0):
            self._scheduled_scalings = steps

        self._anim_timer.start()

    def _scaling_callback(self):
        if self._scheduled_scalings == 0:
            self._anim_timer.stop()
            return

        factor = 1.0 + (self._scheduled_scalings / 300)
        font = self.font()

        if self._point_size is None:
            point_size = font.pointSizeF()
        else:
            point_size = self._point_size

        point_size *= factor
        min_hit = False
        max_hit = False
        if point_size < self.min_point_size:
            point_size = self.min_point_size
            min_hit = True
        elif point_size > self.max_point_size:
            point_size = self.max_point_size
            max_hit = True

        self._point_size = point_size

        font.setPointSizeF(point_size)
        # Using 'self.setFont(font)' would not be propagated when stylesheets
        #   are applied on this widget
        self.setStyleSheet("font-size: {}pt".format(font.pointSize()))

        if (
            (max_hit and self._scheduled_scalings > 0)
            or (min_hit and self._scheduled_scalings < 0)
        ):
            self._scheduled_scalings = 0

        elif self._scheduled_scalings > 0:
            self._scheduled_scalings -= 1
        else:
            self._scheduled_scalings += 1


class DetailsWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        output_widget = ZoomPlainText(self)
        output_widget.setObjectName("PublishLogConsole")
        output_widget.setTextInteractionFlags(QtCore.Qt.TextBrowserInteraction)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(output_widget)

        self._is_active = True
        self._need_refresh = False
        self._output_widget = output_widget
        self._report_item = None
        self._instance_filter = set()
        self._plugin_filter = set()

    def clear(self):
        self._output_widget.setPlainText("")

    def set_active(self, is_active):
        if self._is_active is is_active:
            return
        self._is_active = is_active
        self._update_logs()

    def set_report(self, report):
        self._report_item = report
        self._plugin_filter = set()
        self._instance_filter = set()
        self._need_refresh = True
        self._update_logs()

    def set_plugin_filter(self, plugin_filter):
        self._plugin_filter = plugin_filter
        self._need_refresh = True
        self._update_logs()

    def set_instance_filter(self, instance_filter):
        self._instance_filter = instance_filter
        self._need_refresh = True
        self._update_logs()

    def _update_logs(self):
        if not self._is_active or not self._need_refresh:
            return

        if not self._report_item:
            self._output_widget.setPlainText("")
            return

        filtered_logs = []
        for log in self._report_item.logs:
            if (
                self._instance_filter
                and log.instance_id not in self._instance_filter
            ):
                continue

            if (
                self._plugin_filter
                and log.plugin_id not in self._plugin_filter
            ):
                continue
            filtered_logs.append(log)

        self._set_logs(filtered_logs)

    def _set_logs(self, logs):
        lines = []
        for log in logs:
            if log["type"] == "record":
                message = "{}: {}".format(log["levelname"], log["msg"])

                lines.append(message)
                exc_info = log["exc_info"]
                if exc_info:
                    lines.append(exc_info)

            elif log["type"] == "error":
                lines.append(log["traceback"])

            else:
                print(log["type"])

        text = "\n".join(lines)
        self._output_widget.setPlainText(text)


class PluginDetailsWidget(QtWidgets.QWidget):
    def __init__(self, plugin_item, parent):
        super().__init__(parent)

        content_widget = QtWidgets.QFrame(self)
        content_widget.setObjectName("PluginDetailsContent")

        plugin_label_widget = QtWidgets.QLabel(content_widget)
        plugin_label_widget.setObjectName("PluginLabel")
        plugin_label_widget.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )

        plugin_path_label = QtWidgets.QLabel("File Path:")
        plugin_path_widget = ElideLabel(content_widget)
        plugin_path_widget.set_elide_mode(QtCore.Qt.ElideLeft)

        plugin_families_label = QtWidgets.QLabel("Families:")
        plugin_families_widget = QtWidgets.QLabel(content_widget)
        plugin_families_widget.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )
        plugin_families_widget.setWordWrap(True)

        for label_widget in (
            plugin_path_label,
            plugin_families_label,
        ):
            label_widget.setObjectName("PluginFormLabel")

        plugin_doc_widget = QtWidgets.QLabel(content_widget)
        plugin_doc_widget.setWordWrap(True)
        plugin_doc_widget.setTextInteractionFlags(
            QtCore.Qt.TextBrowserInteraction
        )

        plugin_label = plugin_item.label or plugin_item.name
        if plugin_item.plugin_type:
            plugin_label += " ({})".format(
                plugin_item.plugin_type.capitalize()
            )
        plugin_label_widget.setText(plugin_label)
        # plugin_type_widget.setText(plugin_item.plugin_type or "N/A")
        plugin_path_widget.setText(plugin_item.filepath or "N/A")
        plugin_path_widget.setToolTip(plugin_item.filepath or None)
        plugin_families_widget.setText(str(plugin_item.families or "N/A"))
        plugin_doc_widget.setText(plugin_item.docstring or "N/A")

        row = 0

        content_layout = QtWidgets.QGridLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setColumnStretch(0, 0)
        content_layout.setColumnStretch(1, 1)

        content_layout.addWidget(plugin_label_widget, row, 0, 1, 2)
        row += 1

        # Hide docstring if it is empty
        if plugin_item.docstring:
            content_layout.addWidget(plugin_doc_widget, row, 0, 1, 2)
            row += 1
        else:
            plugin_doc_widget.setVisible(False)

        content_layout.addWidget(plugin_path_label, row, 0)
        content_layout.addWidget(plugin_path_widget, row, 1)
        row += 1

        content_layout.addWidget(plugin_families_label, row, 0)
        content_layout.addWidget(plugin_families_widget, row, 1)
        row += 1

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(content_widget, 0)


class PluginsDetailsWidget(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)

        scroll_content_widget = QtWidgets.QWidget(scroll_area)

        scroll_area.setWidget(scroll_content_widget)

        content_widget = QtWidgets.QWidget(scroll_content_widget)

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)

        scroll_content_layout = QtWidgets.QVBoxLayout(scroll_content_widget)
        scroll_content_layout.setContentsMargins(0, 0, 0, 0)
        scroll_content_layout.addWidget(content_widget, 0)
        scroll_content_layout.addStretch(1)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area, 1)

        self._scroll_area = scroll_area
        self._content_layout = content_layout
        self._content_widget = content_widget

        self._widgets_by_plugin_id = {}
        self._stretch_item_index = 0

        self._is_active = True
        self._need_refresh = False

        self._report_item = None
        self._plugin_filter = set()
        self._plugin_ids = None

    def set_active(self, is_active):
        if self._is_active is is_active:
            return
        self._is_active = is_active
        self._update_widgets()

    def set_plugin_filter(self, plugin_filter):
        self._need_refresh = True
        self._plugin_filter = plugin_filter
        self._update_widgets()

    def set_report(self, report):
        self._plugin_ids = None
        self._plugin_filter = set()
        self._need_refresh = True
        self._report_item = report
        self._update_widgets()

    def _get_plugin_ids(self):
        if self._plugin_ids is not None:
            return self._plugin_ids

        # Clear layout and clear widgets
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setVisible(False)
                widget.deleteLater()

        self._widgets_by_plugin_id.clear()

        plugin_ids = []
        if self._report_item is not None:
            plugin_ids = list(self._report_item.plugins_id_order)
        self._plugin_ids = plugin_ids
        return plugin_ids

    def _update_widgets(self):
        if not self._is_active or not self._need_refresh:
            return

        self._need_refresh = False

        for plugin_id in self._get_plugin_ids():
            widget = self._widgets_by_plugin_id.get(plugin_id)
            if widget is None:
                plugin_item = self._report_item.plugins_items_by_id[plugin_id]
                widget = PluginDetailsWidget(plugin_item, self._content_widget)
                self._widgets_by_plugin_id[plugin_id] = widget
                self._content_layout.addWidget(widget, 0)

            widget.setVisible(
                not self._plugin_filter
                or plugin_id in self._plugin_filter
            )


class DeselectableTreeView(QtWidgets.QTreeView):
    """A tree view that deselects on clicking on an empty area in the view"""

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        clear_selection = False
        if not index.isValid():
            modifiers = QtWidgets.QApplication.keyboardModifiers()
            if modifiers == QtCore.Qt.ShiftModifier:
                return
            elif modifiers == QtCore.Qt.ControlModifier:
                return
            clear_selection = True
        else:
            indexes = self.selectedIndexes()
            if len(indexes) == 1 and index in indexes:
                clear_selection = True

        if clear_selection:
            # clear the selection
            self.clearSelection()
            # clear the current index
            self.setCurrentIndex(QtCore.QModelIndex())
            event.accept()
            return

        QtWidgets.QTreeView.mousePressEvent(self, event)


class DetailsPopup(QtWidgets.QDialog):
    closed = QtCore.Signal()

    def __init__(self, parent, center_widget):
        super().__init__(parent)
        self.setWindowTitle("Report Details")
        layout = QtWidgets.QHBoxLayout(self)

        self._center_widget = center_widget
        self._first_show = True
        self._layout = layout

    def showEvent(self, event):
        layout = self.layout()
        layout.insertWidget(0, self._center_widget)
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.resize(700, 400)

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()


class PublishReportViewerWidget(QtWidgets.QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)

        instances_model = InstancesModel()
        instances_proxy = InstanceProxyModel()
        instances_proxy.setSourceModel(instances_model)

        plugins_model = PluginsModel()
        plugins_proxy = PluginProxyModel()
        plugins_proxy.setSourceModel(plugins_model)

        removed_instances_check = NiceCheckbox(parent=self)
        removed_instances_check.setChecked(instances_proxy.ignore_removed)
        removed_instances_label = QtWidgets.QLabel(
            "Hide removed instances", self
        )

        removed_instances_layout = QtWidgets.QHBoxLayout()
        removed_instances_layout.setContentsMargins(0, 0, 0, 0)
        removed_instances_layout.addWidget(removed_instances_check, 0)
        removed_instances_layout.addWidget(removed_instances_label, 1)

        instances_view = DeselectableTreeView(self)
        instances_view.setObjectName("PublishDetailViews")
        instances_view.setModel(instances_proxy)
        instances_view.setIndentation(0)
        instances_view.setHeaderHidden(True)
        instances_view.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        instances_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        instances_view.setExpandsOnDoubleClick(False)

        instances_delegate = GroupItemDelegate(instances_view)
        instances_view.setItemDelegate(instances_delegate)

        skipped_plugins_check = NiceCheckbox(parent=self)
        skipped_plugins_check.setChecked(plugins_proxy.ignore_skipped)
        skipped_plugins_label = QtWidgets.QLabel("Hide skipped plugins", self)

        skipped_plugins_layout = QtWidgets.QHBoxLayout()
        skipped_plugins_layout.setContentsMargins(0, 0, 0, 0)
        skipped_plugins_layout.addWidget(skipped_plugins_check, 0)
        skipped_plugins_layout.addWidget(skipped_plugins_label, 1)

        plugins_view = DeselectableTreeView(self)
        plugins_view.setObjectName("PublishDetailViews")
        plugins_view.setModel(plugins_proxy)
        plugins_view.setIndentation(0)
        plugins_view.setHeaderHidden(True)
        plugins_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        plugins_view.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers)
        plugins_view.setExpandsOnDoubleClick(False)

        plugins_delegate = GroupItemDelegate(plugins_view)
        plugins_view.setItemDelegate(plugins_delegate)

        details_widget = QtWidgets.QWidget(self)
        details_tab_widget = QtWidgets.QTabWidget(details_widget)
        details_popup_btn = QtWidgets.QPushButton("PopUp", details_widget)

        details_layout = QtWidgets.QVBoxLayout(details_widget)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(details_tab_widget, 1)
        details_layout.addWidget(details_popup_btn, 0)

        details_popup = DetailsPopup(self, details_tab_widget)

        logs_text_widget = DetailsWidget(details_tab_widget)
        plugin_load_report_widget = PluginLoadReportWidget(details_tab_widget)
        plugins_details_widget = PluginsDetailsWidget(details_tab_widget)

        plugin_load_report_widget.set_active(False)
        plugins_details_widget.set_active(False)

        details_tab_widget.addTab(logs_text_widget, "Logs")
        details_tab_widget.addTab(plugins_details_widget, "Plugins Details")
        details_tab_widget.addTab(
            plugin_load_report_widget, "Crashed plugins"
        )

        middle_widget = QtWidgets.QWidget(self)
        middle_layout = QtWidgets.QGridLayout(middle_widget)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        # Row 1
        middle_layout.addLayout(removed_instances_layout, 0, 0)
        middle_layout.addLayout(skipped_plugins_layout, 0, 1)
        # Row 2
        middle_layout.addWidget(instances_view, 1, 0)
        middle_layout.addWidget(plugins_view, 1, 1)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(middle_widget, 0)
        layout.addWidget(details_widget, 1)

        details_tab_widget.currentChanged.connect(self._on_tab_change)
        instances_view.selectionModel().selectionChanged.connect(
            self._on_instance_change
        )
        instances_view.clicked.connect(self._on_instance_view_clicked)
        plugins_view.clicked.connect(self._on_plugin_view_clicked)
        plugins_view.selectionModel().selectionChanged.connect(
            self._on_plugin_change
        )

        skipped_plugins_check.stateChanged.connect(
            self._on_skipped_plugin_check
        )
        removed_instances_check.stateChanged.connect(
            self._on_removed_instances_check
        )
        details_popup_btn.clicked.connect(self._on_details_popup)
        details_popup.closed.connect(self._on_popup_close)

        self._current_tab_idx = 0
        self._ignore_selection_changes = False
        self._report_item = None
        self._logs_text_widget = logs_text_widget
        self._plugin_load_report_widget = plugin_load_report_widget
        self._plugins_details_widget = plugins_details_widget

        self._removed_instances_check = removed_instances_check
        self._instances_view = instances_view
        self._instances_model = instances_model
        self._instances_proxy = instances_proxy

        self._instances_delegate = instances_delegate
        self._plugins_delegate = plugins_delegate

        self._skipped_plugins_check = skipped_plugins_check
        self._plugins_view = plugins_view
        self._plugins_model = plugins_model
        self._plugins_proxy = plugins_proxy

        self._details_widget = details_widget
        self._details_tab_widget = details_tab_widget
        self._details_popup = details_popup

    def _on_instance_view_clicked(self, index):
        if not index.isValid() or not index.data(ITEM_IS_GROUP_ROLE):
            return

        if self._instances_view.isExpanded(index):
            self._instances_view.collapse(index)
        else:
            self._instances_view.expand(index)

    def _on_plugin_view_clicked(self, index):
        if not index.isValid() or not index.data(ITEM_IS_GROUP_ROLE):
            return

        if self._plugins_view.isExpanded(index):
            self._plugins_view.collapse(index)
        else:
            self._plugins_view.expand(index)

    def set_report_data(self, report_data):
        report = PublishReport(report_data)
        self.set_report(report)

    def set_report(self, report):
        self._ignore_selection_changes = True

        self._report_item = report

        self._instances_model.set_report(report)
        self._plugins_model.set_report(report)
        self._logs_text_widget.set_report(report)
        self._plugin_load_report_widget.set_report(report)
        self._plugins_details_widget.set_report(report)

        self._ignore_selection_changes = False

        self._instances_view.expandAll()
        self._plugins_view.expandAll()

    def _on_tab_change(self, new_idx):
        if self._current_tab_idx == new_idx:
            return
        old_widget = self._details_tab_widget.widget(self._current_tab_idx)
        new_widget = self._details_tab_widget.widget(new_idx)
        self._current_tab_idx = new_idx
        old_widget.set_active(False)
        new_widget.set_active(True)

    def _on_instance_change(self, *_args):
        if self._ignore_selection_changes:
            return

        instance_ids = set()
        for index in self._instances_view.selectedIndexes():
            if index.isValid():
                instance_ids.add(index.data(ITEM_ID_ROLE))

        self._logs_text_widget.set_instance_filter(instance_ids)

    def _on_plugin_change(self, *_args):
        if self._ignore_selection_changes:
            return

        plugin_ids = set()
        for index in self._plugins_view.selectedIndexes():
            if index.isValid():
                plugin_ids.add(index.data(ITEM_ID_ROLE))

        self._logs_text_widget.set_plugin_filter(plugin_ids)
        self._plugins_details_widget.set_plugin_filter(plugin_ids)

    def _on_skipped_plugin_check(self):
        self._plugins_proxy.set_ignore_skipped(
            self._skipped_plugins_check.isChecked()
        )

    def _on_removed_instances_check(self):
        self._instances_proxy.set_ignore_removed(
            self._removed_instances_check.isChecked()
        )

    def _on_details_popup(self):
        self._details_widget.setVisible(False)
        self._details_popup.show()

    def _on_popup_close(self):
        self._details_widget.setVisible(True)
        layout = self._details_widget.layout()
        layout.insertWidget(0, self._details_tab_widget)

    def close_details_popup(self):
        if self._details_popup.isVisible():
            self._details_popup.close()
