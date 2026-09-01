"""Toolbar widgets: Customize menu, DisplayType toggle, GroupByMenu."""

from __future__ import annotations

from typing import Literal, Optional

from ayon_core.ui.components.buttons import (
    AYButton,
    AYButtonMenu,
    ButtonMenuDropdown,
)
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.container import (
    AYContainer,
    AYHBoxLayout,
    AYVBoxLayout,
)
from ayon_core.ui.components.dropdown import AYDropdownPopup
from ayon_core.ui.components.filter import AYFilter, FilterItem
from ayon_core.ui.components.filterable_list import FilterableList
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.order import AYOrder
from ayon_core.ui.components.option_action import AYMenu
from ayon_core.ui.components.page_button import AYPageButton
from ayon_core.ui.components.slider import AYSlider
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.browser.ui.browser_group_by import GroupByOption

log = Logger.get_logger(__name__)


class _ColumnMenu(AYMenu):
    """Persistent menu whose rows support visibility paint gestures."""

    visibility_changed = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setProperty("variant", "surface")
        self.menuAction().setProperty("variant", "surface")
        self.setMouseTracking(True)
        self._paint_state: Optional[bool] = None
        self._painted_keys: set[str] = set()
        self._changed = False
        self._pending_submenu_action = None
        self._submenu_timer = QtCore.QTimer(self)
        self._submenu_timer.setSingleShot(True)
        self._submenu_timer.timeout.connect(self._open_pending_submenu)
        self.aboutToHide.connect(self._clear_pending_submenu)

    @staticmethod
    def _column_key(action) -> str:
        if action is None:
            return ""
        return action.property("column-key") or ""

    def mousePressEvent(self, event) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        action = self.actionAt(event.pos())
        if not self._column_key(action) or not action.isEnabled():
            super().mousePressEvent(event)
            return
        self._paint_state = not action.isChecked()
        self._painted_keys.clear()
        self._changed = False
        self._paint_action(action)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._paint_state is None:
            super().mouseMoveEvent(event)
            action = self.actionAt(event.pos())
            submenu = action.menu() if action is not None else None
            if submenu is not None and not submenu.isVisible():
                self._pending_submenu_action = action
                self._submenu_timer.start(0)
            else:
                self._clear_pending_submenu()
            return
        if not event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            self._paint_state = None
            self._painted_keys.clear()
            self._changed = False
            super().mouseMoveEvent(event)
            return
        self._paint_action(self.actionAt(event.pos()))
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._paint_state is None:
            super().mouseReleaseEvent(event)
            return
        self._paint_state = None
        self._painted_keys.clear()
        if self._changed:
            self.visibility_changed.emit()
        self._changed = False
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() in (
            QtCore.Qt.Key.Key_Enter,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Space,
        ):
            action = self.activeAction()
            if self._column_key(action):
                action.setChecked(not action.isChecked())
                self.visibility_changed.emit()
                event.accept()
                return
        super().keyPressEvent(event)

    def _paint_action(self, action) -> None:
        key = self._column_key(action)
        if (
            not key
            or key in self._painted_keys
            or self._paint_state is None
        ):
            return
        self._painted_keys.add(key)
        if action.isChecked() != self._paint_state:
            action.setChecked(self._paint_state)
            self._changed = True
            self.update()

    def _open_pending_submenu(self) -> None:
        action = self._pending_submenu_action
        self._pending_submenu_action = None
        if action is None or action is not self.activeAction():
            return
        submenu = action.menu()
        if submenu is None or submenu.isVisible():
            return
        action_rect = self.actionGeometry(action)
        submenu.popup(
            self.mapToGlobal(
                QtCore.QPoint(
                    action_rect.right() + 1,
                    action_rect.top(),
                )
            )
        )

    def _clear_pending_submenu(self) -> None:
        self._submenu_timer.stop()
        self._pending_submenu_action = None


