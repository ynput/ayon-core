from __future__ import annotations

from qtpy import QtWidgets
from qtpy.QtCore import (
    QAbstractItemModel,
    QEvent,
    QSortFilterProxyModel,
    Qt,
    Signal,
)

from .buttons import AYButton
from .combo_box import AYComboBox
from .container import AYContainer
from .line_edit import AYLineEdit


class TreeFilterProxyModel(QSortFilterProxyModel):
    """Proxy that filters tree items, recursively, by an AND-of-terms
    case-insensitive substring match against the model's filter role.

    The match is "fuzzy" in the same sense as the Launcher's folders
    widget (``ayon_core.tools.utils.folders_widget.FoldersProxyModel``):
    the search text is casefolded and split on whitespace, and every
    resulting term must appear as a substring somewhere in the row's
    filter-role text, rather than requiring one literal contiguous
    match. Recursive filtering means a row also stays visible when one
    of its descendants matches, so a matched folder deep in the
    hierarchy keeps its ancestor chain visible.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.setRecursiveFilteringEnabled(True)  # Qt 5.10+
        self._filter_terms: list[str] = []

    def set_filter_text(self, text: str) -> None:
        """Update the active search terms and re-apply the filter."""
        self._filter_terms = text.casefold().split()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if not self._filter_terms:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return True
        index = source_model.index(source_row, 0, source_parent)
        text = index.data(self.filterRole())
        if not text:
            return False
        text = str(text).casefold()
        return all(term in text for term in self._filter_terms)


class AYSlicer(AYContainer):
    category_changed = Signal(str)

    def __init__(self, item_list=None, parent=None, initial_text=""):
        super().__init__(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            parent=parent,
        )
        self._combo = AYComboBox(
            items=item_list,
            variant=AYComboBox.Variants.Low,
            show_chevron=False,
        )
        if initial_text:
            self._combo.setCurrentText(initial_text)
        self._field = AYLineEdit(placeholder="Search")
        self._button = AYButton(
            variant=AYButton.Variants.Nav,
            icon="search",
            icon_on="close",
            checkable=True,
        )

        self.add_widget(self._combo)
        self.add_widget(self._field, stretch=1)
        self.add_widget(self._button)

        self._field.setVisible(False)

        # search filter
        self._proxy: TreeFilterProxyModel | None = None
        self._view = None
        self._field.installEventFilter(self)

        # signals
        self._button.toggled.connect(self._on_button_toggled)
        self._field.textChanged.connect(self._on_search_changed)
        self._combo.activated.connect(self._on_category_activated)

    def add_trailing_widget(self, widget: QtWidgets.QWidget) -> None:
        """Append an extra action widget after the search toggle button.

        Lets callers place a mode-aware action (e.g. Browser's slicer
        filter menu) inline with the category/search row without
        ``AYSlicer`` needing to know anything about it.

        Args:
            widget: Widget to append, e.g. an icon button.
        """
        self.add_widget(widget)

    def current_category(self) -> str:
        return self._combo.currentText()

    def set_current_category(self, category: str) -> None:
        """Select a category by its display text."""
        if category == self._combo.currentText():
            return
        self._combo.setCurrentText(category)
        self.category_changed.emit(category)

    def _on_category_activated(self, index: int) -> None:
        """Emit the selected category."""
        self.category_changed.emit(self._combo.itemText(index))

    def set_model(
        self,
        model: QAbstractItemModel,
        view=None,
    ):
        """Insert a filter proxy between model and view.

        Args:
            model: The source model (e.g. LazyTreeModel). When it
                exposes a ``FILTER_ROLE`` class attribute (as
                ``LazyTreeModel`` does), search matches against that
                role instead of the plain display label - see
                :class:`TreeFilterProxyModel`.
            view: The QAbstractItemView that displays the model.
        """
        if self._proxy is None:
            self._proxy = TreeFilterProxyModel(self)
        if self._proxy.sourceModel() is not model:
            self._proxy.setSourceModel(model)
            filter_role = getattr(model, "FILTER_ROLE", None)
            if filter_role is not None:
                self._proxy.setFilterRole(filter_role)
        if view is not None:
            if view.model() is not self._proxy:
                view.setModel(self._proxy)
            self._view = view

    def _on_search_changed(self, text: str):
        """Update the proxy filter when the user types.

        A non-empty search expands the whole tree so recursively
        matched rows - whose ancestors may otherwise still be
        collapsed - are actually visible, matching the Launcher
        folders widget's behaviour on a non-empty filter.
        """
        if self._proxy is None:
            return
        self._proxy.set_filter_text(text)
        if text and self._view is not None:
            self._view.expandAll()

    def _on_button_toggled(self, checked):
        self._combo.setVisible(not checked)
        self._field.setVisible(checked)
        if checked:
            self._field.setFocus()
        else:
            # clear the filter when closing search
            self._field.clear()

    def eventFilter(self, obj, event):
        """Close search field on Escape key press."""
        if (
            obj is self._field
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Escape
        ):
            self._button.setChecked(False)  # triggers _on_button_toggled
            return True
        return super().eventFilter(obj, event)
