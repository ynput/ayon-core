"""Toolbar widgets: Customize menu, DisplayType toggle, GroupByMenu."""

from __future__ import annotations

from ayon_ui_qt.components.buttons import (
    AYButton,
    AYButtonMenu,
    ButtonMenuDropdown,
)
from ayon_ui_qt.components.check_box import AYCheckBox
from ayon_ui_qt.components.container import (
    AYContainer,
    AYHBoxLayout,
    AYVBoxLayout,
)
from ayon_ui_qt.components.dropdown import AYDropdownPopup
from ayon_ui_qt.components.filter import AYFilter, FilterItem
from ayon_ui_qt.components.filterable_list import FilterableList
from ayon_ui_qt.components.label import AYLabel
from ayon_ui_qt.components.order import AYOrder
from ayon_ui_qt.components.page_button import AYPageButton
from ayon_ui_qt.components.slider import AYSlider
from qtpy import QtCore, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.loader.ui.review_group_by import GroupByOption

log = Logger.get_logger(__name__)


class Customize(AYButtonMenu):
    """Customize button that controls card size, empty groups, etc."""

    show_empty_groups_changed = QtCore.Signal(bool)  # type: ignore
    card_size_changed = QtCore.Signal(int)  # type: ignore
    featured_version_order_changed = QtCore.Signal(list)  # type: ignore

    # Maps UI display labels to GraphQL featuredVersion order keys.
    _FEATURED_VERSION_LABEL_TO_KEY: dict[str, str] = {
        "Latest Done": "latestDone",
        "Latest": "latest",
        "Hero": "hero",
    }

    _CARD_WIDTH_MIN = 150
    _CARD_WIDTH_MAX = 300

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        initial_card_width: int = 200,
    ) -> None:
        self._show_empty_groups: bool = False
        self._initial_card_width: int = max(
            self._CARD_WIDTH_MIN,
            min(self._CARD_WIDTH_MAX, initial_card_width),
        )
        super().__init__(
            "Customize",
            populate_callback=self._populate,
            parent=parent,
            icon="settings",
            variant=AYButton.Variants.Surface,
            icon_size=16,
        )
        self._stack = None

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

        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)

        self.featured_version_btn = AYPageButton(
            label="Featured Version", icon="layers", value="Latest Done"
        )
        layout.addWidget(self.featured_version_btn, stretch=1)

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

        # Page 2: featured version settings
        page_2 = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=10,
            layout_spacing=15,
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

        featured_order = AYOrder(
            ["Latest Done", "Latest", "Hero"],
            variant=AYOrder.Variants.Low,
        )
        featured_order.order_changed.connect(self.on_featured_version_changed)
        page_2.layout().addWidget(featured_order)

        self._container.popup_closed.connect(self._on_container_closed)

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
            icon_size=16,
            checkable=True,
        )
        self._table_btn.setObjectName("table")
        self._button_grp.addButton(self._table_btn)
        self.add_widget(self._table_btn, stretch=0)

        self._grid_btn = AYButton(
            parent=self,
            icon="grid_view",
            variant=AYButton.Variants.Surface,
            icon_size=16,
            checkable=True,
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

        super().__init__(parent=parent, label="Group By  ")
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
