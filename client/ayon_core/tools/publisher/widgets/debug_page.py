"""Publish debugger page of publisher tool.

Page allows to pause publishing on breakpoints or step through publish
    plugins one by one, inspect data of publish context and instances
    and execute python code with access to them.
"""
from __future__ import annotations

import os
import html
import json
import typing
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.style import get_objected_colors
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    PlaceholderPlainTextEdit,
    TreeView,
    get_qt_icon,
)

if typing.TYPE_CHECKING:
    from ayon_core.tools.publisher.abstract import (
        AbstractPublisherFrontend,
        PublishDebugDataItem,
        PublishDebugPluginItem,
        PublishDebugState,
        PublishDebugStepType,
        PublishDebugValue,
    )

PLUGIN_NAME_ROLE = QtCore.Qt.UserRole + 1
ITEM_ID_ROLE = QtCore.Qt.UserRole + 2
IS_CONTEXT_ROLE = QtCore.Qt.UserRole + 3
STATUS_ROLE = QtCore.Qt.UserRole + 4
VALUE_PATH_ROLE = QtCore.Qt.UserRole + 5
RAW_VALUE_ROLE = QtCore.Qt.UserRole + 6
TYPE_LABEL_ROLE = QtCore.Qt.UserRole + 8
# Value children can be loaded on demand
EXPANDABLE_ROLE = QtCore.Qt.UserRole + 10
# Item is placeholder for children which were not loaded yet
PLACEHOLDER_ROLE = QtCore.Qt.UserRole + 11
VALUE_LABEL_ROLE = QtCore.Qt.UserRole + 9
FILTER_ROLE = QtCore.Qt.UserRole + 7

NEW_COLOR = QtGui.QColor("#72d572")
CHANGED_COLOR = QtGui.QColor("#e6c75c")
PENDING_COLOR = QtGui.QColor("#5fb8e8")
ERROR_COLOR = QtGui.QColor("#e86060")

MAX_HISTORY = 100
# Prefix of attribute name in value path, must match backend
ATTRIBUTE_PREFIX = "."
# Max length of value preview of containers in data view
MAX_PREVIEW_LENGTH = 120


def is_publish_debugger_enabled() -> bool:
    """Debug page is available when 'AYON_DEBUG' is set to "1".

    Returns:
        bool: Show publish debugger in publisher.

    """
    return os.getenv("AYON_DEBUG") == "1"


def _get_icon(name: str) -> QtGui.QIcon:
    return get_qt_icon({"type": "material-symbols", "name": name})


def _get_status_color(status: str) -> Optional[QtGui.QColor]:
    if status == "new":
        return NEW_COLOR
    if status == "changed":
        return CHANGED_COLOR
    return None


def _get_disabled_color() -> QtGui.QColor:
    return get_objected_colors("font-disabled").get_qcolor()


def _get_mono_font() -> QtGui.QFont:
    return QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont)


def _path_to_code(root: str, path: tuple[str, ...]) -> str:
    """Convert path of value to python code accessing the value."""
    output = root
    for key in path:
        if key.startswith("[") and key.endswith("]") and key[1:-1].isdigit():
            output += key
        elif key.startswith(ATTRIBUTE_PREFIX):
            output += key
        else:
            output += f"[{json.dumps(key)}]"
    return output


def _get_index_path(index: QtCore.QModelIndex) -> tuple[str, ...]:
    # Qt bindings may convert tuple to list
    return tuple(index.data(VALUE_PATH_ROLE) or ())


