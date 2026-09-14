from __future__ import annotations

import logging
from functools import cmp_to_key

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import (
    QFont,
    QPainter,
)
from qtpy.QtWidgets import (
    QComboBox,
    QCommonStyle,
    QFrame,
    QHeaderView,
    QLabel,
    QStyle,
    QStyleOption,
    QWidget,
)
from qtpy.shiboken import isValid

from .components.combo_box import ComboBoxItemDelegate
from .components.table_view import TableItemDelegate
from .components.tree_view import TreeViewItemDelegate
from .drawers import (
    ButtonDrawer,
    CheckboxDrawer,
    ComboBoxDrawer,
    FrameDrawer,
    ItemViewItemDrawer,
    LabelDrawer,
    LineEditDrawer,
    MenuDrawer,
    ScrollAreaDrawer,
    ScrollBarDrawer,
    TableHeaderDrawer,
    TooltipDrawer,
    TreeViewDrawer,
    enum_to_str,
)
from .style_types import (
    StyleData,
    StyleDict,  # noqa: F401  (re-exported for backward compatibility)
    get_ayon_style,  # noqa: F401  (re-exported for backward compatibility)
    get_ayon_style_data,  # noqa: F401  (re-exported for backward compatibility)
    hsl_to_html_color,  # noqa: F401  (re-exported for backward compatibility)
)

log = logging.getLogger("AYON Style")

W_T = {}