class AddColumnButton(AYButton):
    """Header button exposing a frontend-style add-column menu."""

    column_state_changed = QtCore.Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(
            parent=parent,
            icon="add",
            variant=AYButton.Variants.Nav_Small,
            tooltip="Add or remove columns",
        )
        self.setFixedSize(28, 28)
        self._columns: list = []
        self._states: list = []
        self._menu_dirty = True
        self._popup_open = False
        self._suppress_reopen_on_next_click = False
        self._menu = _ColumnMenu(self)
        self._attributes_menu = _ColumnMenu("Attributes", self._menu)
        self._attribute_scope_menus: dict[str, _ColumnMenu] = {}
        self._menu.visibility_changed.connect(self._emit_column_state)
        self._attributes_menu.visibility_changed.connect(
            self._emit_column_state
        )
        self._menu.aboutToHide.connect(self._on_popup_closed)
        self.clicked.connect(self._on_button_clicked)

    def set_columns(self, columns: list) -> None:
        columns = list(columns)
        if [
            (column.key, column.label, column.icon, column.entity)
            for column in columns
        ] == [
            (column.key, column.label, column.icon, column.entity)
            for column in self._columns
        ]:
            self._columns = columns
            return
        self._columns = columns
        self._menu_dirty = True

    def _matches_state(self, states: list) -> bool:
        expected_builtin_keys = [
            state.name
            for state in states
            if not state.name.startswith("attr:")
        ]
        if expected_builtin_keys != self._menu_keys(self._menu):
            return False
        actions_by_key = self._actions_by_key()
        if len(actions_by_key) != len(states):
            return False
        for state in states:
            action = actions_by_key.get(state.name)
            if action is None:
                return False
            if action.isChecked() != state.visible:
                return False
        return True

    def _rebuild(self) -> None:
        columns_by_key = {
            column.key: column for column in self._columns
        }
        attribute_keys = [
            column.key
            for column in self._columns
            if column.key.startswith("attr:")
        ]
        attribute_key_set = set(attribute_keys)
        builtin_keys = [
            state.name
            for state in self._states
            if (
                state.name in columns_by_key
                and state.name not in attribute_key_set
            )
        ]
        builtin_keys.extend(
            column.key
            for column in self._columns
            if (
                column.key not in attribute_key_set
                and column.key not in builtin_keys
            )
        )
        by_key = {state.name: state for state in self._states}
        self._menu.clear()
        self._attributes_menu.clear()
        self._attribute_scope_menus = {}
        for key in builtin_keys:
            self._add_column_action(
                self._menu,
                columns_by_key[key],
                by_key.get(key),
            )
        if attribute_keys:
            self._menu.addSeparator()
            self._menu.addMenu(self._attributes_menu)
        attributes_by_entity: dict[str, list[str]] = {}
        for key in attribute_keys:
            column = columns_by_key[key]
            attributes_by_entity.setdefault(column.entity, []).append(key)

        if len(attributes_by_entity) == 1:
            for key in attribute_keys:
                self._add_column_action(
                    self._attributes_menu,
                    columns_by_key[key],
                    by_key.get(key),
                )
        else:
            for entity, keys in attributes_by_entity.items():
                scope_menu = _ColumnMenu(
                    f"{entity} attributes",
                    self._attributes_menu,
                )
                scope_menu.visibility_changed.connect(
                    self._emit_column_state
                )
                self._attribute_scope_menus[entity] = scope_menu
                self._attributes_menu.addMenu(scope_menu)
                for key in keys:
                    self._add_column_action(
                        scope_menu,
                        columns_by_key[key],
                        by_key.get(key),
                    )
                self._fit_menu_width(scope_menu)
        self._fit_menu_width(self._attributes_menu)
        self._fit_menu_width(self._menu)
        self._menu_dirty = False

    @staticmethod
    def _add_column_action(menu, column, state) -> None:
        action = menu.addAction(column.label)
        action.setCheckable(True)
        action.setChecked(state is None or state.visible)
        action.setProperty("variant", "surface")
        action.setProperty("check-style", "checkmark")
        action.setProperty("column-key", column.key)

    @staticmethod
    def _fit_menu_width(menu: QtWidgets.QMenu) -> None:
        """Reserve enough width for the longest menu label and gutters."""
        text_width = max(
            (
                menu.fontMetrics().horizontalAdvance(action.text())
                for action in menu.actions()
                if not action.isSeparator()
            ),
            default=0,
        )
        menu.setMinimumWidth(max(220, text_width + 96))

    @staticmethod
    def _menu_keys(menu) -> list[str]:
        return [
            action.property("column-key")
            for action in menu.actions()
            if action.property("column-key")
        ]

    def _actions_by_key(self) -> dict:
        output = {}
        menus = [
            self._menu,
            self._attributes_menu,
            *self._attribute_scope_menus.values(),
        ]
        for menu in menus:
            for action in menu.actions():
                key = action.property("column-key")
                if key:
                    output[key] = action
        return output

    def _update_action_states(self, states: list) -> None:
        actions_by_key = self._actions_by_key()
        for state in states:
            action = actions_by_key.get(state.name)
            if action is not None:
                action.setChecked(state.visible)

    def set_column_state(self, states: list) -> None:
        states = list(states)
        if self._matches_state(states):
            self._states = states
            return
        expected_builtin_keys = [
            state.name
            for state in states
            if not state.name.startswith("attr:")
        ]
        if expected_builtin_keys == self._menu_keys(self._menu):
            self._states = states
            self._update_action_states(states)
            return
        self._states = states
        self._menu_dirty = True

    def _on_button_clicked(self) -> None:
        if self._suppress_reopen_on_next_click:
            self._suppress_reopen_on_next_click = False
            return
        if self._popup_open:
            self._menu.close()
            return
        self.show_menu(self)

    def show_menu(self, anchor: QtWidgets.QWidget) -> None:
        """Show the shared column menu below an anchor widget."""
        if self._menu_dirty:
            self._rebuild()
        self._popup_open = True
        self._menu.popup(
            anchor.mapToGlobal(
                QtCore.QPoint(0, anchor.height() + 2)
            )
        )

    def _on_popup_closed(self) -> None:
        self._popup_open = False
        if (
            QtWidgets.QApplication.mouseButtons()
            & QtCore.Qt.MouseButton.LeftButton
        ):
            local_pos = self.mapFromGlobal(QtGui.QCursor.pos())
            self._suppress_reopen_on_next_click = (
                self.rect().contains(local_pos)
            )

    def _emit_column_state(self) -> None:
        actions_by_key = self._actions_by_key()
        states = []
        ordered_keys = [
            state.name
            for state in self._states
            if state.name in actions_by_key
        ]
        ordered_keys.extend(
            column.key
            for column in self._columns
            if column.key not in ordered_keys
        )
        for key in ordered_keys:
            action = actions_by_key[key]
            states.append({
                "name": key,
                "visible": action.isChecked(),
            })
        self.column_state_changed.emit(states)