class PluginsModel(QtGui.QStandardItemModel):
    """Publish plugins with checkable breakpoints."""
    breakpoint_changed = QtCore.Signal(str, bool)

    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setColumnCount(3)
        for idx, label in enumerate(("Plugin", "Order", "Type")):
            self.setHeaderData(idx, QtCore.Qt.Horizontal, label)

        self._items_by_name: dict[str, list[QtGui.QStandardItem]] = {}
        self._plugin_names: list[str] = []
        self._updating = False

        self.itemChanged.connect(self._on_item_change)

    def refresh(
        self,
        plugin_items: list[PublishDebugPluginItem],
        breakpoints: set[str],
    ) -> None:
        self._updating = True
        try:
            plugin_names = [item.name for item in plugin_items]
            if plugin_names != self._plugin_names:
                self._rebuild(plugin_items)

            disabled_color = _get_disabled_color()
            bold_font = QtGui.QFont()
            bold_font.setBold(True)
            pending_icon = _get_icon("play_arrow")
            for plugin_item in plugin_items:
                row_items = self._items_by_name[plugin_item.name]
                check_state = QtCore.Qt.Unchecked
                if plugin_item.name in breakpoints:
                    check_state = QtCore.Qt.Checked
                row_items[0].setCheckState(check_state)
                row_items[0].setIcon(
                    pending_icon if plugin_item.is_pending else QtGui.QIcon()
                )
                color = None
                if plugin_item.is_pending:
                    color = PENDING_COLOR
                elif plugin_item.processed:
                    color = disabled_color
                font = bold_font if plugin_item.is_pending else QtGui.QFont()
                for item in row_items:
                    item.setData(color, QtCore.Qt.ForegroundRole)
                    item.setData(font, QtCore.Qt.FontRole)
        finally:
            self._updating = False

    def update_breakpoints(self, breakpoints: set[str]) -> None:
        self._updating = True
        try:
            for name, row_items in self._items_by_name.items():
                check_state = QtCore.Qt.Unchecked
                if name in breakpoints:
                    check_state = QtCore.Qt.Checked
                row_items[0].setCheckState(check_state)
        finally:
            self._updating = False

    def _rebuild(self, plugin_items: list[PublishDebugPluginItem]) -> None:
        self.removeRows(0, self.rowCount())
        self._items_by_name = {}
        self._plugin_names = []
        root_item = self.invisibleRootItem()
        rows = []
        for plugin_item in plugin_items:
            tooltip = plugin_item.name
            if plugin_item.filepath:
                tooltip += f"\n{plugin_item.filepath}"

            label_item = QtGui.QStandardItem(plugin_item.label)
            label_item.setCheckable(True)
            order_item = QtGui.QStandardItem(f"{plugin_item.order:g}")
            type_item = QtGui.QStandardItem(
                "Instance" if plugin_item.is_instance_plugin else "Context"
            )
            row_items = [label_item, order_item, type_item]
            for item in row_items:
                item.setEditable(False)
                item.setToolTip(tooltip)
                item.setData(plugin_item.name, PLUGIN_NAME_ROLE)
            # Make sure plugin name can be used for filtering
            label_item.setData(
                f"{plugin_item.label} {plugin_item.name}",
                FILTER_ROLE,
            )
            self._items_by_name[plugin_item.name] = row_items
            self._plugin_names.append(plugin_item.name)
            rows.append(row_items)

        for row_items in rows:
            root_item.appendRow(row_items)

    def _on_item_change(self, item: QtGui.QStandardItem) -> None:
        if self._updating or item.column() != 0:
            return
        plugin_name = item.data(PLUGIN_NAME_ROLE)
        enabled = item.checkState() == QtCore.Qt.Checked
        self.breakpoint_changed.emit(plugin_name, enabled)


class PluginsWidget(QtWidgets.QWidget):
    """List of publish plugins where breakpoints can be set."""
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        header_widget = QtWidgets.QWidget(self)
        filter_input = PlaceholderLineEdit(header_widget)
        filter_input.setPlaceholderText("Filter plugins...")
        clear_btn = QtWidgets.QPushButton(header_widget)
        clear_btn.setIcon(_get_icon("delete_sweep"))
        clear_btn.setToolTip("Remove all breakpoints")

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(filter_input, 1)
        header_layout.addWidget(clear_btn, 0)

        model = PluginsModel(self)
        proxy = QtCore.QSortFilterProxyModel(self)
        proxy.setSourceModel(model)
        proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        proxy.setFilterRole(FILTER_ROLE)

        view = TreeView(self)
        view.setModel(proxy)
        view.setRootIsDecorated(False)
        view.setAllColumnsShowFocus(True)
        view.setTextElideMode(QtCore.Qt.ElideMiddle)
        view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        view.setToolTip(
            "Check a plugin to pause publishing before it is processed."
        )
        header = view.header()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents
        )
        header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents
        )
        header.setStretchLastSection(False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header_widget, 0)
        layout.addWidget(view, 1)

        filter_input.textChanged.connect(proxy.setFilterFixedString)
        clear_btn.clicked.connect(self._on_clear_click)
        model.breakpoint_changed.connect(self._on_breakpoint_change)
        view.customContextMenuRequested.connect(self._on_context_menu)

        self._controller = controller
        self._model = model
        self._proxy = proxy
        self._view = view

    def refresh(self) -> None:
        self._model.refresh(
            self._controller.get_publish_debug_plugin_items(),
            self._controller.get_publish_breakpoints(),
        )
        self.scroll_to_pending()

    def update_breakpoints(self) -> None:
        self._model.update_breakpoints(
            self._controller.get_publish_breakpoints()
        )

    def scroll_to_pending(self) -> None:
        state = self._controller.get_publish_debug_state()
        if not state.plugin_name:
            return
        for row in range(self._proxy.rowCount()):
            index = self._proxy.index(row, 0)
            if index.data(PLUGIN_NAME_ROLE) == state.plugin_name:
                self._view.scrollTo(
                    index, QtWidgets.QAbstractItemView.PositionAtCenter
                )
                break

    def _get_selected_plugin_names(self) -> list[str]:
        return [
            index.data(PLUGIN_NAME_ROLE)
            for index in self._view.selectionModel().selectedRows()
        ]

    def _on_breakpoint_change(self, plugin_name: str, enabled: bool) -> None:
        self._controller.set_publish_breakpoints([plugin_name], enabled)

    def _on_clear_click(self) -> None:
        self._controller.clear_publish_breakpoints()

    def _on_context_menu(self, point: QtCore.QPoint) -> None:
        plugin_names = self._get_selected_plugin_names()
        if not plugin_names:
            return
        menu = QtWidgets.QMenu(self._view)
        add_action = menu.addAction("Add breakpoint")
        remove_action = menu.addAction("Remove breakpoint")
        menu.addSeparator()
        copy_action = menu.addAction("Copy plugin name")
        result = menu.exec_(self._view.viewport().mapToGlobal(point))
        if result is add_action:
            self._controller.set_publish_breakpoints(plugin_names, True)
        elif result is remove_action:
            self._controller.set_publish_breakpoints(plugin_names, False)
        elif result is copy_action:
            QtWidgets.QApplication.clipboard().setText(
                "\n".join(plugin_names)
            )


