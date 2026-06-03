"""AYTreeView component module."""

from __future__ import annotations

from qtpy.QtCore import QEvent, QItemSelection, Qt, Signal
from qtpy.QtGui import QColor, QMouseEvent, QCursor, QPainter, QPaintEvent, QPalette
from qtpy.QtWidgets import QStyle, QStyleOption, QTreeView, QWidget

from ..style import TreeViewItemDelegate, enum_to_str, get_ayon_style
from ..variants import QTreeViewVariants
from .scroll_area import AYScrollBar
from .style_mixin import StyleMixin


class AYTreeView(StyleMixin, QTreeView):
    """AYON-styled tree view.

    Fully self-contained: uses AYONStyle for all painting, a custom
    item delegate that draws directly bypassing any parent QSS, and
    AYScrollBar instances for scrollbars.

    Args:
        parent: Optional parent widget.
        variant: Visual style variant controlling background colour and
            item-state colours.
    """

    Variants = QTreeViewVariants
    selection_changed = Signal(QItemSelection, QItemSelection)
    double_clicked = Signal(QMouseEvent)

    def __init__(
        self,
        parent: QWidget | None = None,
        variant: QTreeViewVariants = QTreeViewVariants.Default,
    ) -> None:
        self._variant_str: str = variant.value

        super().__init__(parent)

        style = get_ayon_style()
        self.setStyle(style)

        # Self-contained: do not inherit parent background or stylesheet.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)

        # Viewport must also be opaque with our colour.
        self.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground, False
        )
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)
        self._hovered_row_key: tuple | None = None
        self._sync_viewport_palette()

        # Custom item delegate — paints items directly, avoids QSS.
        delegate = TreeViewItemDelegate(
            parent=self,
            style_model=style.model,
            variant=self._variant_str,
        )
        self.setItemDelegate(delegate)

        # Styled scrollbars.
        vsb = AYScrollBar(Qt.Orientation.Vertical, self)
        self.setVerticalScrollBar(vsb)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        hsb = AYScrollBar(Qt.Orientation.Horizontal, self)
        self.setHorizontalScrollBar(hsb)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # No header — single-column hierarchical browser.
        self.setHeaderHidden(True)

        # Indentation from style data.
        tv_style = style.model.get_style("QTreeView", self._variant_str)
        self.setIndentation(int(tv_style.get("indent", 20)))

        # Selection behaviour.
        self.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectionBehavior.SelectRows)

        # No default frame — drawn manually in paintEvent.
        self.setFrameShape(QTreeView.Shape.NoFrame)

    def _sync_viewport_palette(self) -> None:
        """Apply the variant background colour to the viewport palette."""
        style = get_ayon_style()
        tv_style = style.model.get_style("QTreeView", self._variant_str)
        bg = QColor(tv_style.get("background-color", "#252a31"))
        p = self.viewport().palette()
        p.setColor(QPalette.ColorRole.Base, bg)
        p.setColor(QPalette.ColorRole.Window, bg)
        self.viewport().setPalette(p)

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draw the outer container background before the items.

        Args:
            event: The paint event.
        """
        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        style = get_ayon_style()
        tv_style = style.model.get_style("QTreeView", self._variant_str)
        bg = QColor(tv_style.get("background-color", "#252a31"))
        painter.fillRect(self.viewport().rect(), bg)
        painter.end()

        # Let QTreeView draw its items on top.
        super().paintEvent(event)

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            if event.type() == QEvent.Type.MouseMove:
                idx = self.indexAt(event.pos())
                key = (idx.row(), idx.parent()) if idx.isValid() else None
                if key != self._hovered_row_key:
                    self._hovered_row_key = key
                    self.viewport().update()
            elif event.type() == QEvent.Type.Leave:
                if self._hovered_row_key is not None:
                    self._hovered_row_key = None
                    self.viewport().update()
        return super().eventFilter(obj, event)

    def drawBranches(self, painter, rect, index):
        """Draw branch indicators with AYONStyle directly.

        Bypasses ``self.style()`` because, when an application-level QSS is
        active, Qt wraps the widget's style in a ``QStyleSheetStyle`` proxy
        which would otherwise intercept ``PE_IndicatorBranch`` and apply
        QSS ``QTreeView::branch`` rules on top of (or instead of) ours.
        """
        style = get_ayon_style()  # the raw AYONStyle, never wrapped

        opt = QStyleOption()
        opt.rect = rect
        opt.palette = self.palette()
        state = QStyle.StateFlag.State_Item
        if self.model() is not None and self.model().hasChildren(index):
            state |= QStyle.StateFlag.State_Children
        if self.isExpanded(index):
            state |= QStyle.StateFlag.State_Open
        if self.selectionModel().isSelected(index):
            state |= QStyle.StateFlag.State_Selected
        if self.isEnabled():
            state |= QStyle.StateFlag.State_Enabled

        # Row-level hover: is the cursor on the same row as `index`?
        hovered_index = self.indexAt(
            self.viewport().mapFromGlobal(QCursor.pos())
        )
        if (
            hovered_index.isValid()
            and hovered_index.row() == index.row()
            and hovered_index.parent() == index.parent()
        ):
            state |= QStyle.StateFlag.State_MouseOver

        opt.state = state

        # Call our drawer directly, not through self.style().
        style.drawers[
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorBranch,
                "QTreeView",
            )
        ](opt, painter, self)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Emit double_clicked signal on double-click."""
        self.double_clicked.emit(event)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        """Deselect all items when clicking in an empty area."""
        index = self.indexAt(event.pos())
        if not index.isValid():
            self.clearSelection()
            self.setCurrentIndex(self.rootIndex())
            return
        super().mousePressEvent(event)

    def selectionChanged(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        """Override to emit a public signal on selection change.

        Args:
            selected: Newly selected items.
            deselected: Newly deselected items.
        """
        super().selectionChanged(selected, deselected)
        self.selection_changed.emit(selected, deselected)


# =============================================================================
# __main__ - visual test harness
# =============================================================================

if __name__ == "__main__":
    from qtpy import QtWidgets

    try:
        from qtmaterialsymbols import get_icon  # type: ignore
    except ImportError:
        from ..vendor.qtmaterialsymbols import get_icon  # noqa: F401

    from ..tester import Style, test

    def _build() -> QtWidgets.QWidget:
        """Show one AYTreeView per variant with lazy-loaded fake data."""
        from .layouts import AYVBoxLayout
        from .tree_model import LazyTreeModel, TreeNode, PRODUCTS_TEST_DATA

        def fetch_children(
            parent_id: str | None,
        ) -> list[TreeNode]:
            print(f"fetching children of {parent_id}")
            return PRODUCTS_TEST_DATA.get(parent_id, [])

        # ----------------------------------------------------------

        container = QtWidgets.QWidget()
        root_lyt = AYVBoxLayout(container, margin=8, spacing=8)

        for variant in AYTreeView.Variants:
            label = QtWidgets.QLabel(f"variant: {variant.value}")
            label.setFixedHeight(20)
            root_lyt.addWidget(label)

            tv = AYTreeView(variant=variant)
            tv.setModel(LazyTreeModel(fetch_children=fetch_children))
            tv.setMinimumHeight(160)
            root_lyt.addWidget(tv)

            tv.selection_changed.connect(
                lambda selected, deselected, tv=tv: print(
                    "selection changed: "
                    f"Selected {[i.data() for i in selected.indexes()]} "
                    f"and deselected {[i.data() for i in deselected.indexes()]}) "
                    f"(full selection: {[i.data() for i in tv.selectedIndexes()]})"
                )
            )

        container.setMinimumWidth(360)
        return container

    test(_build, style=Style.AyonStyleOverCSS)
