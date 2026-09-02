from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from qtpy.QtCore import (
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QSize,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from qtpy.QtGui import QCloseEvent, QKeySequence, QMouseEvent
from qtpy.QtWidgets import (
    QFrame,
    QShortcut,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from .buttons import AYButton
from .container import AYContainer
from .dropdown import AYDropdownPopup
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYHBoxLayout, AYVBoxLayout
from .line_edit import AYLineEdit
from .table_model import FilterEntry, PaginatedTableModel, TableColumn

ENTITY_ICONS = {
    "Folder": "folder",
    "Product": "inventory_2",
    "Task": "check_circle",
    "Version": "layers",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class FilterCriterion:
    """A single active filter criterion.

    Attributes:
        key: Column key this criterion applies to.
        attribute_label: Human-readable label for the column.
        values: List of accepted values (OR logic within criterion).
        use_substring: When True use case-insensitive substring matching;
            False uses exact match (used for enum columns).
    """

    key: str
    attribute_label: str
    values: list[str] = field(default_factory=list)
    use_substring: bool = False

    def to_def(self) -> dict[str, Any]:
        """Serialise this criterion to the View payload condition format.

        Returns:
            A plain ``dict`` suitable for embedding under
            ``settings.filter.conditions``.
        """
        return {
            "key": self.key,
            "label": self.attribute_label,
            "values": list(self.values),
            "useSubstring": self.use_substring,
        }

    @classmethod
    def from_def(cls, payload: dict[str, Any]) -> "FilterCriterion":
        """Build a :class:`FilterCriterion` from a payload condition dict.

        Args:
            payload: Condition dict (as produced by :meth:`to_def`).
                Unknown keys are ignored so newer payloads roundtrip
                gracefully.

        Returns:
            A new :class:`FilterCriterion`.
        """
        raw_values = payload.get("values") or []
        return cls(
            key=str(payload.get("key", "")),
            attribute_label=str(payload.get("label", payload.get("key", ""))),
            values=[str(v) for v in raw_values],
            use_substring=bool(payload.get("useSubstring", False)),
        )


# ---------------------------------------------------------------------------
# Proxy model
# ---------------------------------------------------------------------------


class AYTableFilterProxyModel(QSortFilterProxyModel):
    """Proxy model that filters rows using a list of FilterCriterion.

    All criteria are combined with AND; values within a single criterion
    are combined with OR.  When no criteria are set every row passes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._criteria: list[FilterCriterion] = []
        self._columns: list[TableColumn] = []
        self._source_column_indices: dict[str, int] = {}
        self._extra_filter_keys: set[str] = set()
        self._row_value_getter: (
            Callable[[QModelIndex, str], Any] | None
        ) = None
        self._tree_mode_getter: Callable[[], bool] | None = None
        self._unloaded_children_getter: (
            Callable[[QModelIndex], bool] | None
        ) = None
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_row_value_getter(
        self,
        getter: Callable[[QModelIndex, str], Any] | None,
    ) -> None:
        """Set the callback used to read values outside table columns."""
        self._row_value_getter = getter

    def set_tree_state_getters(
        self,
        tree_mode_getter: Callable[[], bool] | None,
        unloaded_children_getter: Callable[[QModelIndex], bool] | None,
    ) -> None:
        """Set callbacks used to preserve parents with unloaded children."""
        self._tree_mode_getter = tree_mode_getter
        self._unloaded_children_getter = unloaded_children_getter

    def set_criteria(
        self,
        criteria: list[FilterCriterion],
        columns: list[TableColumn],
        filter_entries: list[FilterEntry] | None = None,
    ) -> None:
        """Replace active criteria and refresh the filter.

        Args:
            criteria: List of active filter criteria.
            columns: Column definitions from the source model.
        """
        self._criteria = [c for c in criteria if c.values]
        self._columns = columns
        self._source_column_indices = {
            column.key: index for index, column in enumerate(columns)
        }
        # Extra filters are backed by row data rather than source columns.
        # Keep this separate so an extra entry cannot overwrite a real
        # column index when both use the same key.
        self._extra_filter_keys = {
            entry.key
            for entry in (filter_entries or [])
            if entry.key not in self._source_column_indices
        }
        self.invalidateFilter()

    def _direct_match(
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Return True if a single row satisfies every active criterion.

        Args:
            source_row: Row number in the source model.
            source_parent: Parent index in the source model.

        Returns:
            ``True`` when all criteria are satisfied (AND logic).
        """
        if not self._criteria:
            return True

        source_model = self.sourceModel()
        if source_model is None:
            return True

        for criterion in self._criteria:
            if not criterion.values:
                continue
            col_idx = self._source_column_indices.get(criterion.key)
            if col_idx is not None:
                index = source_model.index(source_row, col_idx, source_parent)
                cell_value = source_model.data(
                    index, Qt.ItemDataRole.DisplayRole
                )
            elif criterion.key in self._extra_filter_keys:
                index = source_model.index(source_row, 0, source_parent)
                if self._row_value_getter is None:
                    continue
                cell_value = self._row_value_getter(index, criterion.key)
            else:
                continue
            cell_str = "" if cell_value is None else str(cell_value).lower()

            matched = False
            for val in criterion.values:
                val_lower = val.lower()
                if criterion.use_substring:
                    if val_lower in cell_str:
                        matched = True
                        break
                else:
                    if cell_str == val_lower:
                        matched = True
                        break
            if not matched:
                return False

        return True

    def filterAcceptsRow(  # noqa: N802
        self,
        source_row: int,
        source_parent: QModelIndex | QPersistentModelIndex,
    ) -> bool:
        """Return True if the row (or any of its loaded children) matches.

        In flat mode the recursive child check is a no-op because leaf
        nodes have ``rowCount() == 0``.  In tree mode parent folders are
        kept visible as long as at least one loaded descendant passes the
        criteria, preserving the tree structure.

        Args:
            source_row: Row number in the source model.
            source_parent: Parent index in the source model.

        Returns:
            ``True`` when the row or a descendant satisfies all criteria.
        """
        if not self._criteria:
            return True

        # Tentatively accept tree-mode folder nodes whose children haven't
        # been fetched yet. We can't know whether any descendant will match
        # until the children are loaded. PaginatedTableModel emits dataChanged
        # for the node once its children are loaded, which causes this method
        # to be called again with real data to decide.
        source_model = self.sourceModel()
        if (
            self._tree_mode_getter is not None
            and self._tree_mode_getter()
            and self._unloaded_children_getter is not None
        ):
            src_idx = source_model.index(source_row, 0, source_parent)
            if self._unloaded_children_getter(src_idx):
                return True

        if self._direct_match(source_row, source_parent):
            return True

        # Tree hierarchy: keep parent visible if any loaded child matches.
        if source_model is None:
            return False
        source_index = source_model.index(source_row, 0, source_parent)
        for child_row in range(source_model.rowCount(source_index)):
            if self.filterAcceptsRow(child_row, source_index):
                return True

        return False

    def refresh_filter(self) -> None:
        """Re-apply the current filter criteria (e.g. after source data
        changes)."""
        self.invalidateFilter()


# ---------------------------------------------------------------------------
# Floating two-page dropdown
# ---------------------------------------------------------------------------


class _FilterDropdown(AYDropdownPopup):
    """Two-page floating dropdown for attribute + value selection.

    Page 0: attribute list (with live search).
    Page 1: value list or free-text input for a specific attribute.

    Signals:
        criterion_ready: Emitted when the user clicks Apply.
                         Passes (key, values, use_substring).
        popup_closed: Inherited from ``AYDropdownPopup``. Emitted when
            the popup is dismissed.
    """

    criterion_ready = Signal(str, list, bool)  # key, values, use_substring

    def __init__(
        self,
        model: PaginatedTableModel,
        table_filter: AYTableFilter,
        filters: list[FilterEntry],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            variant=AYDropdownPopup.Variants.Low_Framed_Thin,
            translucent_bg=False,
        )
        self._model = model
        self._table_filter = table_filter
        self._filters = filters
        self._column_values: dict[str, list[str]] = {}
        self._filters_by_key: dict[str, FilterEntry] = {}
        self._filters_by_entity: dict[str, list[FilterEntry]] = {}
        self._reindex_filters()
        self._current_key: str = ""
        self._current_label: str = ""
        self._value_buttons: dict[str, AYButton] = {}
        self._is_free_text: bool = False
        self._selected_entity: str | None = None
        self._value_scroll: QScrollArea | None = None
        self._value_back_btn: AYButton | None = None
        self._attr_selection_index = -1
        self._applying = False

        self.setMinimumWidth(220)

        self._build()

    def set_filters(self, filters: list[FilterEntry]) -> None:
        """Replace available filters while keeping the current criteria."""
        self._filters = list(filters)
        self._reindex_filters()

    def _reindex_filters(self) -> None:
        """Build lookup maps used by the dropdown pages."""
        self._filters_by_key = {}
        self._filters_by_entity = {}
        for entry in self._filters:
            self._filters_by_key[entry.key] = entry
            self._filters_by_entity.setdefault(entry.entity, []).append(entry)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root_layout = AYVBoxLayout(self, margin=4, spacing=4)

        self._attr_search = AYLineEdit(
            placeholder="Search",
            variant=AYLineEdit.Variants.Search_Field,
        )
        self._attr_search.installEventFilter(self)
        self._attr_search.textChanged.connect(
            self._on_attr_search_changed
        )
        self._attr_search.returnPressed.connect(
            self._on_search_return_pressed
        )
        root_layout.addWidget(self._attr_search)

        self._stack = QStackedWidget(self)
        root_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_attribute_page())
        self._stack.addWidget(self._build_value_page())

    def _build_attribute_page(self) -> QWidget:
        """Build Page 0 - attribute selector."""
        page = AYFrame(variant=AYFrame.Variants.Low)
        layout = AYVBoxLayout(page, margin=0, spacing=4)

        self._attr_back_btn = AYButton(
            "Back",
            icon="arrow_back",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        self._attr_back_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._attr_back_btn.clicked.connect(self._show_entity_page)
        self._attr_breadcrumb = AYLabel(dim=True, rel_text_size=-1)
        self._attr_breadcrumb.setVisible(False)
        attr_nav_layout = AYHBoxLayout(spacing=4, margin=0)
        attr_nav_layout.addWidget(self._attr_back_btn)
        attr_nav_layout.addWidget(self._attr_breadcrumb)
        layout.addLayout(attr_nav_layout)

        # Scrollable column list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._attr_container = AYFrame(variant=AYFrame.Variants.Low)
        self._attr_layout = AYVBoxLayout(
            self._attr_container, margin=0, spacing=0
        )
        scroll.setWidget(self._attr_container)
        layout.addWidget(scroll, stretch=1)

        self._attr_scroll = scroll
        return page

    def _build_value_page(self) -> QWidget:
        """Build Page 1 - value selector."""
        page = AYFrame(variant=AYFrame.Variants.Low)
        layout = AYVBoxLayout(page, margin=0, spacing=4)
        layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        value_back_btn = AYButton(
            "Back",
            icon="arrow_back",
            variant=AYButton.Variants.Text,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        value_back_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        value_back_btn.clicked.connect(self._go_to_attribute_page)
        value_back_btn.installEventFilter(self)
        self._value_back_btn = value_back_btn
        self._value_breadcrumb = AYLabel(dim=True, rel_text_size=-1)
        value_nav_layout = AYHBoxLayout(spacing=4, margin=0)
        value_nav_layout.addWidget(value_back_btn)
        value_nav_layout.addWidget(self._value_breadcrumb)
        layout.addLayout(value_nav_layout)

        # Content area (swapped depending on column type)
        self._value_content_container = AYFrame(variant=AYFrame.Variants.Low)
        self._value_content_layout = AYVBoxLayout(
            self._value_content_container, margin=0, spacing=0
        )
        layout.addWidget(self._value_content_container, stretch=1)

        # Footer: Apply button
        footer = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=4,
            layout_spacing=8,
        )
        self._apply_btn = AYButton(
            "Confirm",
            variant=AYButton.Variants.Filled,
            icon="check",
        )
        self._apply_btn.clicked.connect(self._on_apply)
        footer.add_widget(self._apply_btn)
        layout.addWidget(footer)

        return page

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_for_new(self, anchor: QWidget) -> None:
        """Open the dropdown on Page 0 (attribute selection).

        Args:
            anchor: Widget to position the popup below.
        """
        self._show_entity_page()
        self._stack.setCurrentIndex(0)
        self._adjust_height()
        self.show_below(anchor)
        self._attr_search.setFocus()

    def open_for_edit(
        self,
        criterion: FilterCriterion,
        anchor: QWidget,
    ) -> None:
        """Open the dropdown on Page 1 pre-populated with *criterion*.

        Args:
            criterion: Existing criterion to edit.
            anchor: Widget to position the popup below.
        """
        self._populate_value_page(
            criterion.key,
            criterion.attribute_label,
            criterion.values,
        )
        self._stack.setCurrentIndex(1)
        self._adjust_height()
        self.show_below(anchor)
        self._attr_search.setFocus()

    def set_column_values(self, values: dict[str, list[str]]) -> None:
        """Set stable value lists for columns backed by project metadata."""
        self._column_values = {
            key: list(items) for key, items in values.items()
        }

    # ------------------------------------------------------------------
    # Attribute page helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _label_with_icon_spacing(
        label: str,
        icon: str | None,
    ) -> str:
        """Add a small visual gap between an icon and button text."""
        return f" {label}" if icon else label

    def _show_entity_page(self) -> None:
        """Show the top-level entity selection page."""
        entities = {entry.entity for entry in self._filters}
        self._selected_entity = "Other" if entities == {"Other"} else None
        self._attr_breadcrumb.setText("")
        self._attr_breadcrumb.setVisible(False)
        self._attr_search.blockSignals(True)
        self._attr_search.clear()
        self._attr_search.blockSignals(False)
        self._attr_back_btn.setVisible(self._selected_entity is not None)
        self._populate_attribute_page(self._selected_entity)
        self._attr_search.setFocus()

    def _populate_attribute_page(self, entity: str | None = None) -> None:
        """Show entity choices or filters for one entity."""
        # Remove old buttons
        while self._attr_layout.count():
            item = self._attr_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._search_separator = None
        self._attr_buttons: dict[str, AYButton] = {}
        self._attr_groups: dict[str, list[AYButton]] = {}
        self._attr_selection_index = -1

        if entity is None:
            for entity_name in self._filters_by_entity:
                self._add_entity_button(entity_name)
        else:
            for entry in self._filters_by_entity.get(entity, []):
                self._add_attribute_button(
                    entry,
                    entry.label,
                )

        self._attr_layout.addStretch()
        self._adjust_height()

    def _add_entity_button(self, entity: str) -> AYButton:
        """Add an entity scope button to the attribute selector."""
        icon = ENTITY_ICONS.get(entity, "label")
        btn = AYButton(
            self._label_with_icon_spacing(entity, icon),
            icon=icon,
            icon_color="#dedede",
            variant=AYButton.Variants.Text,
            checkable=True,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        btn.installEventFilter(self)
        btn.clicked.connect(
            lambda _checked=False, name=entity: (
                self._show_entity_filters(name)
            )
        )
        self._attr_buttons[entity] = btn
        self._attr_layout.addWidget(btn)
        self._attr_groups[entity] = [btn]
        btn.show()
        return btn

    def _add_attribute_button(
        self,
        entry: FilterEntry,
        label: str | None = None,
    ) -> None:
        """Add one filter option to the attribute selector."""
        label = label or entry.label
        icon = entry.icon or "label"
        btn = AYButton(
            self._label_with_icon_spacing(label, icon),
            icon=icon,
            icon_color="#dedede",
            variant=AYButton.Variants.Text,
            checkable=True,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        btn.installEventFilter(self)
        btn.clicked.connect(
            lambda _checked=False, k=entry.key, lbl=label: (
                self._on_attr_selected(k, lbl)
            )
        )
        self._attr_buttons[entry.key] = btn
        self._attr_layout.addWidget(btn)
        btn.show()

    def _show_entity_filters(self, entity: str) -> None:
        """Show filters belonging to one entity."""
        self._selected_entity = entity
        self._attr_breadcrumb.setText(entity)
        self._attr_breadcrumb.setVisible(True)
        self._attr_back_btn.setVisible(True)
        self._stack.setCurrentIndex(0)
        self._attr_search.blockSignals(True)
        self._attr_search.clear()
        self._attr_search.blockSignals(False)
        self._populate_attribute_page(entity)
        self._attr_search.setFocus()

    def _on_attr_search_changed(self, text: str) -> None:
        if self._stack.currentIndex() == 1:
            self._on_value_search_changed(text)
            return

        query = text.lower().strip()
        if not query:
            if self._selected_entity is None:
                self._populate_attribute_page()
            else:
                self._populate_attribute_page(self._selected_entity)
            return

        entity = self._selected_entity
        if entity is None:
            self._attr_back_btn.setVisible(False)
        self._populate_search_results(query, entity=entity)
        self._adjust_height()

    def _populate_search_results(
        self,
        query: str,
        entity: str | None = None,
    ) -> None:
        """Show matching scopes and filters in one search result list."""
        scoped_entity = entity
        while self._attr_layout.count():
            item = self._attr_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._search_separator = None
        self._attr_buttons = {}
        self._attr_groups = {}
        self._attr_selection_index = -1
        entities = (
            [entity]
            if entity is not None
            else list(self._filters_by_entity)
        )

        matching_entities = [
            entity for entity in entities if query in entity.lower()
        ]
        matching_attributes: list[tuple[str, FilterEntry]] = []
        for entity in entities:
            for entry in self._filters_by_entity[entity]:
                if (
                    query in entry.label.lower()
                    or query in entry.key.lower()
                ):
                    matching_attributes.append((entity, entry))

        if entity is None:
            for entity in matching_entities:
                self._add_entity_button(entity)

        if entity is None and matching_entities and matching_attributes:
            separator = QFrame()
            separator.setFrameShape(QFrame.Shape.HLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            separator.setStyleSheet(
                "QFrame { border-top: 1px solid #41474d; }"
            )
            separator.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            separator.setFixedHeight(1)
            self._attr_layout.addWidget(separator)
            self._search_separator = separator

        for entity, entry in matching_attributes:
            self._add_attribute_button(
                entry,
                (
                    entry.label
                    if scoped_entity is not None
                    else f"{entity} > {entry.label}"
                ),
            )

        self._attr_layout.addStretch()

    def _on_attr_selected(self, key: str, label: str) -> None:
        self._populate_value_page(key, label, [])
        self._stack.setCurrentIndex(1)
        self._adjust_height()
        self._attr_search.setFocus()

    def _go_to_attribute_page(self) -> None:
        self._stack.setCurrentIndex(0)
        self._attr_search.blockSignals(True)
        self._attr_search.clear()
        self._attr_search.setPlaceholderText("Search")
        self._attr_search.blockSignals(False)
        self._adjust_height()
        self._attr_search.setFocus()

    def _on_value_search_changed(self, text: str) -> None:
        """Filter value buttons or edit a free-text criterion."""
        if self._is_free_text:
            return

        query = text.lower().strip()
        for value, button in self._value_buttons.items():
            label = button.text().lower()
            button.setVisible(not query or query in label)
        self._adjust_height()

    def _on_search_return_pressed(self) -> None:
        """Apply free-text values when Enter is pressed in the top field."""
        if self._stack.currentIndex() == 1 and self._is_free_text:
            self._on_apply()

    @staticmethod
    def _ensure_widget_visible(
        scroll: QScrollArea | None,
        widget: QWidget,
    ) -> None:
        """Scroll a popup list until the active widget is visible."""
        if scroll is not None:
            scroll.ensureWidgetVisible(widget)

    # ------------------------------------------------------------------
    # Value page helpers
    # ------------------------------------------------------------------

    def _populate_value_page(
        self,
        key: str,
        label: str,
        selected_values: list[str],
    ) -> None:
        """Rebuild the value content area for the given column.

        Args:
            key: Column key.
            label: Column label shown in header.
            selected_values: Values currently selected (for edit mode).
        """
        self._current_key = key
        self._current_label = label
        self._value_buttons = {}
        self._attr_search.blockSignals(True)
        self._attr_search.clear()
        self._attr_search.setPlaceholderText("Search")
        self._attr_search.blockSignals(False)

        # Clear previous content
        self._value_content_layout.clear()

        entry = self._filters_by_key.get(key)
        if entry is not None:
            self._value_breadcrumb.setText(
                f"{entry.entity} / {entry.label}"
            )
        else:
            self._value_breadcrumb.setText(label)
        if entry is not None and entry.text_search:
            distinct = []
        elif key == "version" and entry is not None:
            distinct = list(entry.values)
            for value in (
                self._column_values.get(key)
                or self._model.get_distinct_values(key)
            ):
                if value not in distinct:
                    distinct.append(value)
        elif entry is not None and entry.values:
            distinct = list(entry.values)
        elif key in self._column_values:
            distinct = list(self._column_values[key])
        else:
            distinct = self._model.get_distinct_values(key)
        for value in selected_values:
            if value not in distinct:
                distinct.append(value)
        if key == "task" and "No task" not in distinct:
            distinct.append("No task")

        if distinct:
            self._is_free_text = False
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
            scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            inner = AYFrame(variant=AYFrame.Variants.Low)
            inner_layout = AYVBoxLayout(inner, margin=0, spacing=0)

            for val in distinct:
                value_label = val
                value_icon = None
                value_color = None
                if entry is not None:
                    value_label = entry.value_labels.get(val, val)
                    value_icon = entry.value_icons.get(val)
                    value_color = entry.value_colors.get(val)
                value_label = self._label_with_icon_spacing(
                    value_label,
                    value_icon,
                )
                btn = AYButton(
                    value_label,
                    icon=value_icon,
                    icon_color=value_color,
                    variant=AYButton.Variants.Text,
                    fixed_width=False,
                    checkable=True,
                    label_alignment=Qt.AlignmentFlag.AlignLeft,
                    # TODO: support icons for enum columns
                    #       (need to expose in model)
                )
                btn.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
                )
                btn.setChecked(val in selected_values)
                self._value_buttons[val] = btn
                btn.installEventFilter(self)
                inner_layout.addWidget(btn)

            inner_layout.addStretch()
            scroll.setWidget(inner)
            self._value_content_layout.addWidget(scroll)
            self._value_scroll = scroll
        else:
            self._is_free_text = True
            self._value_scroll = None
            if selected_values:
                self._attr_search.setText(selected_values[0])

        self._apply_btn.installEventFilter(self)

    def _get_value_navigation_widgets(self) -> list[QWidget]:
        """Return controls in the value-page keyboard navigation order."""
        widgets: list[QWidget] = []
        if self._value_back_btn is not None:
            widgets.append(self._value_back_btn)
        widgets.extend(self._value_buttons.values())
        if self._is_free_text:
            widgets.append(self._attr_search)
        widgets.append(self._apply_btn)
        return [
            widget for widget in widgets
            if widget.isVisible() and widget.isEnabled()
        ]

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Navigate and activate visible filter members from the keyboard."""
        if not hasattr(self, "_stack"):
            return super().eventFilter(watched, event)

        if self._stack.currentIndex() == 1:
            widgets = self._get_value_navigation_widgets()
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() in (
                    Qt.Key.Key_Up,
                    Qt.Key.Key_Down,
                )
                and widgets
            ):
                current = widgets.index(watched) if watched in widgets else -1
                step = -1 if event.key() == Qt.Key.Key_Up else 1
                widget = widgets[(current + step) % len(widgets)]
                widget.setFocus()
                if widget in self._value_buttons.values():
                    self._ensure_widget_visible(
                        self._value_scroll,
                        widget,
                    )
                return True
            if (
                event.type() == QEvent.Type.KeyPress
                and event.key() in (
                    Qt.Key.Key_Enter,
                    Qt.Key.Key_Return,
                )
                and widgets
            ):
                if watched in widgets:
                    widget = watched
                else:
                    widget = widgets[0]
                if widget is self._attr_search and self._is_free_text:
                    self._on_apply()
                elif isinstance(widget, AYButton):
                    widget.click()
                return True
            return super().eventFilter(watched, event)

        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
            )
        ):
            buttons = [
                button for button in self._attr_buttons.values()
                if button.isVisible() and button.isEnabled()
            ]
            if buttons:
                focused = (
                    buttons.index(watched)
                    if watched in buttons
                    else self._attr_selection_index
                )
                step = -1 if event.key() == Qt.Key.Key_Up else 1
                self._attr_selection_index = (focused + step) % len(buttons)
                selected_index = self._attr_selection_index
                for index, button in enumerate(buttons):
                    button.setChecked(index == selected_index)
                self._ensure_widget_visible(
                    self._attr_scroll,
                    buttons[selected_index],
                )
                self._attr_search.setFocus()
                return True
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return)
        ):
            buttons = [
                button for button in self._attr_buttons.values()
                if button.isVisible() and button.isEnabled()
            ]
            if buttons:
                if watched in buttons:
                    index = buttons.index(watched)
                elif self._attr_selection_index >= 0:
                    index = self._attr_selection_index
                else:
                    index = 0
                self._attr_selection_index = index
                buttons[index].click()
                return True
        return super().eventFilter(watched, event)

    def _on_apply(self) -> None:
        if not self._current_key:
            return

        values, use_substring = self._current_values()
        self._applying = True
        try:
            self.criterion_ready.emit(
                self._current_key, values, use_substring
            )
            self.close()
        finally:
            self._applying = False

    def _current_values(self) -> tuple[list[str], bool]:
        """Return the current value-page selection and match mode."""
        if self._is_free_text:
            text = self._attr_search.text().strip()
            return ([text] if text else []), True
        return (
            [
                val
                for val, btn in self._value_buttons.items()
                if btn.isChecked()
            ],
            False,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """Commit a non-empty value selection when dismissing the popup."""
        if (
            not self._applying
            and self._stack.currentIndex() == 1
            and self._current_key
        ):
            values, use_substring = self._current_values()
            if values:
                self.criterion_ready.emit(
                    self._current_key,
                    values,
                    use_substring,
                )
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Positioning / layout helpers
    # ------------------------------------------------------------------

    def _adjust_height(self) -> None:
        """Resize the popup to its content, capped by a scrollable list."""
        max_popup_height = 640
        min_popup_height = 100
        max_list_height = 500

        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self._stack.setMinimumHeight(0)
        self._stack.setMaximumHeight(16777215)

        if self._stack.currentIndex() == 0:
            self._attr_layout.activate()
            scroll = self._attr_scroll
            buttons = [
                button for button in self._attr_buttons.values()
                if not button.isHidden()
            ]
            separator = getattr(self, "_search_separator", None)
            empty_search = bool(
                self._attr_search.text().strip()
            ) and not buttons
            scroll.setVisible(not empty_search)
        else:
            self._value_content_layout.activate()
            scroll = self._value_scroll
            buttons = [
                button
                for button in self._value_buttons.values()
                if button.isVisible()
            ]
            separator = None

        if scroll is not None:
            button_height = max(
                (button.sizeHint().height() for button in buttons),
                default=0,
            )
            spacing = (
                self._attr_layout.spacing()
                if self._stack.currentIndex() == 0
                else self._value_content_layout.spacing()
            )
            content_height = (
                len(buttons) * button_height
                + max(0, len(buttons) - 1) * spacing
            )
            if separator is not None:
                content_height += separator.sizeHint().height() + spacing
            list_height = min(content_height, max_list_height)
            scroll.setMinimumHeight(list_height)
            scroll.setMaximumHeight(list_height)

        page = self._stack.currentWidget()
        page.layout().activate()
        popup_layout = self.layout()
        margins = popup_layout.contentsMargins()
        vertical_margins = margins.top() + margins.bottom()
        search_extra_height = (
            self._attr_search.sizeHint().height()
            + popup_layout.spacing()
        )
        content_min_height = max(
            0,
            min_popup_height - vertical_margins - search_extra_height,
        )
        if self._stack.currentIndex() == 0 and not buttons:
            content_min_height = 0
        content_max_height = max(
            0,
            max_popup_height - vertical_margins - search_extra_height,
        )
        height = max(page.sizeHint().height(), content_min_height)
        height = min(height, content_max_height)
        self._stack.setMinimumHeight(height)
        self._stack.setMaximumHeight(height)
        self.setMinimumHeight(
            height + search_extra_height + vertical_margins
        )
        self.setMaximumHeight(
            height + search_extra_height + vertical_margins
        )
        self.setMinimumWidth(max(220, self._table_filter.width()))


# ---------------------------------------------------------------------------
# Criterion badge
# ---------------------------------------------------------------------------


class _CriterionBadge(AYContainer):
    """Displays one active filter criterion as an inline badge.

    Signals:
        edit_requested: User clicked the badge body.
        remove_requested: User clicked the close button.
    """

    edit_requested = Signal(object)  # FilterCriterion
    remove_requested = Signal(object)  # FilterCriterion

    def __init__(
        self,
        criterion: FilterCriterion,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent=parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Criterion,
            layout_margin=2,
            layout_spacing=4,
        )
        self._criterion = criterion
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        front_icon = AYLabel(
            icon="check_small",
            icon_size=16,
        )
        front_icon.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.add_widget(front_icon)

        values_text = (
            " or ".join(criterion.values) if criterion.values else "…"
        )
        badge_text = f"{criterion.attribute_label}: {values_text}"

        self._label = AYLabel(badge_text)
        self._label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.add_widget(self._label)

        self._close_btn = AYButton(
            icon="close",
            icon_size=14,
            variant=AYButton.Variants.Nav_Small,
        )
        self._close_btn.setFixedSize(20, 20)
        self._close_btn.clicked.connect(
            lambda: self.remove_requested.emit(self._criterion)
        )
        self.add_widget(self._close_btn)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.edit_requested.emit(self._criterion)
            event.accept()
            return
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# Main filter bar
# ---------------------------------------------------------------------------


class AYTableFilter(AYContainer):
    """Horizontal filter bar bound to a PaginatedTableModel.

    Displays active criteria as badges and manages a floating two-page
    dropdown for adding/editing criteria.  Applies filtering via an
    internal ``AYTableFilterProxyModel``.

    Typical usage::

        filter_bar = AYTableFilter(model=source_model)
        table.setModel(filter_bar.filter_model)
        layout.addWidget(filter_bar)
        layout.addWidget(table)

    Signals:
        filters_changed: Emitted after any criteria change.
                         Passes the current list of FilterCriterion.
    """

    filters_changed = Signal(list)  # list[FilterCriterion]

    def __init__(
        self,
        model: PaginatedTableModel,
        parent: QWidget | None = None,
        extra_filters: list[FilterEntry] | None = None,
        filters: list[FilterEntry] | None = None,
        filter_locally: bool = True,
        local_filter_keys: set[str] | None = None,
    ) -> None:
        super().__init__(
            parent=parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=4,
        )
        self.setObjectName("AYTableFilter")
        self.setFixedHeight(32)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._model = model
        self._filter_locally = filter_locally
        self._local_filter_keys = set(local_filter_keys or set())
        self._filter_columns = list(model.columns)
        if filters is not None:
            self._filters = list(filters)
        else:
            self._filters = [
                FilterEntry(
                    key=column.key,
                    label=column.label,
                    values=[],
                    icon=column.icon,
                    entity=column.entity,
                )
                for column in model.columns
                if column.filterable
            ]
        if extra_filters:
            self._filters.extend(extra_filters)
        self._criteria: list[FilterCriterion] = []
        self._editing_criterion: FilterCriterion | None = None

        # Proxy model wraps the source model
        self._proxy = AYTableFilterProxyModel(self)
        self._proxy.setSourceModel(model)
        self._proxy.set_row_value_getter(self._get_row_value)
        self._proxy.set_tree_state_getters(
            self._is_tree_mode,
            self._has_unloaded_children,
        )
        # Re-filter whenever new rows are loaded
        model.rowsInserted.connect(lambda *_: self._proxy.refresh_filter())

        # Shared dropdown instance (reused across open calls)
        self._dropdown = _FilterDropdown(
            model,
            self,
            filters=self._filters,
        )
        self._dropdown.criterion_ready.connect(self._on_criterion_ready)

        # search button - always visible, opens empty dropdown for new
        # criterion
        self._search_btn = AYButton(
            icon="search",
            variant=AYButton.Variants.Nav_Small,
        )
        self._search_btn.setFixedSize(24, 24)
        self._search_btn.clicked.connect(self._open_filter_dropdown)
        self.add_widget(self._search_btn)
        self._filter_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self._filter_shortcut.activated.connect(self._open_filter_dropdown)

        # main container for criteria badges
        self._criteria_container = AYHBoxLayout(spacing=4, margin=0)
        self.add_layout(self._criteria_container, stretch=1)

        self._rebuild_bar()

    def minimumSizeHint(self) -> QSize:
        """Keep badge widths from increasing the containing UI minimum."""
        return QSize(self._search_btn.width() + 100, self.height())

    def _open_filter_dropdown(self) -> None:
        """Open the filter dropdown for a new criterion."""
        self._editing_criterion = None
        self._dropdown.open_for_new(self)

    def _get_row_value(self, index: QModelIndex, key: str) -> Any:
        """Return an extra filter value for a source-model row."""
        node = index.internalPointer()
        return getattr(node, "row_data", {}).get(key)

    def _is_tree_mode(self) -> bool:
        """Return whether the source model currently represents a tree."""
        return bool(getattr(self._model, "_tree_mode", False))

    @staticmethod
    def _has_unloaded_children(index: QModelIndex) -> bool:
        """Return whether a tree row has children that are not loaded."""
        node = index.internalPointer()
        return bool(
            node is not None
            and getattr(node, "row_has_children", False)
            and not getattr(node, "children_loaded", True)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def filter_model(self) -> AYTableFilterProxyModel:
        """Return the proxy model to set on the view."""
        return self._proxy

    def get_criteria(self) -> list[FilterCriterion]:
        """Return a copy of the currently active filter criteria.

        Returns:
            A new list of :class:`FilterCriterion` instances.
        """
        return list(self._criteria)

    def set_active_criteria(self, criteria: list[FilterCriterion]) -> None:
        """Replace the active filter criteria and refresh the bar/proxy.

        Distinct from :meth:`AYTableFilterProxyModel.set_criteria` —
        the proxy method takes ``(criteria, columns)`` and lives on the
        proxy instance returned by :attr:`filter_model`.  Calling that
        proxy method directly bypasses the bar's badge rendering and is
        unsupported for external callers.

        Args:
            criteria: New criteria to apply.  An empty list clears the
                filter bar.
        """
        self._criteria = list(criteria)
        self._editing_criterion = None
        self._rebuild_bar()
        self._update_proxy()

    def set_columns(self, columns: list[TableColumn]) -> None:
        """Update the source columns used for local filtering."""
        self._filter_columns = list(columns)
        self._update_proxy()

    def set_filters(
        self,
        filters: list[FilterEntry],
        retain_unavailable_criteria: bool = True,
    ) -> None:
        """Replace available filters and optionally prune stale criteria."""
        self._filters = list(filters)
        self._dropdown.set_filters(self._filters)
        if retain_unavailable_criteria:
            return

        available_keys = {item.key for item in self._filters}
        available_keys.update(column.key for column in self._filter_columns)
        criteria = [
            item for item in self._criteria
            if item.key in available_keys
        ]
        if criteria == self._criteria:
            return
        self._criteria = criteria
        self._rebuild_bar()
        self._update_proxy()

    def set_local_filter_keys(self, keys: set[str]) -> None:
        """Set criteria that should always be evaluated by the proxy."""
        normalized = set(keys)
        if self._local_filter_keys == normalized:
            return
        self._local_filter_keys = normalized
        self._update_proxy()

    def set_filter_entry_values(
        self,
        key: str,
        values: list[str],
    ) -> None:
        """Update the fixed values offered by an extra filter entry."""
        for entry in self._filters:
            if entry.key == key:
                entry.values = list(values)
                return

    def set_column_filter_values(
        self,
        values: dict[str, list[str]],
    ) -> None:
        """Set project-wide values offered for regular column filters."""
        self._dropdown.set_column_values(values)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Open the add-filter menu when unused bar space is clicked."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._open_filter_dropdown()
        super().mousePressEvent(event)

    # ------------------------------------------------------------------
    # Bar management
    # ------------------------------------------------------------------

    def _rebuild_bar(self) -> None:
        """Clear and repopulate the bar with current criteria."""
        self._criteria_container.clear()

        if not self._criteria:
            empty_btn = AYButton(
                "Filter",
                variant=AYButton.Variants.Table_Filter,
                label_alignment=Qt.AlignmentFlag.AlignLeft,
                fixed_width=False,
            )
            empty_btn.clicked.connect(self._open_filter_dropdown)
            self._criteria_container.addWidget(empty_btn)
            return

        for i, criterion in enumerate(self._criteria):
            if i > 0:
                sep = AYLabel("and", dim=True)
                sep.setContentsMargins(2, 0, 2, 0)
                sep.setAttribute(
                    Qt.WidgetAttribute.WA_TransparentForMouseEvents
                )
                self._criteria_container.addWidget(sep)

            badge = _CriterionBadge(criterion)
            badge.edit_requested.connect(self._on_badge_edit)
            badge.remove_requested.connect(self._on_badge_remove)
            self._criteria_container.addWidget(badge)

        # "+" button to add another criterion
        add_btn = AYButton(
            icon="add",
            variant=AYButton.Variants.Nav_Small,
        )
        add_btn.setFixedSize(24, 24)
        add_btn.clicked.connect(self._open_filter_dropdown)
        self._criteria_container.addWidget(add_btn)

        self._criteria_container.addStretch()

    # ------------------------------------------------------------------
    # Criterion handlers
    # ------------------------------------------------------------------

    def _get_criterion_label(self, key: str) -> str:
        """Return the qualified label shown for an active criterion."""
        entry = next(
            (item for item in self._filters if item.key == key),
            None,
        )
        if entry is None or entry.entity == "Other":
            return entry.label if entry is not None else key
        return f"{entry.entity} {entry.label}"

    def _on_criterion_ready(
        self, key: str, values: list[str], use_substring: bool
    ) -> None:
        criterion_label = self._get_criterion_label(key)
        if not values:
            # Empty apply — remove existing criterion for this key if any
            self._criteria = [c for c in self._criteria if c.key != key]
        elif self._editing_criterion is not None:
            # Update in-place
            self._editing_criterion.values = values
            self._editing_criterion.use_substring = use_substring
            self._editing_criterion.attribute_label = criterion_label
        else:
            # Check if criterion for this key already exists
            existing = next((c for c in self._criteria if c.key == key), None)
            if existing:
                existing.values = values
                existing.use_substring = use_substring
                existing.attribute_label = criterion_label
            else:
                self._criteria.append(
                    FilterCriterion(
                        key=key,
                        attribute_label=criterion_label,
                        values=values,
                        use_substring=use_substring,
                    )
                )

        self._editing_criterion = None
        self._rebuild_bar()
        self._update_proxy()

    def _on_badge_edit(self, criterion: FilterCriterion) -> None:
        self._editing_criterion = criterion
        self._dropdown.open_for_edit(criterion, self)

    def _on_badge_remove(self, criterion: FilterCriterion) -> None:
        self._criteria = [c for c in self._criteria if c is not criterion]
        self._rebuild_bar()
        self._update_proxy()

    def _update_proxy(self) -> None:
        if self._filter_locally:
            criteria = self._criteria
        else:
            criteria = [
                item
                for item in self._criteria
                if item.key in self._local_filter_keys
            ]
        self._proxy.set_criteria(
            criteria,
            self._filter_columns,
            self._filters,
        )
        self.filters_changed.emit(list(self._criteria))