class DataItemsWidget(QtWidgets.QListView):
    """List of context and instances."""
    selection_changed = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)

        model = QtGui.QStandardItemModel(self)
        self.setModel(model)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)

        self.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        self._model = model

    def get_selected_item_id(self) -> Optional[str]:
        for index in self.selectionModel().selectedIndexes():
            return index.data(ITEM_ID_ROLE)
        return None

    def set_items(
        self,
        items: list[PublishDebugDataItem],
        select_pending: bool,
    ) -> None:
        selected_id = self.get_selected_item_id()
        if select_pending:
            for item in items:
                if item.is_pending:
                    selected_id = item.id
                    break

        disabled_color = _get_disabled_color()
        pending_icon = _get_icon("play_arrow")
        new_items = []
        for item in items:
            label = item.label
            if not item.is_active:
                label += " (disabled)"
            q_item = QtGui.QStandardItem(label)
            q_item.setData(item.id, ITEM_ID_ROLE)
            q_item.setData(item.is_context, IS_CONTEXT_ROLE)
            color = _get_status_color(item.status)
            if item.is_pending:
                color = PENDING_COLOR
                q_item.setIcon(pending_icon)
            elif not item.is_active:
                color = disabled_color
            q_item.setData(color, QtCore.Qt.ForegroundRole)
            if item.is_context:
                font = QtGui.QFont()
                font.setItalic(True)
                q_item.setData(font, QtCore.Qt.FontRole)
            new_items.append(q_item)

        selection_model = self.selectionModel()
        selection_model.blockSignals(True)
        self._model.clear()
        root_item = self._model.invisibleRootItem()
        if new_items:
            root_item.appendRows(new_items)

        index_to_select = None
        for row in range(self._model.rowCount()):
            index = self._model.index(row, 0)
            if index.data(ITEM_ID_ROLE) == selected_id:
                index_to_select = index
                break

        if index_to_select is None and self._model.rowCount():
            index_to_select = self._model.index(0, 0)

        if index_to_select is not None:
            self.setCurrentIndex(index_to_select)
        selection_model.blockSignals(False)
        self.selection_changed.emit()

    def _on_selection_change(self) -> None:
        self.selection_changed.emit()


class DataProxyModel(QtCore.QSortFilterProxyModel):
    def __init__(self, parent: Optional[QtCore.QObject] = None) -> None:
        super().__init__(parent)
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterKeyColumn(0)
        self._changes_only = False

    def set_changes_only(self, changes_only: bool) -> None:
        if self._changes_only == changes_only:
            return
        self._changes_only = changes_only
        self.invalidateFilter()

    def filterAcceptsRow(
        self, source_row: int, source_parent: QtCore.QModelIndex
    ) -> bool:
        if self._changes_only:
            index = self.sourceModel().index(source_row, 0, source_parent)
            if not index.data(STATUS_ROLE):
                return False
        return super().filterAcceptsRow(source_row, source_parent)