class Customize(AYButtonMenu):
    """Customize button that controls card size, empty groups, etc."""

    show_empty_groups_changed = QtCore.Signal(bool)  # type: ignore
    card_size_changed = QtCore.Signal(int)  # type: ignore
    card_size_committed = QtCore.Signal(int)  # type: ignore
    row_height_changed = QtCore.Signal(int)  # type: ignore
    row_height_committed = QtCore.Signal(int)  # type: ignore
    featured_version_order_changed = QtCore.Signal(list)  # type: ignore
    latest_per_folder_changed = QtCore.Signal(bool)  # type: ignore
    include_children_changed = QtCore.Signal(bool)  # type: ignore
    columns_requested = QtCore.Signal()

    # Maps UI display labels to GraphQL featuredVersion order keys.
    _FEATURED_VERSION_LABEL_TO_KEY: dict[str, str] = {
        "Latest Done": "latestDone",
        "Latest": "latest",
        "Hero": "hero",
    }

    _CARD_WIDTH_MIN = 150
    _CARD_WIDTH_MAX = 500
    _ROW_HEIGHT_MIN = 24
    _ROW_HEIGHT_MAX = 160

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        *,
        initial_card_width: int,
        initial_row_height: int,
        initial_show_empty_groups: bool,
        initial_featured_version_order: tuple[str, ...],
        initial_latest_per_folder: bool,
        initial_include_children: bool,
    ) -> None:
        self._show_empty_groups = bool(initial_show_empty_groups)
        self._latest_per_folder = bool(initial_latest_per_folder)
        self._include_children = bool(initial_include_children)
        self._featured_version_order = tuple(
            initial_featured_version_order
        )
        self._initial_card_width: int = max(
            self._CARD_WIDTH_MIN,
            min(self._CARD_WIDTH_MAX, initial_card_width),
        )
        self._initial_row_height = max(
            self._ROW_HEIGHT_MIN,
            min(self._ROW_HEIGHT_MAX, int(initial_row_height)),
        )
        self._stack = None
        super().__init__(
            "Customize",
            populate_callback=self._populate,
            parent=parent,
            icon="settings",
            variant=AYButton.Variants.Surface,
        )

    def _populate(self, container: ButtonMenuDropdown) -> None:
        self._container = container
        container.setMinimumWidth(300)
        layout = container.layout()
        if not isinstance(layout, AYVBoxLayout):
            log.warning(
                "Customize menu layout is not an AYVBoxLayout: %r",
                layout,
            )
            return

        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(16)

        featured_labels = self._featured_labels(
            self._featured_version_order
        )
        self.featured_version_btn = AYPageButton(
            label="Featured Version",
            icon="layers",
            value=featured_labels[0],
            tooltip=(
                "Define the featured version when acting on the product"
                " (applies when grouped by Product)"
            ),
        )
        layout.addWidget(self.featured_version_btn, stretch=1)

        self.columns_btn = AYPageButton(
            label="Columns", icon="view_column", value=""
        )
        layout.addWidget(self.columns_btn, stretch=1)
        self.columns_btn.clicked.connect(self._on_columns_requested)

        self.card_size_slider = AYSlider(
            label="Card size",
            variant=AYSlider.Variants.Low,
            value=self._initial_card_width,
            minimum=self._CARD_WIDTH_MIN,
            maximum=self._CARD_WIDTH_MAX,
            step=10,
        )
        layout.addWidget(self.card_size_slider, stretch=1)
        self.card_size_slider.value_changed.connect(self.card_size_changed)
        self.card_size_slider.value_committed.connect(
            self.card_size_committed
        )

        self.row_height_slider = AYSlider(
            label="Row height",
            variant=AYSlider.Variants.Low,
            value=self._initial_row_height,
            minimum=self._ROW_HEIGHT_MIN,
            maximum=self._ROW_HEIGHT_MAX,
            step=2,
        )
        self.row_height_slider.setToolTip(
            "Adjust row height in the table view"
        )
        layout.addWidget(self.row_height_slider, stretch=1)
        self.row_height_slider.value_changed.connect(
            self.row_height_changed
        )
        self.row_height_slider.value_committed.connect(
            self.row_height_committed
        )

        self.show_empty_grps_ui = AYCheckBox(
            "Show empty groups",
            checked=self._show_empty_groups,
            variant=AYCheckBox.Variants.Menu,
            parent=self,
        )
        self.show_empty_grps_ui.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.show_empty_grps_ui, stretch=0)
        self.show_empty_grps_ui.toggled.connect(self.show_empty_groups_changed)

        self.latest_per_folder_ui = AYCheckBox(
            "Latest per folder",
            checked=self._latest_per_folder,
            variant=AYCheckBox.Variants.Menu,
            parent=self,
        )
        self.latest_per_folder_ui.setToolTip(
            "Show only the latest published version per folder "
            "(1 version per folder)."
        )
        self.latest_per_folder_ui.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.latest_per_folder_ui, stretch=0)
        self.latest_per_folder_ui.toggled.connect(
            self.latest_per_folder_changed
        )

        self.include_children_ui = AYCheckBox(
            "Show versions from child folders",
            checked=self._include_children,
            variant=AYCheckBox.Variants.Menu,
            parent=self,
        )
        self.include_children_ui.setToolTip(
            "Include versions from folders below the selected folder"
        )
        self.include_children_ui.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        layout.addWidget(self.include_children_ui, stretch=0)
        self.include_children_ui.toggled.connect(
            self.include_children_changed
        )

        # Page 2: featured version settings
        page_2 = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=8,
        )
        container.add_page(page_2)

        page2_nav_lyt = AYHBoxLayout(margin=0, spacing=10)
        page2_back_btn = AYButton(
            icon="arrow_back", variant=AYButton.Variants.Nav
        )
        page2_back_btn.clicked.connect(lambda: container.set_current_page(0))
        page2_nav_lyt.addWidget(page2_back_btn)
        page2_nav_lyt.addWidget(
            AYLabel("Featured Version", variant=AYLabel.Variants.Default)
        )
        page2_nav_lyt.addStretch(1)
        page2_exit_btn = AYButton(icon="close", variant=AYButton.Variants.Nav)
        page2_exit_btn.clicked.connect(self._container.close)
        page2_nav_lyt.addWidget(page2_exit_btn)
        page_2.layout().addLayout(page2_nav_lyt)

        self.featured_version_btn.clicked.connect(
            lambda: container.set_current_page(1)
        )
        self.featured_order = AYOrder(
            featured_labels,
            variant=AYOrder.Variants.Low,
        )
        self.featured_order.order_changed.connect(
            self.on_featured_version_changed
        )
        page_2.layout().addWidget(self.featured_order)

        self._container.popup_closed.connect(self._on_container_closed)

    def _on_columns_requested(self) -> None:
        """Close Customize before opening the shared column menu."""
        self._container.close()
        self.columns_requested.emit()

    def _on_container_closed(self) -> None:
        if self._container:
            self._container.close()
            self._container.set_current_page(0)

    def on_featured_version_changed(self, order: list) -> None:
        """Convert UI labels to GraphQL keys and notify listeners.

        Args:
            order: Ordered list of display labels as returned by the
                :class:`AYOrder` widget (e.g.
                ``["Latest Done", "Latest", "Hero"]``).
        """
        gql_order = [
            self._FEATURED_VERSION_LABEL_TO_KEY.get(label, label)
            for label in order
        ]
        self.featured_version_order_changed.emit(gql_order)

    def set_featured_version_order(self, order: list[str]) -> None:
        """Update the featured-version order without emitting a change."""
        self._featured_version_order = tuple(order)
        if not hasattr(self, "featured_order"):
            return
        labels = self._featured_labels(self._featured_version_order)
        self.featured_order.set_order(labels)
        self.featured_version_btn.set_value(labels[0])

    @classmethod
    def _featured_labels(cls, order: tuple[str, ...]) -> list[str]:
        labels_by_key = {
            key: label
            for label, key in cls._FEATURED_VERSION_LABEL_TO_KEY.items()
        }
        return [labels_by_key.get(key, key) for key in order]

    def set_show_empty_groups(self, enabled: bool) -> None:
        """Update checkbox state without re-emitting change signal."""
        self._show_empty_groups = enabled
        if not hasattr(self, "show_empty_grps_ui"):
            return
        self.show_empty_grps_ui.blockSignals(True)
        self.show_empty_grps_ui.setChecked(enabled)
        self.show_empty_grps_ui.blockSignals(False)

    def set_card_width(self, width: int) -> None:
        """Update slider value without re-emitting change signal."""
        self._initial_card_width = max(
            self._CARD_WIDTH_MIN, min(self._CARD_WIDTH_MAX, width)
        )
        if not hasattr(self, "card_size_slider"):
            return
        self.card_size_slider.blockSignals(True)
        self.card_size_slider.setValue(self._initial_card_width)
        self.card_size_slider.blockSignals(False)

    def set_row_height(self, height: int) -> None:
        """Update the row-height slider without emitting a change."""
        self._initial_row_height = max(
            self._ROW_HEIGHT_MIN,
            min(self._ROW_HEIGHT_MAX, int(height)),
        )
        if not hasattr(self, "row_height_slider"):
            return
        self.row_height_slider.blockSignals(True)
        self.row_height_slider.setValue(self._initial_row_height)
        self.row_height_slider.blockSignals(False)

    def set_latest_per_folder(
        self, enabled: bool, *, disabled: bool = False
    ) -> None:
        """Reflect the latest-per-folder setting in the customize menu."""
        self._latest_per_folder = bool(enabled)
        if not hasattr(self, "latest_per_folder_ui"):
            return
        self.latest_per_folder_ui.blockSignals(True)
        self.latest_per_folder_ui.setChecked(
            self._latest_per_folder and not disabled
        )
        self.latest_per_folder_ui.setEnabled(not disabled)
        if disabled:
            self.latest_per_folder_ui.setToolTip(
                "Disabled when grouping by product"
            )
        else:
            self.latest_per_folder_ui.setToolTip(
                "Show only the latest published version per folder "
                "(1 version per folder)."
            )
        self.latest_per_folder_ui.blockSignals(False)

    def set_include_children(
        self, enabled: bool, *, disabled: bool = False
    ) -> None:
        """Reflect the child-folder inclusion setting in the menu."""
        self._include_children = bool(enabled)
        if not hasattr(self, "include_children_ui"):
            return
        self.include_children_ui.blockSignals(True)
        self.include_children_ui.setChecked(
            self._include_children and not disabled
        )
        self.include_children_ui.setEnabled(not disabled)
        self.include_children_ui.blockSignals(False)


