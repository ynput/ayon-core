"""List of placeholders that are in the current scene."""

from __future__ import annotations

from typing import Any, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.style import get_default_tools_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.ui.components import (
    AYButton,
    AYContainer,
    AYLabel,
    AYLineEdit,
    AYMenu,
    AYTreeView,
)
from ayon_core.ui.components.tree_view import TreeViewItemDelegate
from ayon_core.ui.style_types import get_ayon_style

from ..abstract import PlaceholderItemInfo, PlaceholderPluginItem

SCENE_IDENTIFIER_ROLE = QtCore.Qt.UserRole + 1
PLUGIN_IDENTIFIER_ROLE = QtCore.Qt.UserRole + 2
ORDER_ROLE = QtCore.Qt.UserRole + 3
LABEL_ROLE = QtCore.Qt.UserRole + 4
PENDING_ROLE = QtCore.Qt.UserRole + 5

# Order of the row of a placeholder that is being created, keeps it on top
PENDING_ORDER = -(2 ** 31)

# Put before the name of a placeholder with unsaved changes. Before, so
#   it stays visible when a long name is elided.
UNSAVED_MARK = "\u25cf "

DEFAULT_PLACEHOLDER_ICON = {
    "type": "material-symbols",
    "name": "extension",
    "color": get_default_tools_icon_color(),
}

CREATE_ICON = "add"
DELETE_ICON = "delete"
RUN_ICON = "play_arrow"
SELECT_ICON = "my_location"
REFRESH_ICON = "refresh"

# Horizontal padding inside of a cell, matches the padding of the header
#   labels so the values line up with their column titles.
CELL_PADDING = 8
COLUMN_PADDING = 2 * CELL_PADDING

ORDER_COLUMN = 0
LABEL_COLUMN = 1
TYPE_COLUMN = 2


def get_placeholder_icon(
    icon_def: Optional[dict[str, Any]]
) -> Optional[QtGui.QIcon]:
    """Icon of a placeholder plugin.

    Args:
        icon_def (Optional[dict[str, Any]]): Icon definition of the plugin.

    Returns:
        Optional[QtGui.QIcon]: Icon of the plugin, or the default placeholder
            icon when the plugin does not define a valid one.

    """
    icon = None
    if icon_def:
        icon = get_qt_icon(icon_def, default=None)
    if icon is None:
        icon = get_qt_icon(DEFAULT_PLACEHOLDER_ICON, default=None)
    return icon


def get_action_icon(icon_name: str) -> Optional[QtGui.QIcon]:
    """Material symbols icon used in menus.

    Args:
        icon_name (str): Name of material symbols icon.

    Returns:
        Optional[QtGui.QIcon]: Icon, None when the name is not available.

    """
    return get_qt_icon(
        {
            "type": "material-symbols",
            "name": icon_name,
            "color": get_default_tools_icon_color(),
        },
        default=None,
    )


class _PaddedItemDelegate(TreeViewItemDelegate):
    """Item delegate with more space between a cell edge and its text.

    The AYON tree view style keeps the text 2px from the cell edge, which
    squeezes short values, like the order, against the edge of the list.
    """

    def _tv_styles(self) -> dict[str, dict]:
        if self._styles_cache is None:
            styles = super()._tv_styles()
            base_style = dict(styles.get("base", {}))
            vertical_padding = base_style.get("item-padding", [1, 2])[0]
            base_style["item-padding"] = [vertical_padding, CELL_PADDING]
            self._styles_cache = dict(styles, base=base_style)
        return self._styles_cache