def _get_type_label(value: PublishDebugValue) -> str:
    if value.length is None:
        return f"{{{value.type_name}}}"
    return f"{{{value.type_name}: {value.length}}}"


def _get_value_preview(value: PublishDebugValue, max_length: int) -> str:
    """Value label shown in data view, similar to python 'repr'.

    Containers show preview of their children, limited by length.
    """
    if value.children is None:
        if value.type_name == "str":
            return repr(value.value)
        return value.value.replace("\n", " ⏎ ")

    opening, closing = ("{", "}") if value.is_mapping else ("[", "]")
    parts = []
    length = 2
    for child in value.children:
        if child.key == "..." and not child.type_name:
            parts.append("...")
            break
        child_preview = _get_value_preview(child, max_length - length)
        if value.is_mapping:
            child_preview = f"{child.key!r}: {child_preview}"
        length += len(child_preview) + 2
        if length > max_length:
            parts.append("...")
            break
        parts.append(child_preview)
    return opening + ", ".join(parts) + closing


class DataValueDelegate(QtWidgets.QStyledItemDelegate):
    """Paint value row as 'key = {type} value' like python debuggers."""
    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        key_text = opt.text
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(
            QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget
        )

        text_rect = style.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, opt, widget
        )
        type_label = index.data(TYPE_LABEL_ROLE) or ""
        value_label = index.data(VALUE_LABEL_ROLE) or ""

        # Use palette of original option, 'initStyleOption' applies
        #   foreground role (status color) to the palette
        value_color = option.palette.color(QtGui.QPalette.Text)
        key_color = index.data(QtCore.Qt.ForegroundRole)
        if key_color is None:
            key_color = value_color
        muted_color = _get_disabled_color()

        segments = [(key_text, key_color)]
        if type_label:
            segments.append((" = ", muted_color))
            segments.append((type_label + " ", muted_color))
        else:
            segments.append(("  ", muted_color))
        segments.append((value_label, value_color))

        painter.save()
        painter.setFont(opt.font)
        metrics = QtGui.QFontMetrics(opt.font)
        pos_x = text_rect.left()
        right = text_rect.right()
        for text, color in segments:
            available = right - pos_x
            if available <= 0:
                break
            text = metrics.elidedText(
                text, QtCore.Qt.ElideRight, available
            )
            painter.setPen(color)
            painter.drawText(
                QtCore.QRect(
                    pos_x, text_rect.top(), available, text_rect.height()
                ),
                QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                text,
            )
            pos_x += metrics.horizontalAdvance(text)
        painter.restore()


