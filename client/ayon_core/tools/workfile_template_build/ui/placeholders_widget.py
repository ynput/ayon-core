"""List of placeholders that are in the current scene."""

from __future__ import annotations

from typing import Any, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.style import get_default_tools_icon_color
from ayon_core.tools.utils import get_qt_icon
from ayon_core.ui.components import (
    AYButton,
    AYContainer,
    AYLineEdit,
    AYMenu,
    AYTreeView,
)

from ..abstract import PlaceholderItemInfo, PlaceholderPluginItem

SCENE_IDENTIFIER_ROLE = QtCore.Qt.UserRole + 1
PLUGIN_IDENTIFIER_ROLE = QtCore.Qt.UserRole + 2
ORDER_ROLE = QtCore.Qt.UserRole + 3

DEFAULT_PLACEHOLDER_ICON = {
    "type": "material-symbols",
    "name": "extension",
    "color": get_default_tools_icon_color(),
}

CREATE_ICON = "add"
DELETE_ICON = "delete"
SELECT_ICON = "my_location"
REFRESH_ICON = "refresh"

COLUMN_PADDING = 16


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


class PlaceholdersWidget(AYContainer):
    """Filterable list of placeholders with actions to manage them.

    Signals:
        selection_changed: Selected placeholder changed.
        create_requested: User wants to create a new placeholder.
        delete_requested: User wants to delete selected placeholder.
        select_in_scene_requested: User wants to select the placeholder in
            the host scene.
        refresh_requested: User wants to re-collect placeholders.

    """
    selection_changed = QtCore.Signal()
    create_requested = QtCore.Signal()
    delete_requested = QtCore.Signal()
    select_in_scene_requested = QtCore.Signal()
    refresh_requested = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=6,
        )

        filter_input = AYLineEdit(
            self,
            placeholder="Filter placeholders...",
            variant=AYLineEdit.Variants.Search_Field,
        )

        model = QtGui.QStandardItemModel()
        model.setHorizontalHeaderLabels(["Placeholder", "Type", "Order"])

        proxy_model = QtCore.QSortFilterProxyModel()
        proxy_model.setSourceModel(model)
        proxy_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        # Filter by placeholder label and by placeholder type
        proxy_model.setFilterKeyColumn(-1)

        view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        view.setModel(proxy_model)
        view.setIndentation(0)
        view.setRootIsDecorated(False)
        view.setSortingEnabled(True)
        view.setAllColumnsShowFocus(True)
        view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        view.sortByColumn(2, QtCore.Qt.AscendingOrder)

        header = view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

        btns_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        create_btn = AYButton(
            "Add",
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon=CREATE_ICON,
            tooltip="Create a new placeholder",
        )
        delete_btn = AYButton(
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon=DELETE_ICON,
        )
        select_btn = AYButton(
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon=SELECT_ICON,
        )
        refresh_btn = AYButton(
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon=REFRESH_ICON,
            tooltip="Collect placeholders from the scene again",
        )
        btns_widget.add_widget(create_btn, stretch=1)
        btns_widget.add_widget(delete_btn)
        btns_widget.add_widget(select_btn)
        btns_widget.add_widget(refresh_btn)

        self.add_widget(filter_input)
        self.add_widget(view, stretch=1)
        self.add_widget(btns_widget)

        filter_input.textChanged.connect(self._on_filter_change)
        view.selection_changed.connect(self._on_selection_change)
        view.customContextMenuRequested.connect(self._on_context_menu)
        create_btn.clicked.connect(self.create_requested)
        delete_btn.clicked.connect(self.delete_requested)
        select_btn.clicked.connect(self.select_in_scene_requested)
        refresh_btn.clicked.connect(self.refresh_requested)

        self._model = model
        self._proxy_model = proxy_model
        self._view = view
        self._filter_input = filter_input

        self._create_btn = create_btn
        self._delete_btn = delete_btn
        self._select_btn = select_btn

        # Action support by plugin identifier
        self._delete_support: dict[str, bool] = {}
        self._select_support: dict[str, bool] = {}

        self._update_btns_state()

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
            label_item = QtGui.QStandardItem(placeholder_item.label)
            icon = get_placeholder_icon(placeholder_item.icon)
            if icon is not None:
                label_item.setIcon(icon)
            label_item.setToolTip(
                "{}\nType: {}\nScene identifier: {}".format(
                    placeholder_item.label,
                    placeholder_item.plugin_label,
                    placeholder_item.scene_identifier,
                )
            )
            type_item = QtGui.QStandardItem(placeholder_item.plugin_label)
            order_item = QtGui.QStandardItem()
            order_item.setData(placeholder_item.order, QtCore.Qt.DisplayRole)

            for item in (label_item, type_item, order_item):
                item.setEditable(False)
                item.setData(
                    placeholder_item.scene_identifier, SCENE_IDENTIFIER_ROLE
                )
                item.setData(
                    placeholder_item.plugin_identifier, PLUGIN_IDENTIFIER_ROLE
                )
                item.setData(placeholder_item.order, ORDER_ROLE)

            root_item.appendRow([label_item, type_item, order_item])

        self._resize_columns()

        if selected_identifier is not None:
            self.select_identifier(selected_identifier)

    def _resize_columns(self) -> None:
        """Fit "Type" and "Order" columns to their content."""
        header = self._view.header()
        for column in (1, 2):
            width = max(
                self._view.sizeHintForColumn(column),
                header.sectionSizeHint(column),
            )
            # Size hints don't count with padding of the item delegate
            header.resizeSection(column, width + COLUMN_PADDING)

    def set_plugin_items(
        self, plugin_items: list[PlaceholderPluginItem]
    ) -> None:
        """Store which actions each placeholder plugin implements.

        Args:
            plugin_items (list[PlaceholderPluginItem]): Available plugins.

        """
        self._delete_support = {
            plugin_item.identifier: plugin_item.delete_supported
            for plugin_item in plugin_items
        }
        self._select_support = {
            plugin_item.identifier: plugin_item.select_supported
            for plugin_item in plugin_items
        }
        self._update_btns_state()

    def get_selected_plugin_identifier(self) -> Optional[str]:
        """Plugin identifier of selected placeholder.

        Returns:
            Optional[str]: Plugin identifier of the selection.

        """
        for index in self._view.selectionModel().selectedIndexes():
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
                Selection is cleared when None is passed.

        """
        if scene_identifier is None:
            self._view.selectionModel().clearSelection()
            return

        matches = self._proxy_model.match(
            self._proxy_model.index(0, 0),
            SCENE_IDENTIFIER_ROLE,
            scene_identifier,
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
        self._update_btns_state()
        self.selection_changed.emit()

    def _on_context_menu(self, point: QtCore.QPoint) -> None:
        index = self._view.indexAt(point)
        if not index.isValid():
            return

        plugin_identifier = index.data(PLUGIN_IDENTIFIER_ROLE)

        menu = AYMenu(self._view)
        if self._select_support.get(plugin_identifier):
            action = menu.addAction("Select in scene")
            icon = get_action_icon(SELECT_ICON)
            if icon is not None:
                action.setIcon(icon)
            action.triggered.connect(self.select_in_scene_requested)

        if self._delete_support.get(plugin_identifier):
            action = menu.addAction("Delete")
            icon = get_action_icon(DELETE_ICON)
            if icon is not None:
                action.setIcon(icon)
            action.triggered.connect(self.delete_requested)

        if not menu.actions():
            return
        menu.exec_(self._view.viewport().mapToGlobal(point))

    def _update_btns_state(self) -> None:
        plugin_identifier = self.get_selected_plugin_identifier()
        delete_enabled = bool(self._delete_support.get(plugin_identifier))
        select_enabled = bool(self._select_support.get(plugin_identifier))

        self._delete_btn.setEnabled(delete_enabled)
        self._select_btn.setEnabled(select_enabled)

        delete_tooltip = "Delete selected placeholder"
        select_tooltip = "Select placeholder in the scene"
        if plugin_identifier is not None:
            if not delete_enabled:
                delete_tooltip = (
                    "Deleting placeholders is not implemented for this"
                    " placeholder type."
                )
            if not select_enabled:
                select_tooltip = (
                    "Selecting placeholders in the scene is not implemented"
                    " for this placeholder type."
                )
        self._delete_btn.setToolTip(delete_tooltip)
        self._select_btn.setToolTip(select_tooltip)