class AddPlaceholderButton(AYButton):
    """Button that starts creation of a placeholder.

    The placeholder type is picked from a menu when the host has more than
    one placeholder plugin, otherwise the only type is used right away.

    The button can be highlighted when adding a placeholder is the only
    thing to do, e.g. while the scene has none.

    Signals:
        create_requested: Create placeholder of plugin identifier (str).

    Args:
        text (str): Text of the button.
        parent (Optional[QtWidgets.QWidget]): Parent widget.
        variant (AYButton.Variants): Look of the button.

    """
    create_requested = QtCore.Signal(str)

    def __init__(
        self,
        text: str,
        parent: Optional[QtWidgets.QWidget] = None,
        variant: AYButton.Variants = AYButton.Variants.Surface,
    ):
        super().__init__(
            text,
            parent=parent,
            variant=variant,
            icon=CREATE_ICON,
            tooltip="Create a new placeholder",
        )
        self._default_variant = variant
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._highlighted = False
        self.setEnabled(False)
        self.clicked.connect(self._on_click)

    def set_plugin_items(
        self, plugin_items: list[PlaceholderPluginItem]
    ) -> None:
        """Set placeholder types that can be created.

        Args:
            plugin_items (list[PlaceholderPluginItem]): Available plugins.

        """
        self._plugin_items = list(plugin_items)
        self.setEnabled(bool(self._plugin_items))
        self._update_variant()

    def set_highlighted(self, highlighted: bool) -> None:
        """Show the button as the main action.

        Args:
            highlighted (bool): Use the filled look. Only applied when there
                is a placeholder type to create.

        """
        self._highlighted = highlighted
        self._update_variant()

    def is_highlighted(self) -> bool:
        """Button is shown as the main action.

        Returns:
            bool: Button uses the filled look.

        """
        return self._highlighted and bool(self._plugin_items)

    def _update_variant(self) -> None:
        if self.is_highlighted():
            self.set_variant(AYButton.Variants.Filled)
        else:
            self.set_variant(self._default_variant)

    def _on_click(self) -> None:
        if not self._plugin_items:
            return

        if len(self._plugin_items) == 1:
            self.create_requested.emit(self._plugin_items[0].identifier)
            return

        menu = AYMenu(self)
        for plugin_item in self._plugin_items:
            action = menu.addAction(plugin_item.label)
            action.setData(plugin_item.identifier)
            icon = get_placeholder_icon(plugin_item.icon)
            if icon is not None:
                action.setIcon(icon)

        action = menu.exec_(self.mapToGlobal(QtCore.QPoint(0, self.height())))
        if action is not None:
            self.create_requested.emit(action.data())