class DataWidget(QtWidgets.QWidget):
    """Tree view of data of selected context or instance."""
    path_copied = QtCore.Signal(str)

    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        header_widget = QtWidgets.QWidget(self)
        filter_input = PlaceholderLineEdit(header_widget)
        filter_input.setPlaceholderText("Filter keys...")
        changes_only_checkbox = QtWidgets.QCheckBox(
            "Changes only", header_widget
        )
        changes_only_checkbox.setToolTip(
            "Show only values that were added or changed by plugins"
            " processed since the previous pause."
        )

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(filter_input, 1)
        header_layout.addWidget(changes_only_checkbox, 0)

        model = QtGui.QStandardItemModel(self)
        proxy = DataProxyModel(self)
        proxy.setSourceModel(model)

        view = TreeView(self)
        view.setModel(proxy)
        view.setHeaderHidden(True)
        view.setUniformRowHeights(True)
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        delegate = DataValueDelegate(view)
        view.setItemDelegate(delegate)

        legend_label = QtWidgets.QLabel(
            "Since previous pause:"
            f" <span style='color:{NEW_COLOR.name()}'>added</span>,"
            f" <span style='color:{CHANGED_COLOR.name()}'>changed</span>",
            self,
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header_widget, 0)
        layout.addWidget(view, 1)
        layout.addWidget(legend_label, 0)

        filter_input.textChanged.connect(self._on_filter_change)
        changes_only_checkbox.stateChanged.connect(
            self._on_changes_only_change
        )
        view.customContextMenuRequested.connect(self._on_context_menu)
        view.expanded.connect(self._on_expand)
        view.collapsed.connect(self._on_collapse)

        self._model = model
        self._proxy = proxy
        self._controller = controller
        self._view = view
        self._delegate = delegate
        self._filter_input = filter_input
        self._changes_only_checkbox = changes_only_checkbox

        self._item_id: Optional[str] = None
        self._root_code: str = "context.data"
        self._expanded_paths_by_item_id: dict[str, set[tuple[str, ...]]] = {}
        self._restoring_expanded = False

    def clear_expanded_state(self) -> None:
        self._expanded_paths_by_item_id = {}

    def set_item(self, item: Optional[PublishDebugDataItem]) -> None:
        # Keep scroll position if the same item is refreshed
        scroll_bar = self._view.verticalScrollBar()
        scroll_value = None
        if item is not None and item.id == self._item_id:
            scroll_value = scroll_bar.value()

        self._model.clear()

        self._item_id = None
        if item is None:
            return

        self._item_id = item.id
        self._root_code = (
            "context.data" if item.is_context else "instance.data"
        )
        root_item = self._model.invisibleRootItem()
        children = item.data.children or []
        rows = [self._create_item(child, ()) for child in children]
        if rows:
            root_item.appendRows(rows)

        self._restore_expanded()
        if self._filter_input.text():
            self._view.expandAll()
        if scroll_value is not None:
            scroll_bar.setValue(scroll_value)

    def _create_item(
        self, value: PublishDebugValue, parent_path: tuple[str, ...]
    ) -> QtGui.QStandardItem:
        key = value.key
        if value.is_attribute:
            key = ATTRIBUTE_PREFIX + key
        path = parent_path + (key, )
        type_label = ""
        if value.type_name:
            type_label = _get_type_label(value)
        value_label = _get_value_preview(value, MAX_PREVIEW_LENGTH)

        item = QtGui.QStandardItem(value.key)
        item.setEditable(False)
        item.setData(type_label, TYPE_LABEL_ROLE)
        item.setData(value_label, VALUE_LABEL_ROLE)
        item.setData(value.value, RAW_VALUE_ROLE)
        item.setData(value.status, STATUS_ROLE)
        item.setData(path, VALUE_PATH_ROLE)
        if value.children is None:
            item.setToolTip(html.escape(value.value))
        color = _get_status_color(value.status)
        if color is not None:
            item.setData(color, QtCore.Qt.ForegroundRole)

        if value.children:
            item.appendRows([
                self._create_item(child, path)
                for child in value.children
            ])

        elif value.is_expandable:
            # Placeholder child to show expand arrow, attributes are
            #   loaded on expand
            item.setData(True, EXPANDABLE_ROLE)
            placeholder_item = QtGui.QStandardItem("Loading...")
            placeholder_item.setEditable(False)
            placeholder_item.setData(True, PLACEHOLDER_ROLE)
            item.appendRow(placeholder_item)
        return item

    def _load_children(self, index: QtCore.QModelIndex) -> None:
        """Load children of expandable value if were not loaded yet."""
        source_index = self._proxy.mapToSource(index)
        item = self._model.itemFromIndex(source_index)
        if item is None or not item.data(EXPANDABLE_ROLE):
            return
        first_child = item.child(0)
        if first_child is None or not first_child.data(PLACEHOLDER_ROLE):
            return

        path = _get_index_path(source_index)
        children = self._controller.get_publish_debug_value_children(
            self._item_id, path
        )
        new_items = []
        if children is None:
            missing_item = QtGui.QStandardItem("Value is not available")
            missing_item.setEditable(False)
            new_items.append(missing_item)
        else:
            new_items = [
                self._create_item(child, path)
                for child in children
            ]

        item.removeRows(0, item.rowCount())
        if new_items:
            item.appendRows(new_items)

    def _expand_recursively(self, index: QtCore.QModelIndex) -> None:
        """Expand children without loading values on demand."""
        queue = [index]
        while queue:
            parent = queue.pop()
            if parent.data(EXPANDABLE_ROLE) and parent != index:
                continue
            self._view.setExpanded(parent, True)
            for row in range(self._proxy.rowCount(parent)):
                queue.append(self._proxy.index(row, 0, parent))

    def _get_expanded_paths(self) -> set[tuple[str, ...]]:
        if self._item_id is None:
            return set()
        return self._expanded_paths_by_item_id.setdefault(
            self._item_id, set()
        )

    def _restore_expanded(self) -> None:
        expanded_paths = self._get_expanded_paths()
        if not expanded_paths:
            return
        self._restoring_expanded = True
        try:
            queue = [QtCore.QModelIndex()]
            while queue:
                parent = queue.pop()
                for row in range(self._proxy.rowCount(parent)):
                    index = self._proxy.index(row, 0, parent)
                    if _get_index_path(index) in expanded_paths:
                        self._view.setExpanded(index, True)
                        queue.append(index)
        finally:
            self._restoring_expanded = False

    def _on_expand(self, index: QtCore.QModelIndex) -> None:
        self._load_children(index)
        if self._restoring_expanded or self._filter_input.text():
            return
        self._get_expanded_paths().add(_get_index_path(index))

    def _on_collapse(self, index: QtCore.QModelIndex) -> None:
        if self._filter_input.text():
            return
        self._get_expanded_paths().discard(_get_index_path(index))

    def _on_filter_change(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)
        if text:
            self._view.expandAll()
        else:
            self._view.collapseAll()
            self._restore_expanded()

    def _on_changes_only_change(self) -> None:
        self._proxy.set_changes_only(
            self._changes_only_checkbox.isChecked()
        )
        self._restore_expanded()

    def _on_context_menu(self, point: QtCore.QPoint) -> None:
        index = self._view.indexAt(point)
        if not index.isValid():
            return

        path = _get_index_path(index)
        menu = QtWidgets.QMenu(self._view)
        copy_value_action = menu.addAction("Copy value")
        copy_path_action = menu.addAction("Copy path as code")
        menu.addSeparator()
        expand_action = menu.addAction("Expand all children")
        collapse_action = menu.addAction("Collapse all")
        result = menu.exec_(self._view.viewport().mapToGlobal(point))
        clipboard = QtWidgets.QApplication.clipboard()
        if result is copy_value_action:
            clipboard.setText(index.data(RAW_VALUE_ROLE) or "")
        elif result is copy_path_action:
            code = _path_to_code(self._root_code, path)
            clipboard.setText(code)
            self.path_copied.emit(code)
        elif result is expand_action:
            self._expand_recursively(index)
        elif result is collapse_action:
            self._view.collapseAll()
            self._get_expanded_paths().clear()


