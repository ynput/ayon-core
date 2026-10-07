"""QSS override module. NOT CURRENTLY USED."""

from __future__ import annotations

from qtpy.QtCore import QEvent, QObject
from qtpy.QtGui import QPainter
from qtpy.QtWidgets import QStyle, QStyleOptionFrame, QWidget

from ..style_types import get_ayon_style


class AYONStyleEventFilter(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        object_name: str | None = None,
    ) -> None:
        super().__init__(parent, objectName=object_name)
        self._ayon_style = get_ayon_style()

    def eventFilter(self, obj, event: QEvent) -> bool:
        # Handle paint events for child widgets
        if event.type() == QEvent.Type.Paint:
            if isinstance(obj, QWidget):
                # Custom painting logic for child widget backgrounds
                p = QPainter(obj)
                option = QStyleOptionFrame()
                obj.initStyleOption(option)
                self._ayon_style.drawControl(
                    QStyle.ControlElement.CE_ShapedFrame, option, p, obj
                )
                p.end()
                return False
        # Continue with default event handling
        return super().eventFilter(obj, event)


def _collect_child_widgets(w: QWidget, seen: set[int], out: list) -> None:
    """Recursively collect all widgets including those in layouts."""
    if id(w) in seen:
        return

    seen.add(id(w))
    out.append(w)

    # Collect direct widget children
    for child in w.children():
        if isinstance(child, QWidget):
            _collect_child_widgets(child, seen, out)

    # Collect widgets from layouts
    if (layout := w.layout()) is not None:
        for i in range(layout.count()):
            if (item := layout.itemAt(i)) and (item_widget := item.widget()):
                _collect_child_widgets(item_widget, seen, out)


def install_event_filter(obj) -> None:
    seen_widgets: set[int] = set()

    children = []
    _collect_child_widgets(obj, seen_widgets, children)

    filter_obj = AYONStyleEventFilter(parent=obj)
    # Install event filter on child widgets
    for child in children:
        if not hasattr(child, "paintEvent"):
            child.installEventFilter(filter_obj)
