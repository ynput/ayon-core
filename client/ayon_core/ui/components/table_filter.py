from __future__ import annotations

from dataclasses import dataclass, field

from qtpy.QtCore import (
    QModelIndex,
    QPersistentModelIndex,
    QSortFilterProxyModel,
    Qt,
    Signal,
)
from qtpy.QtGui import QMouseEvent
from qtpy.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QWidget,
)

from .buttons import AYButton
from .check_box import AYCheckBox
from .container import AYContainer
from .dropdown import AYDropdownPopup
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYHBoxLayout, AYVBoxLayout
from .line_edit import AYLineEdit
from .table_model import PaginatedTableModel, TableColumn

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
    exclude: bool = False


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
        self._key_to_col: dict[str, int] = {}
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_criteria(
        self,
        criteria: list[FilterCriterion],
        columns: list[TableColumn],
    ) -> None:
        """Replace active criteria and refresh the filter.

        Args:
            criteria: List of active filter criteria.
            columns: Column definitions from the source model.
        """
        self._criteria = [c for c in criteria if c.values]
        self._columns = columns
        self._key_to_col = {col.key: idx for idx, col in enumerate(columns)}
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
            col_idx = self._key_to_col.get(criterion.key)
            if col_idx is None:
                continue
            index = source_model.index(source_row, col_idx, source_parent)
            cell_value = source_model.data(index, Qt.ItemDataRole.DisplayRole)
            cell_str = str(cell_value).lower() if cell_value else ""

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
            isinstance(source_model, PaginatedTableModel)
            and source_model._tree_mode
        ):
            src_idx = source_model.index(source_row, 0, source_parent)
            node = src_idx.internalPointer()
            if (
                node is not None
                and node.row_has_children
                and not node.children_loaded
            ):
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
                         Passes (key, values, use_substring, excludes).
        popup_closed: Inherited from ``AYDropdownPopup``. Emitted when
            the popup is dismissed.
    """

    criterion_ready = Signal(
        str, list, bool, bool
    )  # key, values, use_substring

    def __init__(
        self,
        model: PaginatedTableModel,
        table_filter: AYTableFilter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            variant=AYDropdownPopup.Variants.Low_Framed_Thin,
            translucent_bg=False,
        )
        self._model = model
        self._table_filter = table_filter
        self._current_key: str = ""
        self._current_label: str = ""
        self._value_buttons: dict[str, AYButton] = {}
        self._is_free_text: bool = False

        self.setMinimumWidth(220)

        self._build()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root_layout = AYVBoxLayout(self, margin=4, spacing=4)

        self._stack = QStackedWidget(self)
        root_layout.addWidget(self._stack)

        self._stack.addWidget(self._build_attribute_page())
        self._stack.addWidget(self._build_value_page())

    def _build_attribute_page(self) -> QWidget:
        """Build Page 0 - attribute selector."""
        page = AYFrame(variant=AYFrame.Variants.Low)
        layout = AYVBoxLayout(page, margin=0, spacing=4)

        # Search field
        self._attr_search = AYLineEdit(
            placeholder="Search or filter...",
            variant=AYLineEdit.Variants.Search_Field,
        )
        self._attr_search.textChanged.connect(self._on_attr_search_changed)
        layout.addWidget(self._attr_search)

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
        layout.addWidget(scroll)

        self._attr_scroll = scroll
        return page

    def _build_value_page(self) -> QWidget:
        """Build Page 1 - value selector."""
        page = AYFrame(variant=AYFrame.Variants.Low)
        layout = AYVBoxLayout(page, margin=0, spacing=4)
        layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

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
        self._back_btn = AYButton(
            "Back",
            icon="arrow_back",
            variant=AYButton.Variants.Nav_Small,
        )
        self._back_btn.clicked.connect(self._go_to_attribute_page)
        footer.add_widget(self._back_btn)
        footer.addStretch()
        self._exclude_checkbox = AYCheckBox(
            "Excludes",
            variant=AYCheckBox.Variants.Button,
        )
        footer.add_widget(self._exclude_checkbox)
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
        self._populate_attribute_page()
        self._attr_search.clear()
        self._stack.setCurrentIndex(0)
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
        self.show_below(anchor)

    # ------------------------------------------------------------------
    # Attribute page helpers
    # ------------------------------------------------------------------

    def _populate_attribute_page(self) -> None:
        """Rebuild the attribute button list from model columns."""
        # Remove old buttons
        while self._attr_layout.count():
            item = self._attr_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._attr_buttons: dict[str, AYButton] = {}

        for col in self._model.columns:
            if not col.filterable:
                continue
            btn = AYButton(
                col.label,
                icon=col.icon or "",
                icon_color="#dedede",
                variant=AYButton.Variants.Text,
                fixed_width=False,
                label_alignment=Qt.AlignmentFlag.AlignLeft,
            )
            btn.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
            )
            btn.clicked.connect(
                lambda checked,
                k=col.key,
                lbl=col.label: self._on_attr_selected(k, lbl)
            )
            self._attr_buttons[col.key] = btn
            self._attr_layout.addWidget(btn)

        self._attr_layout.addStretch()
        self._adjust_height()

    def _on_attr_search_changed(self, text: str) -> None:
        query = text.lower().strip()
        for key, btn in self._attr_buttons.items():
            col = next((c for c in self._model.columns if c.key == key), None)
            label = col.label if col else key
            btn.setVisible(not query or query in label.lower())
        self._adjust_height()

    def _on_attr_selected(self, key: str, label: str) -> None:
        self._populate_value_page(key, label, [])
        self._stack.setCurrentIndex(1)
        self._adjust_height()

    def _go_to_attribute_page(self) -> None:
        self._stack.setCurrentIndex(0)
        self._adjust_height()

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

        # Clear previous content
        self._value_content_layout.clear()

        distinct = self._model.get_distinct_values(key)

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
                btn = AYButton(
                    val,
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
                inner_layout.addWidget(btn)

            inner_layout.addStretch()
            scroll.setWidget(inner)
            self._value_content_layout.addWidget(scroll)
        else:
            self._is_free_text = True
            self._free_text_edit = AYLineEdit(
                placeholder="Search", variant=AYLineEdit.Variants.Search_Field
            )
            if selected_values:
                self._free_text_edit.setText(selected_values[0])
            self._value_content_layout.addWidget(self._free_text_edit)

    def _on_apply(self) -> None:
        if not self._current_key:
            return

        if self._is_free_text:
            text = self._free_text_edit.text().strip()
            values = [text] if text else []
            use_substring = True
        else:
            values = [
                val
                for val, btn in self._value_buttons.items()
                if btn.isChecked()
            ]
            use_substring = False

        excludes = self._exclude_checkbox.isChecked()

        self.criterion_ready.emit(
            self._current_key, values, use_substring, excludes
        )
        self.close()

    # ------------------------------------------------------------------
    # Positioning / layout helpers
    # ------------------------------------------------------------------

    def _adjust_height(self) -> None:
        """Resize popup to fit current page content."""
        _MAX_H = 420
        _ROW_H = 32  # nominal height per button row
        _CHROME = 24  # root layout margins + spacing overhead

        if self._stack.currentIndex() == 0 and hasattr(self, "_attr_buttons"):
            visible = [
                b for b in self._attr_buttons.values() if not b.isHidden()
            ]
            search_h = max(self._attr_search.sizeHint().height(), 28)
            desired = search_h + _ROW_H * max(len(visible), 1) + _CHROME
        else:
            # value page: header + scrollable values + apply footer
            desired = self._stack.currentWidget().sizeHint().height() + 8

        self.setFixedHeight(min(desired, _MAX_H))
        self.setMinimumWidth(self._table_filter.width())


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
            icon="check_small"
            if not criterion.exclude
            else "do_not_disturb_on",
            icon_size=16 if not criterion.exclude else 12,
        )
        self.add_widget(front_icon)

        values_text = (
            " or ".join(criterion.values) if criterion.values else "…"
        )
        badge_text = f"{criterion.attribute_label}: {values_text}"

        self._label = AYLabel(badge_text)
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
    ) -> None:
        super().__init__(
            parent=parent,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low_Framed_Thin,
            layout_margin=4,
        )
        self.setObjectName("AYTableFilter")
        self.setFixedHeight(32)

        self._model = model
        self._criteria: list[FilterCriterion] = []
        self._editing_criterion: FilterCriterion | None = None

        # Proxy model wraps the source model
        self._proxy = AYTableFilterProxyModel(self)
        self._proxy.setSourceModel(model)
        # Re-filter whenever new rows are loaded
        model.rowsInserted.connect(lambda *_: self._proxy.refresh_filter())

        # Shared dropdown instance (reused across open calls)
        self._dropdown = _FilterDropdown(model, self)
        self._dropdown.criterion_ready.connect(self._on_criterion_ready)

        # search button - always visible, opens empty dropdown for new
        # criterion
        self._search_btn = AYButton(
            icon="search",
            variant=AYButton.Variants.Nav_Small,
        )
        self._search_btn.clicked.connect(
            lambda: self._dropdown.open_for_new(self)
        )
        self.add_widget(self._search_btn)

        # main container for criteria badges
        self._criteria_container = AYHBoxLayout(spacing=4, margin=0)
        self.add_layout(self._criteria_container, stretch=1)

        self._rebuild_bar()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def filter_model(self) -> AYTableFilterProxyModel:
        """Return the proxy model to set on the view."""
        return self._proxy

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
            empty_btn.clicked.connect(
                lambda: self._dropdown.open_for_new(self)
            )
            self._criteria_container.addWidget(empty_btn)
            return

        for i, criterion in enumerate(self._criteria):
            if i > 0:
                sep = AYLabel("and", dim=True)
                sep.setContentsMargins(2, 0, 2, 0)
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
        add_btn.clicked.connect(lambda: self._dropdown.open_for_new(self))
        self._criteria_container.addWidget(add_btn)

        self._criteria_container.addStretch()

    # ------------------------------------------------------------------
    # Criterion handlers
    # ------------------------------------------------------------------

    def _on_criterion_ready(
        self, key: str, values: list[str], use_substring: bool, excludes: bool
    ) -> None:
        if not values:
            # Empty apply — remove existing criterion for this key if any
            self._criteria = [c for c in self._criteria if c.key != key]
        elif self._editing_criterion is not None:
            # Update in-place
            self._editing_criterion.values = values
            self._editing_criterion.use_substring = use_substring
        else:
            # Check if criterion for this key already exists
            existing = next((c for c in self._criteria if c.key == key), None)
            if existing:
                existing.values = values
                existing.use_substring = use_substring
            else:
                col = next(
                    (c for c in self._model.columns if c.key == key), None
                )
                label = col.label if col else key
                self._criteria.append(
                    FilterCriterion(
                        key=key,
                        attribute_label=label,
                        values=values,
                        use_substring=use_substring,
                        exclude=excludes,
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
        self._proxy.set_criteria(self._criteria, self._model.columns)
        self.filters_changed.emit(list(self._criteria))