class ConsoleInput(PlaceholderPlainTextEdit):
    """Code input. Enter executes, Shift+Enter adds new line."""
    execute_requested = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget) -> None:
        super().__init__(parent)
        self.setFont(_get_mono_font())
        self.setTabChangesFocus(False)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.setPlaceholderText(
            "Python code... Enter to run, Shift+Enter for new line,"
            " Up/Down for history"
        )
        self._history: list[str] = []
        self._history_index: Optional[int] = None

    def add_history(self, code: str) -> None:
        if self._history and self._history[-1] == code:
            return
        self._history.append(code)
        self._history = self._history[-MAX_HISTORY:]
        self._history_index = None

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if (
            key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)
            and not event.modifiers() & QtCore.Qt.ShiftModifier
        ):
            event.accept()
            self.execute_requested.emit()
            return

        if key == QtCore.Qt.Key_Tab:
            event.accept()
            self.insertPlainText("    ")
            return

        if (
            key in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down)
            and "\n" not in self.toPlainText()
            and self._history
        ):
            event.accept()
            self._move_history(-1 if key == QtCore.Qt.Key_Up else 1)
            return

        super().keyPressEvent(event)

    def _move_history(self, offset: int) -> None:
        index = self._history_index
        if index is None:
            index = len(self._history)
        index = max(0, min(len(self._history), index + offset))
        self._history_index = index
        text = ""
        if index < len(self._history):
            text = self._history[index]
        self.setPlainText(text)
        self.moveCursor(QtGui.QTextCursor.End)


