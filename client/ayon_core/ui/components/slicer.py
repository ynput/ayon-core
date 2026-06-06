from __future__ import annotations

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
    """Proxy that filters tree items by label, recursively."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterRole(Qt.ItemDataRole.DisplayRole)
        self.setRecursiveFilteringEnabled(True)  # Qt 5.10+


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

        self._field.installEventFilter(self)

        # signals
        self._button.toggled.connect(self._on_button_toggled)
        self._field.textChanged.connect(self._on_search_changed)
        self._combo.currentTextChanged.connect(self._on_category_changed)

    def current_category(self) -> str:
        return self._combo.currentText()

    def _on_category_changed(self, text: str):
        """Notify other widgets of the criteria change."""
        self.category_changed.emit(text)

    def set_model(
        self,
        model: QAbstractItemModel,
        view=None,
    ):
        """Insert a filter proxy between model and view.

        Args:
            model: The source model (e.g. LazyTreeModel).
            view: The QAbstractItemView that displays the model.
        """
        self._proxy = TreeFilterProxyModel(self)
        self._proxy.setSourceModel(model)
        if view is not None:
            view.setModel(self._proxy)
        self._view = view

    def _on_search_changed(self, text: str):
        """Update the proxy filter when the user types."""
        if self._proxy is None:
            return
        self._proxy.setFilterFixedString(text)

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


if __name__ == "__main__":
    from functools import partial

    from qtmaterialsymbols import get_icon  # type: ignore  # noqa: F401

    from ..tester import Style, test
    from .tree_model import (
        PRODUCTS_TEST_DATA,
        REVIEWS_TEST_DATA,
        LazyTreeModel,
        TreeNode,
    )
    from .tree_view import AYTreeView

    _DATA = PRODUCTS_TEST_DATA

    def _build():
        def fetch_children(
            parent_id: str | None,
        ) -> list[TreeNode]:
            print(f"fetching children of {parent_id!r}")
            return _DATA.get(parent_id, [])

        def _update_model(_tv, _slicer, _category: str):
            global _DATA
            print(f"category changed to {_category!r}")
            if _category == "Products":
                _DATA = PRODUCTS_TEST_DATA
            elif _category == "Reviews":
                _DATA = REVIEWS_TEST_DATA
            # reset the model
            mod = tv.model()
            if isinstance(mod, TreeFilterProxyModel):
                mod = mod.sourceModel()
            mod.reset()
            _slicer.set_model(mod, view=tv)

        w = AYContainer(
            variant=AYContainer.Variants.High,
            layout=AYContainer.Layout.VBox,
            layout_margin=20,
            layout_spacing=10,
        )
        w.setMinimumWidth(400)

        items = [
            {
                "text": "Products",
                "short_text": "PRD",
                "icon": "photo_library",
                "color": "#f4f5f5",
            },
            {
                "text": "Reviews",
                "short_text": "REV",
                "icon": "subscriptions",
                "color": "#f4f5f5",
            },
        ]

        slicer = AYSlicer(item_list=items)
        w.add_widget(slicer)

        tv = AYTreeView(variant=AYTreeView.Variants.Low)
        tv.setModel(LazyTreeModel(fetch_children=fetch_children))
        tv.setMinimumHeight(300)
        w.add_widget(tv)

        # pass the data to be filtered.
        slicer.set_model(tv.model(), view=tv)

        # update the model when the slicer changes
        slicer.category_changed.connect(partial(_update_model, tv, slicer))

        return w

    test(_build, Style.AyonStyleOverCSS)