class PlaceholdersWidget(AYContainer):
    """Filterable list of placeholders with actions to manage them.

    Signals:
        selection_changed: Selected placeholder changed.
        create_requested: User wants to create a new placeholder of plugin
            identifier (str).
        select_in_scene_requested: User wants to select the placeholder in
            the host scene.
        refresh_requested: User wants to re-collect placeholders.

    """
    selection_changed = QtCore.Signal()
    create_requested = QtCore.Signal(str)
    select_in_scene_requested = QtCore.Signal()
    refresh_requested = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=4,
        )

        # --- Header ---
        header_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        title_label = AYLabel("Placeholders", parent=header_widget, bold=True)
        count_label = AYLabel(parent=header_widget, dim=True)
        create_btn = AddPlaceholderButton("Add", parent=header_widget)
        header_widget.add_widget(title_label)
        header_widget.add_widget(count_label)
        header_widget.addStretch(1)
        header_widget.add_widget(create_btn)

        # --- Filter ---
        filter_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=4,
        )
        filter_input = AYLineEdit(
            filter_widget,
            placeholder="Filter placeholders...",
            variant=AYLineEdit.Variants.Search_Field,
        )
        refresh_btn = AYButton(
            parent=filter_widget,
            variant=AYButton.Variants.Surface,
            icon=REFRESH_ICON,
            tooltip="Collect placeholders from the scene again",
        )
        # Height of a line edit depends on the font of the host, follow the
        #   height of the refresh button instead so the row lines up.
        filter_input.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored
        )
        filter_widget.add_widget(filter_input, stretch=1)
        filter_widget.add_widget(refresh_btn)

        # --- Placeholders ---
        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(["Order", "Placeholder", "Type"])

        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(model)
        proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        # Filter by placeholder label and by placeholder type
        proxy_model.setFilterKeyColumn(-1)
        # Always show placeholders in the order they are populated. Sort is
        #   stable, so placeholders with the same order keep the order they
        #   were collected in, which is the order they are populated in.
        proxy_model.setSortRole(ORDER_ROLE)
        proxy_model.sort(ORDER_COLUMN, QtCore.Qt.AscendingOrder)

        view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        view.setItemDelegate(
            _PaddedItemDelegate(
                parent=view,
                style_model=get_ayon_style().model,
                variant=AYTreeView.Variants.Low.value,
            )
        )
        view.setModel(proxy_model)
        view.setVisible(False)
        view.setIndentation(0)
        view.setRootIsDecorated(False)
        view.setAllColumnsShowFocus(True)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)

        header = view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(
            LABEL_COLUMN, QtWidgets.QHeaderView.Stretch
        )

        # Shown instead of the list, and its header, when the scene has no
        #   placeholders
        empty_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
        )
        empty_label = AYLabel(
            "No placeholders yet", parent=empty_widget, dim=True
        )
        empty_widget.add_widget(empty_label)
        empty_widget.layout().setAlignment(
            empty_label, QtCore.Qt.AlignCenter
        )

        # Filter sits close to the list it filters
        self.add_widget(header_widget)
        self.layout().addSpacing(4)
        self.add_widget(filter_widget)
        self.add_widget(view, stretch=1)
        self.add_widget(empty_widget, stretch=1)

        filter_input.textChanged.connect(self._on_filter_change)
        view.selection_changed.connect(self._on_selection_change)
        view.doubleClicked.connect(self._on_double_click)
        view.customContextMenuRequested.connect(self._on_context_menu)
        create_btn.create_requested.connect(self.create_requested)
        refresh_btn.clicked.connect(self.refresh_requested)

        self._model = model
        self._proxy_model = proxy_model
        self._view = view
        self._empty_widget = empty_widget
        self._filter_input = filter_input
        self._count_label = count_label
        self._create_btn = create_btn

        # Action support by plugin identifier
        self._select_support: dict[str, bool] = {}
        self._unsaved_identifier: Optional[str] = None
        self._pending_plugin_item: Optional[PlaceholderPluginItem] = None
        self._has_placeholders = False

    def set_placeholder_items(
        self, placeholder_items: list[PlaceholderItemInfo]
    ) -> None:
        """Fill the view with placeholders.

        Selection is kept when the previously selected placeholder is still
        available.

        Args:
            placeholder_items (list[PlaceholderItemInfo]): Placeholders to
                show.

        """
        selected_identifier = self.get_selected_identifier()

        root_item = self._model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        for placeholder_item in placeholder_items:
            order_item = QtGui.QStandardItem()
            order_item.setData(placeholder_item.order, QtCore.Qt.DisplayRole)
            label_item = QtGui.QStandardItem(placeholder_item.label)
            label_item.setData(placeholder_item.label, LABEL_ROLE)
            icon = get_placeholder_icon(placeholder_item.icon)
            if icon is not None:
                label_item.setIcon(icon)
            type_item = QtGui.QStandardItem(placeholder_item.plugin_label)

            tooltip = "{}\nType: {}\nScene identifier: {}".format(
                placeholder_item.label,
                placeholder_item.plugin_label,
                placeholder_item.scene_identifier,
            )
            for item in (order_item, label_item, type_item):
                item.setEditable(False)
                item.setToolTip(tooltip)
                item.setData(
                    placeholder_item.scene_identifier, SCENE_IDENTIFIER_ROLE
                )
                item.setData(
                    placeholder_item.plugin_identifier, PLUGIN_IDENTIFIER_ROLE
                )
                item.setData(placeholder_item.order, ORDER_ROLE)

            root_item.appendRow([order_item, label_item, type_item])

        self._count_label.setText(
            str(len(placeholder_items)) if placeholder_items else ""
        )
        self._has_placeholders = bool(placeholder_items)
        self._add_pending_row()
        self._update_view_visibility()
        self._update_unsaved_mark()
        self._resize_columns()

        if selected_identifier is not None:
            self.select_identifier(selected_identifier)

    def set_pending_item(
        self, plugin_item: Optional[PlaceholderPluginItem]
    ) -> None:
        """Show a row for a placeholder that is being created.

        The row is on top of the list and is selected when no other
        placeholder is, so the list shows what the editor is working on.

        Args:
            plugin_item (Optional[PlaceholderPluginItem]): Plugin of the new
                placeholder. None removes the row.

        """
        self._remove_pending_row()
        self._pending_plugin_item = plugin_item
        self._add_pending_row()
        self._update_view_visibility()
        self._resize_columns()
        if plugin_item is not None:
            self.select_identifier(None)

    def _remove_pending_row(self) -> None:
        for row in reversed(range(self._model.rowCount())):
            if self._model.item(row, LABEL_COLUMN).data(PENDING_ROLE):
                self._model.removeRow(row)

    def _add_pending_row(self) -> None:
        plugin_item = self._pending_plugin_item
        if plugin_item is None:
            return

        order_item = QtGui.QStandardItem()
        label_item = QtGui.QStandardItem("New placeholder")
        label_item.setData("New placeholder", LABEL_ROLE)
        icon = get_placeholder_icon(plugin_item.icon)
        if icon is not None:
            label_item.setIcon(icon)
        type_item = QtGui.QStandardItem(plugin_item.label)
        for item in (order_item, label_item, type_item):
            item.setEditable(False)
            item.setToolTip("Not created yet")
            item.setData(True, PENDING_ROLE)
            item.setData(PENDING_ORDER, ORDER_ROLE)
        self._model.appendRow([order_item, label_item, type_item])

    def _update_view_visibility(self) -> None:
        has_rows = (
            self._has_placeholders or self._pending_plugin_item is not None
        )
        self._view.setVisible(has_rows)
        self._empty_widget.setVisible(not has_rows)

    def set_unsaved_identifier(
        self, scene_identifier: Optional[str]
    ) -> None:
        """Mark the placeholder that has unsaved changes.

        Args:
            scene_identifier (Optional[str]): Scene identifier of the
                placeholder, None when no placeholder has unsaved changes.

        """
        if scene_identifier == self._unsaved_identifier:
            return
        self._unsaved_identifier = scene_identifier
        self._update_unsaved_mark()

    def _update_unsaved_mark(self) -> None:
        for row in range(self._model.rowCount()):
            item = self._model.item(row, LABEL_COLUMN)
            if item.data(PENDING_ROLE):
                continue
            label = item.data(LABEL_ROLE)
            is_unsaved = (
                self._unsaved_identifier is not None
                and item.data(SCENE_IDENTIFIER_ROLE)
                == self._unsaved_identifier
            )
            item.setText(UNSAVED_MARK + label if is_unsaved else label)

    def _resize_columns(self) -> None:
        """Fit "Order" and "Type" columns to their content."""
        header = self._view.header()
        font_metrics = self._view.fontMetrics()
        for column in (ORDER_COLUMN, TYPE_COLUMN):
            # Item delegate does not give a size hint based on the text
            text_width = max(
                (
                    font_metrics.horizontalAdvance(
                        str(self._model.index(row, column).data() or "")
                    )
                    for row in range(self._model.rowCount())
                ),
                default=0,
            )
            header.resizeSection(
                column,
                max(header.sectionSizeHint(column), text_width)
                + COLUMN_PADDING,
            )

    def set_add_highlighted(self, highlighted: bool) -> None:
        """Show the "Add" button as the main action.

        Args:
            highlighted (bool): Use the filled look.

        """
        self._create_btn.set_highlighted(highlighted)

    def set_plugin_items(
        self, plugin_items: list[PlaceholderPluginItem]
    ) -> None:
        """Set placeholder types that can be created and their actions.

        Args:
            plugin_items (list[PlaceholderPluginItem]): Available plugins.

        """
        self._create_btn.set_plugin_items(plugin_items)
        self._select_support = {
            plugin_item.identifier: plugin_item.select_supported
            for plugin_item in plugin_items
        }

    def get_selected_plugin_identifier(self) -> Optional[str]:
        """Plugin identifier of selected placeholder.

        Returns:
            Optional[str]: Plugin identifier of the selection.

        """
        for index in self._view.selectionModel().selectedIndexes():
            if index.data(PENDING_ROLE):
                return None
            return index.data(PLUGIN_IDENTIFIER_ROLE)
        return None

    def get_selected_identifier(self) -> Optional[str]:
        """Scene identifier of selected placeholder.

        Returns:
            Optional[str]: Selected scene identifier.

        """
        for index in self._view.selectionModel().selectedIndexes():
            return index.data(SCENE_IDENTIFIER_ROLE)
        return None

    def select_identifier(self, scene_identifier: Optional[str]) -> None:
        """Select placeholder by its scene identifier.

        Args:
            scene_identifier (Optional[str]): Scene identifier to select.
                None selects the placeholder that is being created, or
                clears the selection when there is none.

        """
        if scene_identifier is None:
            role, value = PENDING_ROLE, True
        else:
            role, value = SCENE_IDENTIFIER_ROLE, scene_identifier

        matches = self._proxy_model.match(
            self._proxy_model.index(0, 0),
            role,
            value,
            1,
            QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive,
        )
        if not matches:
            self._view.selectionModel().clearSelection()
            return

        index = matches[0]
        self._view.selectionModel().setCurrentIndex(
            index,
            QtCore.QItemSelectionModel.ClearAndSelect
            | QtCore.QItemSelectionModel.Rows
        )
        self._view.scrollTo(index)

    def _on_filter_change(self, text: str) -> None:
        self._proxy_model.setFilterFixedString(text)

    def _on_selection_change(self, *_args) -> None:
        self.selection_changed.emit()

    def _on_double_click(self, index: QtCore.QModelIndex) -> None:
        if index.data(PENDING_ROLE):
            return
        if self._select_support.get(index.data(PLUGIN_IDENTIFIER_ROLE)):
            self.select_in_scene_requested.emit()

    def _on_context_menu(self, point: QtCore.QPoint) -> None:
        index = self._view.indexAt(point)
        if not index.isValid() or index.data(PENDING_ROLE):
            return

        plugin_identifier = index.data(PLUGIN_IDENTIFIER_ROLE)

        menu = AYMenu(self._view)
        if self._select_support.get(plugin_identifier):
            action = menu.addAction("Select in scene")
            icon = get_action_icon(SELECT_ICON)
            if icon is not None:
                action.setIcon(icon)
            action.triggered.connect(self.select_in_scene_requested)

        if not menu.actions():
            return
        menu.exec_(self._view.viewport().mapToGlobal(point))