class ConsoleWidget(QtWidgets.QWidget):
    """Execute python code with access to publish data."""
    code_executed = QtCore.Signal()

    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        output_widget = QtWidgets.QPlainTextEdit(self)
        output_widget.setReadOnly(True)
        output_widget.setFont(_get_mono_font())
        output_widget.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        output_widget.setPlaceholderText(
            "Variables: 'context', 'instance' (selected instance),"
            " 'instances', 'plugin' (plugin to be processed next),"
            " 'create_context'. Assigned variables are kept until reset."
        )

        input_widget = QtWidgets.QWidget(self)
        code_input = ConsoleInput(input_widget)
        metrics = code_input.fontMetrics()
        code_input.setFixedHeight(int(metrics.height() * 3.5))

        btns_widget = QtWidgets.QWidget(input_widget)
        run_btn = QtWidgets.QPushButton(btns_widget)
        run_btn.setIcon(_get_icon("terminal"))
        run_btn.setToolTip("Run code (Enter)")
        clear_btn = QtWidgets.QPushButton(btns_widget)
        clear_btn.setIcon(_get_icon("clear_all"))
        clear_btn.setToolTip("Clear output")

        btns_layout = QtWidgets.QVBoxLayout(btns_widget)
        btns_layout.setContentsMargins(0, 0, 0, 0)
        btns_layout.addWidget(run_btn, 0)
        btns_layout.addWidget(clear_btn, 0)
        btns_layout.addStretch(1)

        input_layout = QtWidgets.QHBoxLayout(input_widget)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.addWidget(code_input, 1)
        input_layout.addWidget(btns_widget, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(output_widget, 1)
        layout.addWidget(input_widget, 0)

        code_input.execute_requested.connect(self._execute)
        run_btn.clicked.connect(self._execute)
        clear_btn.clicked.connect(output_widget.clear)

        self._controller = controller
        self._output_widget = output_widget
        self._code_input = code_input
        self._instance_id: Optional[str] = None

    def set_instance_id(self, instance_id: Optional[str]) -> None:
        self._instance_id = instance_id

    def insert_code(self, code: str) -> None:
        self._code_input.insertPlainText(code)
        self._code_input.setFocus()

    def _append_output(
        self, text: str, color: Optional[QtGui.QColor] = None
    ) -> None:
        cursor = self._output_widget.textCursor()
        cursor.movePosition(QtGui.QTextCursor.End)
        text_format = QtGui.QTextCharFormat()
        if color is not None:
            text_format.setForeground(color)
        if not self._output_widget.document().isEmpty():
            text = "\n" + text
        cursor.insertText(text, text_format)
        self._output_widget.setTextCursor(cursor)
        self._output_widget.ensureCursorVisible()

    def _execute(self) -> None:
        code = self._code_input.toPlainText()
        if not code.strip():
            return
        self._code_input.add_history(code)
        self._code_input.clear()

        echo = "\n".join(
            ("... " if idx else ">>> ") + line
            for idx, line in enumerate(code.splitlines())
        )
        self._append_output(echo, _get_disabled_color())
        result = self._controller.publish_debug_execute(
            code, self._instance_id
        )
        output = result.output.rstrip("\n")
        if output:
            color = None if result.success else ERROR_COLOR
            self._append_output(output, color)
        self.code_executed.emit()


class PublishDebugWidget(QtWidgets.QFrame):
    """Publish debugger page.

    +--------------------------------------------------------------------+
    | <State label>                     <Continue> <Step> <Step plugin>  |
    +---------------+------------+---------------------------------------+
    | <Plugins>     | <Context>  | <Data of selected context/instance>   |
    |               | <Instances>|                                       |
    +---------------+------------+---------------------------------------+
    | <Console>                                                          |
    +--------------------------------------------------------------------+
    """
    step_requested = QtCore.Signal(str)

    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        # Header with state and buttons
        header_widget = QtWidgets.QWidget(self)
        state_label = QtWidgets.QLabel(header_widget)
        state_label.setTextFormat(QtCore.Qt.RichText)

        continue_btn = QtWidgets.QPushButton("Continue", header_widget)
        continue_btn.setIcon(_get_icon("resume"))
        continue_btn.setToolTip(
            "Continue publishing until next breakpoint"
        )
        step_btn = QtWidgets.QPushButton("Step", header_widget)
        step_btn.setIcon(_get_icon("step_into"))
        step_btn.setToolTip(
            "Process next plugin on one instance (or context) and pause"
        )
        step_plugin_btn = QtWidgets.QPushButton("Step plugin", header_widget)
        step_plugin_btn.setIcon(_get_icon("step_over"))
        step_plugin_btn.setToolTip(
            "Process next plugin on all its instances and pause"
        )

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(state_label, 1)
        header_layout.addWidget(continue_btn, 0)
        header_layout.addWidget(step_btn, 0)
        header_layout.addWidget(step_plugin_btn, 0)

        # Content
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)

        top_splitter = QtWidgets.QSplitter(
            QtCore.Qt.Horizontal, main_splitter
        )
        plugins_widget = PluginsWidget(controller, top_splitter)
        data_items_widget = DataItemsWidget(top_splitter)
        data_widget = DataWidget(controller, top_splitter)
        top_splitter.addWidget(plugins_widget)
        top_splitter.addWidget(data_items_widget)
        top_splitter.addWidget(data_widget)
        top_splitter.setStretchFactor(0, 3)
        top_splitter.setStretchFactor(1, 2)
        top_splitter.setStretchFactor(2, 5)

        console_widget = ConsoleWidget(controller, main_splitter)

        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(console_widget)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(header_widget, 0)
        layout.addWidget(main_splitter, 1)

        continue_btn.clicked.connect(self._on_continue_click)
        step_btn.clicked.connect(self._on_step_click)
        step_plugin_btn.clicked.connect(self._on_step_plugin_click)
        data_items_widget.selection_changed.connect(
            self._on_data_item_selection_change
        )
        data_widget.path_copied.connect(console_widget.insert_code)
        console_widget.code_executed.connect(self._on_code_executed)

        controller.register_event_callback(
            "publish.reset.finished", self._on_publish_reset
        )
        controller.register_event_callback(
            "publish.process.started", self._on_publish_start
        )
        controller.register_event_callback(
            "publish.process.stopped", self._on_publish_stop
        )
        controller.register_event_callback(
            "publish.debug.breakpoints.changed",
            self._on_breakpoints_change
        )

        self._controller = controller
        self._state_label = state_label
        self._continue_btn = continue_btn
        self._step_btn = step_btn
        self._step_plugin_btn = step_plugin_btn
        self._plugins_widget = plugins_widget
        self._data_items_widget = data_items_widget
        self._data_widget = data_widget
        self._console_widget = console_widget

        self._data_items_by_id: dict[str, PublishDebugDataItem] = {}
        self._refresh_needed = True
        self._select_pending = False
        # Publishing can be started (e.g. instances have valid context)
        self._start_allowed = True

    def set_start_allowed(self, allowed: bool) -> None:
        """Set if publishing can be started from the debug page.

        Args:
            allowed (bool): Publishing can be started.

        """
        if self._start_allowed == allowed:
            return
        self._start_allowed = allowed
        self._update_state()

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._refresh_needed:
            self._refresh()

    def _refresh(self) -> None:
        self._refresh_needed = False
        self._update_state()
        self._plugins_widget.refresh()
        self._refresh_data()

    def _refresh_data(self) -> None:
        items = self._controller.get_publish_debug_data_items()
        self._data_items_by_id = {item.id: item for item in items}
        select_pending, self._select_pending = self._select_pending, False
        self._data_items_widget.set_items(items, select_pending)

    def _update_state(self) -> None:
        state: PublishDebugState = (
            self._controller.get_publish_debug_state()
        )
        is_running = self._controller.publish_is_running()
        has_started = self._controller.publish_has_started()
        can_continue = (
            not is_running
            and self._controller.publish_can_continue()
            and (has_started or self._start_allowed)
        )
        for btn in (
            self._continue_btn,
            self._step_btn,
            self._step_plugin_btn,
        ):
            btn.setEnabled(can_continue)

        if is_running:
            text = "Publishing..."
        elif state.is_paused:
            reason = "breakpoint" if state.pause_reason == "breakpoint" else (
                "step"
            )
            text = (
                f"Paused ({reason}) before"
                f" <b>{html.escape(state.plugin_label or '')}</b>"
                f" on <b>{html.escape(state.item_label or '')}</b>"
            )
        elif not has_started and not self._start_allowed:
            text = "Publishing can't be started, Publish button is disabled."
        elif not has_started:
            text = (
                "Check plugins to add breakpoints,"
                " then Publish or Step through plugins."
            )
        elif self._controller.publish_has_finished():
            text = "Publishing finished"
        elif can_continue:
            text = "Publishing paused"
        else:
            text = "Publishing stopped"
        self._state_label.setText(text)

    def _on_publish_reset(self) -> None:
        self._data_widget.clear_expanded_state()
        # Always refresh data on reset, so first pause can show changes
        self._update_state()
        self._plugins_widget.refresh()
        self._refresh_data()
        self._refresh_needed = False

    def _on_publish_start(self) -> None:
        self._update_state()

    def _on_publish_stop(self) -> None:
        self._select_pending = True
        if self.isVisible():
            self._refresh()
        else:
            self._refresh_needed = True
            self._update_state()

    def _on_breakpoints_change(self) -> None:
        self._plugins_widget.update_breakpoints()

    def _on_code_executed(self) -> None:
        self._refresh_data()

    def _on_data_item_selection_change(self) -> None:
        item_id = self._data_items_widget.get_selected_item_id()
        item = self._data_items_by_id.get(item_id)
        self._data_widget.set_item(item)
        instance_id = None
        if item is not None and not item.is_context:
            instance_id = item.id
        self._console_widget.set_instance_id(instance_id)

    def _request_step(self, step_type: PublishDebugStepType) -> None:
        self.step_requested.emit(step_type)

    def _on_continue_click(self) -> None:
        self._request_step("continue")

    def _on_step_click(self) -> None:
        self._request_step("item")

    def _on_step_plugin_click(self) -> None:
        self._request_step("plugin")