class AYONStyle(QCommonStyle):
    """
    AYON QStyle implementation that replaces QSS styling with native Qt
    painting. Supports widget variants: surface, tonal, filled, tertiary,
    text, nav, etc.
    """

    def __init__(self) -> None:
        super().__init__()
        self.model = StyleData()
        self._in_widget_key = False
        self.drawers = {}
        self.sizers = {}
        self.metrics = {}
        self.base_classes = {}
        self.drawer_objs = [
            TooltipDrawer(self),
            LabelDrawer(self),
            LineEditDrawer(self),
            ButtonDrawer(self),
            CheckboxDrawer(self),
            ComboBoxDrawer(self),
            ScrollBarDrawer(self),
            FrameDrawer(self),
            TreeViewDrawer(self),
            TableHeaderDrawer(self),
            ItemViewItemDrawer(self),
            ScrollAreaDrawer(self),
            MenuDrawer(self),
        ]
        for obj in self.drawer_objs:
            self.base_classes.update(obj.base_class)
            if hasattr(obj, "register_drawers"):
                self.drawers.update(obj.register_drawers())
            if hasattr(obj, "register_sizers"):
                self.sizers.update(obj.register_sizers())
            if hasattr(obj, "register_metrics"):
                self.metrics.update(obj.register_metrics())

        # Sort base_classes: most-specific first to guarantee correct widget
        # key resolution order.
        def _specificity_cmp(a, b):
            """Return <0 if `a` is more specific than `b`.

            More specific means: `a` is a (strict) subclass of `b`.
            For unrelated classes, fall back to MRO depth so deeper
            classes still come first, then class name for stability.
            """
            ca, cb = a[1], b[1]
            if ca is cb:
                return 0
            if issubclass(ca, cb):
                return -1  # a before b
            if issubclass(cb, ca):
                return 1  # b before a
            # Unrelated: deeper MRO first, then name for determinism.
            d = len(cb.__mro__) - len(ca.__mro__)
            if d:
                return d
            return (ca.__name__ > cb.__name__) - (ca.__name__ < cb.__name__)

        self.base_classes = dict(
            sorted(self.base_classes.items(), key=cmp_to_key(_specificity_cmp))
        )

    def widget_key(self, w: QWidget | None) -> str:
        if self._in_widget_key or not w or not isValid(w):
            return ""

        # Handle item view widgets - check parent for delegate and exclude
        # ComboBoxItemDelegate
        if (
            hasattr(w, "itemDelegate")
            and not isinstance(w, (QComboBox, QHeaderView))
        ):
            # Calling itemDelegate() is not a simple getter - it can
            # trigger Qt's internal operations that call back into the
            # custom style methods (subElementRect, drawPrimitive,
            # pixelMetric, etc.), each of which calls widget_key() again,
            # creating infinite recursion.
            self._in_widget_key = True
            try:
                delegate = w.itemDelegate()
                if not isinstance(
                    delegate,
                    (
                        TreeViewItemDelegate,
                        TableItemDelegate,
                        ComboBoxItemDelegate
                    )
                ):
                    return "QStyledItemDelegate"
            finally:
                self._in_widget_key = False

        for name, wtype in self.base_classes.items():
            if not issubclass(type(w), wtype):
                continue

            if w.objectName() == "qtooltip_label":
                return "QToolTip"

            if isinstance(w, QLabel):
                p = w.parent()
                # NOTE: Qt does not use QToolTip but a QLabel (a
                # private QLabelTip class) !!
                # if the parent is a widget and it doesn't have a
                # layout, it could be a tooltip.
                # Sometimes, objectName() == "qtooltip_label" but the
                # object name is set when the rect requests are made.
                if p and isinstance(p, QWidget) and not p.layout():
                    return "QToolTip"
            return name
        return ""

    def style_widget(self, widget: QWidget) -> None:
        """Apply AYON style to a widget (palette, font, hover tracking)."""
        if not isinstance(widget, QWidget):
            return

        variant = getattr(widget, "_variant_str", "default")
        if hasattr(widget, "_style_data") and not widget._style_data:
            widget._style_data = self.model.get_style(
                self.widget_key(widget),
                variant,
            )
            widget._style_data.set_context(widget)

        if hasattr(widget, "set_palette"):
            widget.set_palette(
                self.model.get_style_palette(
                    widget, self.widget_key(widget)
                )
            )
        else:
            widget.setPalette(QtGui.QPalette(self.model.base_palette))

        if hasattr(widget, "set_font"):
            widget.set_font(QFont(self.model.base_font))
        else:
            widget.setFont(QFont(self.model.base_font))

        # Enable mouse tracking for buttons to receive hover events
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget.setMouseTracking(True)

        if isinstance(widget, QComboBox):
            widget.setMinimumContentsLength(1)
            widget.setItemDelegate(
                ComboBoxItemDelegate(parent=widget, style_model=self.model)
            )
            widget.setSizeAdjustPolicy(
                QComboBox.SizeAdjustPolicy.AdjustToContents
            )
        elif isinstance(widget, QLabel):
            # rounded corner no background.
            widget.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, True
            )
        elif isinstance(widget, QtWidgets.QMenu):
            widget.setAttribute(
                Qt.WidgetAttribute.WA_TranslucentBackground, True
            )
            widget.setWindowFlags(
                widget.windowFlags() | Qt.WindowType.NoDropShadowWindowHint
            )

            # make icons visible in menus (MacOS)
            def _setup_actions(menu):
                for action in menu.actions():
                    if action.isSeparator():
                        continue
                    action.setIconVisibleInMenu(True)
                    action.setShortcutVisibleInContextMenu(True)
                    if action.menu():
                        _setup_actions(action.menu())

            _setup_actions(widget)

    def polish(self, widget) -> None:
        """Polish widgets to enable hover tracking and custom palette."""
        if isinstance(widget, QWidget):
            super().polish(widget)
            self.style_widget(widget)

        else:
            super().polish(widget)

    def drawControl(
        self,
        element: QStyle.ControlElement,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget | None = None,
    ) -> None:
        """Draw control elements (buttons, labels, etc.)."""
        key = enum_to_str(QStyle.ControlElement, element, self.widget_key(w))

        if type(w).__name__ in W_T:
            log.info("  >>  drawControl %s %s", type(w), key)

        draw_ce_calls = self.drawers.get(key)
        if draw_ce_calls is None:
            super().drawControl(element, option, painter, w)
            return

        if isinstance(draw_ce_calls, list):
            for draw_ce in draw_ce_calls:
                draw_ce(option, painter, w)
        elif callable(draw_ce_calls):
            draw_ce_calls(option, painter, w)

    def drawComplexControl(
        self,
        cc: QStyle.ComplexControl,
        opt: QtWidgets.QStyleOptionComplex,
        p: QPainter,
        w: QWidget | None = None,
    ) -> None:
        key = enum_to_str(QStyle.ComplexControl, cc, self.widget_key(w))
        if type(w).__name__ in W_T:
            log.info("  >>  drawComplexControl %s %s", type(w), key)

        draw_cc = self.drawers.get(key)
        if draw_cc is None:
            # no custom drawer fallback
            return super().drawComplexControl(cc, opt, p, w)

        draw_cc(opt, p, w)

    def drawPrimitive(
        self,
        element: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget | None = None,
    ) -> None:
        """Draw primitive elements."""

        key = enum_to_str(QStyle.PrimitiveElement, element, self.widget_key(w))
        if type(w).__name__ in W_T:
            log.info("  >>  drawPrimitive %s %s", type(w), key)

        draw_prim = self.drawers.get(key)
        if draw_prim is None:
            # Fall back to parent implementation
            super().drawPrimitive(element, option, painter, w)
            return

        draw_prim(option, painter, w)

    def subElementRect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget | None = None,
    ) -> QRect:
        """Calculate rectangles for sub-elements."""
        key = enum_to_str(QStyle.SubElement, element, self.widget_key(widget))

        if isinstance(widget, QLabel):
            log.debug("%s %s", type(widget).__name__, key)

        sizer = self.sizers.get(key)
        if sizer is None:
            # Fall back to parent implementation
            # Catch RuntimeError in case widget's C++ object was already
            # deleted
            try:
                if widget is not None:
                    return super().subElementRect(element, option, widget)
                return super().subElementRect(element, option)
            except RuntimeError:
                # Widget was deleted, call without it
                return super().subElementRect(element, option)

        return sizer(element, option, widget)

    def subControlRect(
        self,
        cc: QStyle.ComplexControl,
        opt: QtWidgets.QStyleOptionComplex,
        sc: QStyle.SubControl,
        w: QWidget | None = None,
    ) -> QRect:
        key = enum_to_str(QStyle.ComplexControl, cc, self.widget_key(w))

        if isinstance(w, QLabel):
            log.debug("%s %s", type(w).__name__, key)

        sizer = self.sizers.get(key)
        if sizer is None:
            # Fall back to parent implementation
            return super().subControlRect(cc, opt, sc, w)

        try:
            return sizer(cc, opt, sc, w)
        except ValueError:
            return super().subControlRect(cc, opt, sc, w)

    def pixelMetric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Return pixel measurements for various style metrics."""
        key = enum_to_str(QStyle.PixelMetric, metric, self.widget_key(widget))

        if isinstance(widget, QLabel):
            log.debug("%s %s", type(widget), key)

        metric_func = self.metrics.get(key)
        if metric_func is None:
            # Fall back to parent implementation
            return super().pixelMetric(metric, opt, widget)

        return metric_func(metric, opt, widget)

    def styleHint(
        self,
        hint: QStyle.StyleHint,
        opt: QStyleOption | None = None,
        w: QWidget | None = None,
        shret: QtWidgets.QStyleHintReturn | None = None,
    ) -> int:
        """Return style hints for behavior configuration."""

        if hint == QStyle.StyleHint.SH_Button_FocusPolicy:
            return Qt.FocusPolicy.StrongFocus
        elif hint == QStyle.StyleHint.SH_RequestSoftwareInputPanel:
            return 0
        elif hint == QStyle.StyleHint.SH_ComboBox_PopupFrameStyle:
            return QFrame.Shape.NoFrame
        # Fall back to parent implementation
        return super().styleHint(hint, opt, w, shret)

    def sizeFromContents(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QtCore.QSize,
        widget: QWidget | None = None,
    ) -> QtCore.QSize:
        """Calculate minimum size requirements for widgets based on their
        content."""
        key = enum_to_str(
            QStyle.ContentsType, contents_type, self.widget_key(widget)
        )

        if isinstance(widget, QLabel):
            log.debug("%s", widget)

        sizer = self.sizers.get(key)
        if sizer is not None:
            return sizer(contents_type, option, contents_size, widget)

        if option:
            return super().sizeFromContents(
                contents_type, option, contents_size, widget
            )

        # Create a reasonable default size if no option is provided
        return QtCore.QSize(100, 32)