class DisplayType(AYContainer):
    """Toggle between table and grid display types."""

    display_type_changed = QtCore.Signal(str)  # type: ignore

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_display_type: str = "list",
    ) -> None:
        super().__init__(
            parent=parent,
            variant=AYContainer.Variants.Surface,
            layout_margin=1,
            layout_spacing=1,
        )
        self._display_type = initial_display_type
        self._build()

    def _build(self) -> None:
        self._button_grp = QtWidgets.QButtonGroup(parent=self, exclusive=True)

        self._table_btn = AYButton(
            parent=self,
            icon="table_rows",
            variant=AYButton.Variants.Surface,
            checkable=True,
            tooltip="Table",
        )
        self._table_btn.setObjectName("table")
        self._button_grp.addButton(self._table_btn)
        self.add_widget(self._table_btn, stretch=0)

        self._grid_btn = AYButton(
            parent=self,
            icon="grid_view",
            variant=AYButton.Variants.Surface,
            checkable=True,
            tooltip="Cards",
        )
        self._grid_btn.setObjectName("grid")
        self._button_grp.addButton(self._grid_btn)
        self.add_widget(self._grid_btn, stretch=0)

        self._button_grp.buttonClicked.connect(self._on_button_clicked)

        if self._display_type == "table":
            self._table_btn.setChecked(True)
        else:
            self._grid_btn.setChecked(True)

    @property
    def display_type(self) -> str:
        return self._display_type

    def set_display_type(self, display_type: Literal["table", "grid"]) -> None:
        """Set the active display mode programmatically.

        Args:
            display_type: ``"table"`` or ``"grid"``.
        """
        target = "grid" if display_type == "grid" else "table"
        if target == self._display_type:
            return

        self._display_type = target
        table_checked = target == "table"
        self._table_btn.blockSignals(True)
        self._grid_btn.blockSignals(True)
        self._table_btn.setChecked(table_checked)
        self._grid_btn.setChecked(not table_checked)
        self._table_btn.blockSignals(False)
        self._grid_btn.blockSignals(False)

        self.display_type_changed.emit(self._display_type)

    def _on_button_clicked(self, button: QtWidgets.QAbstractButton) -> None:
        self._display_type = button.objectName()
        self.display_type_changed.emit(self._display_type)


class GroupByMenu(AYFilter):
    """Drop-down filter that controls which field is used to group rows."""

    group_by_changed = QtCore.Signal(str)  # type: ignore

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        options: list[GroupByOption] | None = None,
        default_key: str = "product",
    ) -> None:
        self._options_by_key: dict[str, GroupByOption] = {
            option.key: option for option in (options or [])
        }
        self._filters: dict[str, FilterItem] = {
            option.key: FilterItem(key=option.key, label=option.label)
            for option in self._options_by_key.values()
        }
        if default_key in self._filters:
            self._filters[default_key].selected = True
        elif "none" in self._filters:
            self._filters["none"].selected = True

        super().__init__(parent=parent, label="Group By")
        self._sync_tags()

    def _create_dropdown_popup(self) -> AYDropdownPopup | None:
        self._dropdown = AYDropdownPopup(
            parent=self,
            variant=AYDropdownPopup.Variants.Low_Framed_Thin,
            translucent_bg=True,
        )
        lyt = AYVBoxLayout(self._dropdown, margin=2, spacing=0)
        self._filterable_list = FilterableList(
            placeholder="",
            parent=self._dropdown,
        )
        lyt.addWidget(self._filterable_list, stretch=10)
        search = self._filterable_list.search_field()
        search.textChanged.connect(self._on_search_changed)

        self._populate_list()
        return self._dropdown

    def _populate_list(self) -> None:
        self._filterable_list.clear_items()

        kw = {
            "variant": AYButton.Variants.Text,
            "checkable": True,
            "label_alignment": QtCore.Qt.AlignmentFlag.AlignLeft,
            "fixed_width": False,
        }

        self._menu_grp = QtWidgets.QButtonGroup(self._dropdown)
        self._menu_grp.setExclusive(True)
        self._menu_grp.buttonClicked.connect(self._on_dropdown_closed)

        for option in self._options_by_key.values():
            wdgt_name = f"grp_by_{option.key.replace(':', '_')}"
            w = AYButton(option.label, icon=option.icon, **kw)
            w.setProperty("group_by_key", option.key)
            setattr(self, wdgt_name, w)
            if self._filters[option.key].selected:
                w.setChecked(True)
            self._filterable_list.add_item(
                w,
                match_fn=lambda text, n=option.label: (
                    not text.lower().strip()
                    or text.lower().strip() in n.lower()
                ),
            )
            self._menu_grp.addButton(w)

        self._menu_grp.buttonClicked.connect(self._on_group_by_changed)

    def _on_dropdown_closed(self) -> None:
        """Close the dropdown and reset the search field."""
        self._dropdown.close()
        self._filterable_list.search_field().clear()

    def _on_search_changed(self, text: str) -> None:
        self._filterable_list.adjustSize()

    def _set_filter_state(self, key: str, selected: bool) -> None:
        if key not in self._filters:
            return
        self._filters[key].selected = selected

    def _sync_tags(self) -> None:
        self._sync_tags_from_items(list(self._filters.values()))
        if self._filters["none"].selected:
            self._remove_tag("none")

    def _on_group_by_changed(self, button: AYButton) -> None:
        grp_key = button.property("group_by_key")
        if not isinstance(grp_key, str):
            return
        log.debug("Group By: %s", grp_key)
        for k, v in self._filters.items():
            v.selected = k == grp_key
        self._sync_tags()
        self.group_by_changed.emit(grp_key)

    def _handle_tag_removed(self, key: str) -> None:
        """React to a tag dismissal by resetting to "none".

        Args:
            key: Key of the dismissed tag.
        """
        for v in self._filters.values():
            v.selected = False
        self._filters["none"].selected = True
        self._sync_tags()
        self.group_by_changed.emit("none")

    def set_options(
        self,
        options: list[GroupByOption],
        selected_key: str,
    ) -> None:
        """Replace group-by options and keep the current selection.

        Args:
            options: New list of :class:`GroupByOption` items.
            selected_key: Key of the option that should be selected.
        """
        self._options_by_key = {option.key: option for option in options}
        self._filters = {
            option.key: FilterItem(
                key=option.key,
                label=option.label,
                selected=(option.key == selected_key),
            )
            for option in options
        }
        if selected_key not in self._filters and "none" in self._filters:
            self._filters["none"].selected = True
        self._sync_tags()
        self._populate_list()

    def get_selected_keys(self) -> list[str]:
        """Return the list of selected filter keys.

        Returns:
            List of selected keys.
        """
        return [v.key for v in self._filters.values() if v.selected]
