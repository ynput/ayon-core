from __future__ import annotations

import copy
import json
import logging
from functools import cmp_to_key, partial
from pathlib import Path
from typing import Any
from glob import glob
import os
import platform

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtCore import QRect, QRectF, QSize, Qt
from qtpy.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
)
from qtpy.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QCommonStyle,
    QFrame,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionComplex,
    QStyleOptionFrame,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QToolTip,
    QTreeView,
    QWidget,
)
from qtpy.shiboken import isValid

from .components.style_mixin import StyleMixin

from qtmaterialsymbols import get_icon  # type: ignore


_ayon_style_instance: AYONStyle | None = None


logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s]:   %(funcName)16s:  %(message)s",
)
log = logging.getLogger("Ayon Style")


# DEBUG -----------------------------------------------------------------------


def _debug_rect(p: QPainter, color: str, rect: QRect | QRectF):
    p.save()
    pen = QPen(QColor(color))
    brush = QBrush(Qt.BrushStyle.NoBrush)
    p.setPen(pen)
    p.setBrush(brush)
    p.drawRect(rect)
    p.restore()


# Override the platform key used for OS-specific font sizes.
# Set the ``AYON_CORE_UI_FONT_OS`` env var to a fixed value (e.g. ``"linux"``)
# to make font selection deterministic across machines — useful for visual
# regression tests.


def _font_platform() -> str:
    """Return the platform key used to select OS-specific font sizes.

    Resolution order:
    1. ``AYON_CORE_UI_FONT_OS`` environment variable.
    2. Live ``platform.system()`` result (normalised to lower-case).
    """
    env_val = os.environ.get("AYON_CORE_UI_FONT_OS")
    if env_val:
        return env_val.lower()
    return platform.system().lower()


def _style_font(style: dict, w: QWidget | None) -> QFont:
    font = QFont()
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setFamily(style["font-family"])
    os_name = _font_platform()
    pt_size = style.get(f"font-size-{os_name}", style["font-size"])
    font.setPointSizeF(pt_size)
    font.setWeight(QFont.Weight(style["font-weight"]))
    return font


def _all_enums(t):
    meta_object: QtCore.QMetaObject = t.staticMetaObject
    enums = [
        meta_object.enumerator(v) for v in range(meta_object.enumeratorCount())
    ]
    for enum in enums:
        # enum.isFlag() is always False
        non_empty_indices = [i for i in range(17) if enum.valueToKey(i)]
        is_flag = non_empty_indices == [0, 1, 2, 4, 8, 16]

        print(
            f"  === {enum.scope()}.{enum.enumName()}[{enum.keyCount()}] -- {'Flag' if is_flag else ''}"
        )

        if is_flag:
            for i in range(enum.keyCount()):
                flag_idx = 2**i if i > 0 else 0
                v = enum.valueToKey(flag_idx)
                if v:
                    print(f"    {flag_idx}: {v}")
        else:
            for i in range(enum.keyCount()):
                print(f"    {i}: {enum.valueToKey(i)}")


def _enum_values(enum):
    # qmeta = QtCore.QMetaEnum(enum)
    meta_object: QtCore.QMetaObject = QStyle.staticMetaObject  # type: ignore
    enum_index = meta_object.indexOfEnumerator(enum.__name__)
    meta_enum: QtCore.QMetaEnum = meta_object.enumerator(enum_index)
    num_keys = meta_enum.keyCount()
    vals = [meta_enum.value(v) for v in range(num_keys) if meta_enum.key(v)]
    # print(f"=== enum = {meta_enum.scope()}.{meta_enum.enumName()} -> {keys}")
    return vals


def _enum_values_dict(enum):
    # qmeta = QtCore.QMetaEnum(enum)
    meta_object: QtCore.QMetaObject = QStyle.staticMetaObject  # type: ignore
    enum_index = meta_object.indexOfEnumerator(enum.__name__)
    meta_enum: QtCore.QMetaEnum = meta_object.enumerator(enum_index)
    num_keys = meta_enum.keyCount()
    vals = {
        meta_enum.key(i): meta_enum.value(i)
        for i in range(num_keys)
        if meta_enum.key(i)
    }
    # print(f"=== enum = {meta_enum.scope()}.{meta_enum.enumName()} -> {keys}")
    return vals


def enum_to_str(enum, enum_value: int, widget: str) -> str:
    """Convert enum value to string representation."""
    cachekey = f"{enum.__name__}_{enum_value}_{widget}"
    try:
        return enum_to_str._cache[cachekey]  # type: ignore
    except AttributeError:
        enum_to_str._cache = {}  # type: ignore
    except KeyError:
        pass

    try:
        enum_to_str._cache[cachekey] = enum.valueToKey(enum_value)  # type: ignore
    except AttributeError:
        meta_object = QStyle.staticMetaObject  # type: ignore
        enum_index = meta_object.indexOfEnumerator(enum.__name__)
        meta_enum = meta_object.enumerator(enum_index)
        enum_to_str._cache[cachekey] = (  # type: ignore
            f"{meta_enum.valueToKey(enum_value)}-{widget}"  # type: ignore
        )
        # print(f'{cachekey}: {enum_to_str._cache[cachekey]}')

    return enum_to_str._cache[cachekey]  # type: ignore


def hsl_to_html_color(hsl: str):
    vals = hsl[4:-1].split(", ")
    hue = int(vals[0]) / 360.0
    sat = int(vals[1][:-1]) / 100.0
    lum = int(vals[2][:-1]) / 100.0
    return QColor.fromHslF(hue, sat, lum).name()


def do_nothing(*args, **kwargs):
    pass


# ----------------------------------------------------------------------------


def get_ayon_style() -> AYONStyle:
    """Get the singleton AYONStyle instance.

    Returns:
        The singleton AYONStyle instance.
    """
    global _ayon_style_instance
    if _ayon_style_instance is None:
        _ayon_style_instance = AYONStyle()
    return _ayon_style_instance


def get_ayon_style_data(
    widget_cls: str, variant: str | None = None
) -> StyleDict:
    """Get the AYON style data.

    Returns:
        The AYON style data.
    """
    return get_ayon_style().model.get_style(
        widget_cls, variant=variant, state="all"
    )


def style_widget_and_siblings(widget: QWidget, fix_app: bool = False) -> None:
    """Apply AYON style to a widget and its siblings recursively.

    Removes any existing stylesheets and applies the AYON QStyle
    to the given widget and all its sibling widgets (widgets that
    share the same parent), including all their nested children
    even if they are in QLayouts.

    Args:
        widget: The widget whose siblings (and itself) will be styled.
        fix_app: Whether to temporarily remove and restore app stylesheet.
    """

    def _collect_widgets(w: QWidget, seen: set[int]) -> None:
        """Recursively collect all widgets including those in layouts."""
        if id(w) in seen:
            return

        seen.add(id(w))
        widgets_to_style.append(w)

        # Collect direct widget children
        for child in w.children():
            if isinstance(child, QWidget):
                _collect_widgets(child, seen)

        # Collect widgets from layouts
        if (layout := w.layout()) is not None:
            for i in range(layout.count()):
                if (item := layout.itemAt(i)) and (
                    item_widget := item.widget()
                ):
                    _collect_widgets(item_widget, seen)

    # Determine root widgets: siblings if parent exists, otherwise just widget
    root_widgets = [widget]

    # Collect all widgets recursively
    seen_widgets: set[int] = set()
    widgets_to_style: list[QWidget] = []
    for w in root_widgets:
        _collect_widgets(w, seen_widgets)

    qss = None
    app = QApplication.instance()
    if fix_app and app and isinstance(app, QApplication):
        qss = copy.copy(app.property("styleSheet"))

    if fix_app and qss and isinstance(app, QApplication):
        app.setStyleSheet("")

    widget.setAttribute(Qt.WidgetAttribute.WA_WindowPropagation, False)

    # Apply style to all collected widgets
    style = get_ayon_style()
    for w in widgets_to_style:
        w.style().unpolish(w)
        w.setStyle(style)

    if fix_app and qss and isinstance(app, QApplication):
        app.setStyleSheet(qss)


class StyleDict(dict):
    """A dict where string values starting with '@' are resolved
    via getattr() on a bound context object.

    Example:
        ctx = SomeWidget(...)
        d = StyleDict({"color": "@fg_color"}, _context=ctx)
        d["color"]  # -> ctx.fg_color
    """

    _SENTINEL = object()

    def __init__(
        self,
        *args: Any,
        _context: Any = None,
        deepcopy: bool = True,
        **kwargs: Any,
    ) -> None:
        if deepcopy:
            args = copy.deepcopy(args)
            kwargs = copy.deepcopy(kwargs)
        super().__init__(*args, **kwargs)
        # store as attribute on the instance — not as a dict key
        object.__setattr__(self, "_context", _context)
        # convert nested dicts to StyleDicts with the same context
        for k, v in self.items():
            super().__setitem__(
                k,
                StyleDict(v, _context=_context) if isinstance(v, dict) else v,
            )

    def set_context(self, _context: Any) -> None:
        object.__setattr__(self, "_context", _context)
        for v in self.values():
            if isinstance(v, StyleDict):
                v.set_context(_context)

    def __getitem__(self, key: str) -> Any:
        value = super().__getitem__(key)
        return self._resolve(value)

    def get(self, key: str, default: Any = None, raw: bool = False) -> Any:
        value = super().get(key, self._SENTINEL)
        if value is self._SENTINEL:
            return default
        if raw:
            return value
        return self._resolve(value)

    def _resolve(self, value: Any) -> Any:
        if (
            isinstance(value, str)
            and value.startswith("@")
            and self._context is not None
        ):
            return getattr(self._context, value[1:], value)
        return value

    def __repr__(self) -> str:
        return f"StyleDict({super().__repr__()}, context={self._context!r})"


class StyleData:
    def __init__(self) -> None:
        fpath = Path(__file__).parent / "ayon_style.json"
        with open(fpath, "r") as fh:
            self.data = json.load(fh)
        # Palette values can reference each other
        self._palette = self.data.get("palette", {})
        for k, v in self._palette.items():
            if v.startswith("hsl("):
                self._palette[k] = hsl_to_html_color(v)
        for k, v in self._palette.items():
            self._palette[k] = self._palette.get(v, v)
        for k, v in self._palette.items():
            if v in self._palette:
                raise ValueError(f"Unresolved palette value in {k}")
        # cache
        self._cache = {}
        self.last_key = ""
        # base palette
        self.base_palette: QPalette = self._build_palette()
        self._base_font: QFont | None = None
        self._base_font_checked: bool = False

    @property
    def base_font(self) -> QFont:
        # delayed to make sure QApplication is initialized
        if self._base_font is None:
            self._base_font = _style_font(
                self.data.get("global", {}), QWidget()
            )
            if not self._base_font_checked:
                self._check_font_availability(self._base_font)
        return QFont(self._base_font)

    def _check_font_availability(self, font: QFont):
        # check if the font is available and load it if need be.
        families = QFontDatabase.families()
        if font.family() not in families:
            # Attempt to load from resources
            font_name = font.family().replace(" ", "")
            glob_path = str(
                Path(__file__).parent / "resources" / f"{font_name}*.ttf"
            )
            font_files = glob(glob_path)

            if not font_files:
                log.error(
                    f"Base font '{font.family()}' is not available and no font "
                    f"files were found in '{glob_path}'"
                )
            else:
                for font_path in font_files:
                    if QFontDatabase.addApplicationFont(str(font_path)) == -1:
                        log.error(f"Failed to load base font from {font_path}")
                    else:
                        log.debug(f"Loaded base font file {font_path}")
        self._base_font_checked = True

    def _build_palette(self) -> QPalette:
        bp = {
            QPalette.ColorRole.Window: "qt-active-window",
            QPalette.ColorRole.WindowText: "qt-active-window-text",
            QPalette.ColorRole.Base: "qt-active-base",
            QPalette.ColorRole.Text: "qt-active-text",
            QPalette.ColorRole.Link: "qt-active-link",
            QPalette.ColorRole.Button: "qt-active-button",
            QPalette.ColorRole.ButtonText: "qt-active-button-text",
            QPalette.ColorRole.PlaceholderText: "qt-active-placeholder-text",
            QPalette.ColorRole.Highlight: "qt-active-highlight",
            QPalette.ColorRole.HighlightedText: "qt-active-highlight-text",
            QPalette.ColorRole.Light: "qt-active-light",
            QPalette.ColorRole.Midlight: "qt-active-midlight",
            QPalette.ColorRole.Dark: "qt-active-dark",
            QPalette.ColorRole.Mid: "qt-active-mid",
            QPalette.ColorRole.Shadow: "qt-active-shadow",
        }
        p = QPalette()
        for role, color_name in bp.items():
            p.setColor(
                QPalette.ColorGroup.Active,
                role,
                QColor(self._palette.get(color_name, "#ff0000")),
            )
        return p

    def get_style_palette(self, widget: QWidget, widget_key: str) -> QPalette:
        """Get a QPalette for the widget based on the current style data.

        Resolves any @ references in the style data to widget attributes.
        Caches results for efficiency, if there are no @ references.
        """
        variant = getattr(widget, "_variant_str", "default")
        # check if cached
        cache_key = f"{widget_key}-{variant}-palette"
        if cache_key in self._cache:
            return QPalette(self._cache[cache_key])

        style: StyleDict = self.get_styles(
            widget_key,
            variant=variant,
        )
        style.set_context(widget)

        p = QPalette(self.base_palette)

        fg_color = style.get("base", {}).get("color")
        if fg_color:
            p.setColor(
                widget.foregroundRole(),
                QColor(fg_color),
            )
        opacity = style.get("disabled", {}).get("opacity")
        if opacity:
            disabled_fg_color = QColor(fg_color)
            disabled_fg_color.setAlphaF(opacity)
            p.setColor(
                QPalette.ColorGroup.Disabled,
                widget.foregroundRole(),
                disabled_fg_color,
            )

        bg_color = style.get("base", {}).get("background-color")
        if bg_color:
            p.setColor(
                widget.backgroundRole(),
                QColor(bg_color),
            )

        # cache result
        style.set_context(None)
        self._cache[cache_key] = p

        return QPalette(p)

    def dump_cache_stats(self):
        print(f"[StyleData] cached {len(self._cache)} styles.")
        print(f"[StyleData]   >> {list(self._cache.keys())}")

    def widget_variants(self, widget_cls: str) -> list[str]:
        return list(
            self.data["widgets"].get(widget_cls, {}).get("variants", {}).keys()
        )

    def widget_states(self, widget_cls: str) -> list[str]:
        states = list(
            self.data["widgets"].get(widget_cls, {}).get("states", [])
        )
        return states if "base" in states else ["base"] + states

    def widget_data(self, widget_cls: str) -> dict:
        return self.data["widgets"].get(widget_cls, {})

    def widget_list(self) -> list[str]:
        return list(self.data["widgets"].keys())

    def default_variant(self, widget_data) -> str:
        variants = widget_data.get("variants", {})
        return widget_data.get(
            "default-variant", next(iter(variants.keys()), "default")
        )

    def validate_variant(self, widget_data, variant) -> str:
        if variant not in widget_data.get("variants", {}):
            return self.default_variant(widget_data)
        return variant

    def palette(self):
        return self._palette

    def get_style(
        self,
        widget_cls: str,
        variant=None,
        state="base",
    ) -> StyleDict:
        """Returns a style for a widget, variant and state."""
        try:
            return StyleDict(self._cache[f"{widget_cls}-{variant}-{state}"])
        except KeyError:
            pass

        data = self.widget_data(widget_cls)
        vrt = self.validate_variant(data, variant)
        dvrt = self.default_variant(data)
        pal = self._palette
        d = copy.copy(self.data["global"])
        d.update(copy.deepcopy(data.get("variants", {}).get(dvrt, {})))
        d.update(copy.deepcopy(data.get("variants", {}).get(vrt, {})))

        if state == "all":
            for key, val in d.items():
                if isinstance(val, dict):
                    d[key] = {kk: pal.get(vv, vv) for kk, vv in val.items()}
                elif not isinstance(val, list):
                    d[key] = pal.get(val, val)
        else:
            # Override palette variables with the current state's values and remove
            # all states. That way, we can directly use "background-color" without
            # checking the widget's state.
            state_dict = {}
            for key, val in list(d.items()):
                if isinstance(val, dict):
                    if key == state:
                        state_dict = {
                            kk: pal.get(vv, vv) for kk, vv in val.items()
                        }
                    d.pop(key)
                elif not isinstance(val, list):
                    d[key] = pal.get(val, val)
            # apply current state overrides last to ensure they take precedence
            # over the base variant
            d.update(state_dict)

        # cache result
        d = StyleDict(d)
        self.last_key = f"{widget_cls}-{variant}-{state}"
        self._cache[self.last_key] = d
        return StyleDict(d)

    def get_styles(
        self,
        widget_cls: str,
        variant: str | None = None,
        states: list[str] | None = None,
    ) -> StyleDict:
        """Returns styles for a widget, variant and multiple states at once.

        This is more efficient than calling get_style() multiple times
        when you need styles for several states of the same widget/variant.

        Args:
            widget_cls: The widget class name (e.g., "QStyledItemDelegate").
            variant: The variant name (e.g., "default"). Defaults to None.
            states: List of states to retrieve (e.g., ["base", "hover",
                "checked"]). Defaults to all defined states.

        Returns:
            A dictionary mapping state names to their style dictionaries.
        """
        if states is None:
            states = self.widget_states(widget_cls)

        cache_key = f"all-{widget_cls}-{variant}-{'|'.join(states)}"
        try:
            return StyleDict(self._cache[cache_key])
        except KeyError:
            pass

        d = {
            state: self.get_style(widget_cls, variant, state)
            for state in states
        }
        self._cache[cache_key] = StyleDict(d)
        return StyleDict(d)

    def current_style(self):
        return self._cache[self.last_key]

    def get_widget_color(
        self,
        color_name: str,
        style: dict,
        w: QWidget,
        default: str | QColor,
    ) -> QColor:
        """Process color definitions referencing a widget attribute/property
        using the @ syntax.

        Args:
            color_name: The color name to retrieve.
            style: The style dictionary.
            w: The widget to get the color from.
            default: The default color to use if the attribute is not found.
        Returns:
            The color.
        """
        color = style[color_name]
        if isinstance(color, str) and color.startswith("@"):
            color = getattr(w, color[1:], default)
        return QColor(color)


# ----------------------------------------------------------------------------


class ButtonDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QPushButton": QPushButton}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButton,
                "QPushButton",
            ): [
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_PushButtonBevel,
                ),
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_PushButtonLabel,
                ),
            ],
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButtonBevel,
                "QPushButton",
            ): self.draw_push_button_bevel,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_PushButtonLabel,
                "QPushButton",
            ): self.draw_push_button_label,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ContentsType,
                QStyle.ContentsType.CT_PushButton,
                "QPushButton",
            ): self.calculate_push_button_size,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_PushButtonContents,
                "QPushButton",
            ): self.sub_element_rect,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_PushButtonFocusRect,
                "QPushButton",
            ): self.sub_element_rect,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ButtonMargin,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_DefaultFrameWidth,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ButtonDefaultIndicator,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_FocusFrameVMargin,
                "QPushButton",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_FocusFrameHMargin,
                "QPushButton",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ):
        if metric == QStyle.PixelMetric.PM_ButtonMargin:
            return 6
        elif metric == QStyle.PixelMetric.PM_DefaultFrameWidth:
            return 0
        elif metric == QStyle.PixelMetric.PM_ButtonDefaultIndicator:
            return 0
        elif metric == QStyle.PixelMetric.PM_FocusFrameVMargin:
            return 2
        elif metric == QStyle.PixelMetric.PM_FocusFrameHMargin:
            return 2

    def get_button_variant(self, widget: QWidget) -> str:
        """Extract button variant from widget properties."""
        if widget is None:
            return "surface"
        return getattr(widget, "_variant_str", "surface")

    def get_button_has_icon(self, widget: QWidget) -> bool:
        """Check if button has an icon."""
        if widget is None:
            return False

        # Method 1: Try has_icon property
        if hasattr(widget, "has_icon"):
            return widget.has_icon  # type: ignore

        # Method 2: Try Qt property
        has_icon_prop = widget.property("has_icon")
        if has_icon_prop is not None:
            return bool(has_icon_prop)

        # Method 3: Check the actual icon
        return bool(widget.icon() and not widget.icon().isNull())  # type: ignore

    def get_button_style(
        self, widget: QWidget, state: QStyle.StateFlag
    ) -> tuple[dict, str]:
        """Get the appropriate style dictionary for the widget's variant and
        state."""
        variant = self.get_button_variant(widget)

        wstate = "base"
        if not (state & QStyle.StateFlag.State_Enabled):
            wstate = "disabled"
        elif state & QStyle.StateFlag.State_Sunken:
            wstate = "pressed"
        elif state & QStyle.StateFlag.State_MouseOver and not (
            state & QStyle.StateFlag.State_On
        ):
            wstate = "hover"
        elif state & QStyle.StateFlag.State_On:
            wstate = "checked"

        style = self.model.get_style("QPushButton", variant, wstate)
        style.set_context(widget)

        return style, wstate

    def draw_push_button_bevel(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Draw the button background and frame with hover detection."""
        if not isinstance(option, QStyleOptionButton) or widget is None:
            return

        style, _ = self.get_button_style(widget, option.state)
        rect = option.rect

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw button background with hover awareness
        bg_color = style["background-color"]
        painter.setOpacity(style.get("opacity", 1.0))

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        border_radius = style.get("border-radius", 0)

        draw_icon_as_background = style.get("icon-as-background", False)
        clip_icon_to_radius = style.get("clip-icon-to-radius", False)

        if draw_icon_as_background:
            # draw the icon clipped by the same rounded rect
            painter.save()
            if clip_icon_to_radius:
                clip_path = QPainterPath()
                clip_path.addRoundedRect(rect, border_radius, border_radius)
                painter.setClipPath(clip_path)

            mode = QtGui.QIcon.Mode.Normal
            painter.drawRoundedRect(rect, border_radius, border_radius)
            option.icon.paint(
                painter,
                rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
            )

            if clip_icon_to_radius:
                painter.setClipping(False)

            pen = QPen(QColor(style.get("border-color")))
            pen.setWidth(int(style.get("border-width", 0)))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, border_radius, border_radius)
            painter.restore()
        else:
            painter.drawRoundedRect(rect, border_radius, border_radius)

        # Draw focus outline if needed
        if (
            option.state & QStyle.StateFlag.State_HasFocus
            and option.state  # type: ignore
            & QStyle.StateFlag.State_KeyboardFocusChange
        ):
            focus_color = style["focus-outline-color"]
            pen = QPen(
                QColor(focus_color), style.get("focus-outline-width", 0)
            )
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_rect = rect.adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(
                focus_rect, border_radius + 1, border_radius + 1
            )

        painter.restore()

    def draw_push_button_label(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Draw the button text and icon."""
        if not isinstance(option, QStyleOptionButton) or widget is None:
            return

        style, wstate = self.get_button_style(widget, option.state)  # type: ignore
        variant = self.get_button_variant(widget)

        # Set up text color
        text_color = self.model.get_widget_color(
            "color",
            style,
            widget,
            widget.palette().color(QPalette.ColorRole.ButtonText),
        )
        if not (option.state & QStyle.StateFlag.State_Enabled):  # type: ignore
            # Apply some opacity to disabled text
            text_color.setAlpha(int(255 * 0.5))

        painter.save()
        painter.setPen(text_color)

        # Set up font
        painter.setFont(widget.font())

        # Get content rectangle
        content_rect = self.style_inst.subElementRect(
            QStyle.SubElement.SE_PushButtonContents, option, widget
        )
        # _debug_rect(painter, "#ff5555", content_rect)

        # Optional per-widget alignment override (None → default centered layout)
        label_alignment = getattr(widget, "_label_alignment", None)

        # Draw icon if present
        if option.icon:  # type: ignore
            if option.text and not style.get("ignore-text", False):  # type: ignore
                icon_size = option.iconSize  # type: ignore
                icon_w = icon_size.width()
                icon_h = icon_size.height()
                _gap = 4

                # Draw icon with text color inheritance
                mode = QtGui.QIcon.Mode.Normal
                if not (
                    option.state & QStyle.StateFlag.State_Enabled  # type: ignore
                ):
                    mode = QtGui.QIcon.Mode.Disabled
                elif option.state & QStyle.StateFlag.State_Sunken:  # type: ignore
                    mode = QtGui.QIcon.Mode.Active

                if label_alignment is not None:
                    # Group layout: icon + text move together as a unit
                    h_align = (
                        label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask
                    )
                    text_w = painter.fontMetrics().horizontalAdvance(
                        option.text  # type: ignore
                    )
                    group_w = icon_w + _gap + text_w
                    if h_align == Qt.AlignmentFlag.AlignLeft:
                        group_x = content_rect.left()
                    elif h_align == Qt.AlignmentFlag.AlignRight:
                        group_x = content_rect.right() - group_w
                    else:
                        group_x = (
                            content_rect.left()
                            + (content_rect.width() - group_w) // 2
                        )
                    icon_rect = QRect(
                        group_x,
                        content_rect.center().y() - icon_h // 2,
                        icon_w,
                        icon_h,
                    )
                    text_rect = QRect(
                        icon_rect.right() + _gap,
                        content_rect.top(),
                        text_w,
                        content_rect.height(),
                    )
                    option.icon.paint(  # type: ignore
                        painter,
                        icon_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        mode,
                    )
                    painter.drawText(
                        text_rect,
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        option.text,  # type: ignore
                    )
                else:
                    # Icon + text: place icon on the left (default centered layout)
                    icon_rect = QRect(content_rect)
                    icon_rect.setSize(icon_size)
                    icon_rect.moveCenter(
                        QtCore.QPoint(
                            content_rect.left() + style["icon-padding"][0],
                            content_rect.center().y(),
                        )
                    )
                    option.icon.paint(  # type: ignore
                        painter,
                        icon_rect,
                        Qt.AlignmentFlag.AlignCenter,
                        mode,
                    )
                    # Adjust text rectangle
                    text_rect = QRect(content_rect)
                    text_rect.setLeft(icon_rect.right() + _gap)
                    # Draw text
                    painter.drawText(
                        text_rect,
                        Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter,
                        option.text,  # type: ignore
                    )
            elif variant not in ("thumbnail", "entity-card"):
                # Icon only
                mode = QtGui.QIcon.Mode.Normal
                if not (
                    option.state & QStyle.StateFlag.State_Enabled  # type: ignore
                ):
                    mode = QtGui.QIcon.Mode.Disabled
                elif option.state & QStyle.StateFlag.State_Sunken:  # type: ignore
                    mode = QtGui.QIcon.Mode.Active

                checkable = widget.isCheckable() if widget else False
                # checked = widget.isChecked() if widget else False

                icon_state = (
                    (
                        QtGui.QIcon.State.On
                        if wstate == "hover"
                        else QtGui.QIcon.State.Off
                    )
                    if not checkable
                    else (
                        QtGui.QIcon.State.On
                        if option.state & QStyle.StateFlag.State_On
                        else QtGui.QIcon.State.Off
                    )
                )

                _icon_align = (
                    (label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask)
                    | Qt.AlignmentFlag.AlignVCenter
                    if label_alignment is not None
                    else Qt.AlignmentFlag.AlignCenter
                )
                option.icon.paint(  # type: ignore
                    painter,
                    content_rect,
                    _icon_align,
                    mode,
                    icon_state,
                )
        else:
            # Text only
            if option.text and not style.get("ignore-text", False):  # type: ignore
                _text_align = (
                    (label_alignment & Qt.AlignmentFlag.AlignHorizontal_Mask)
                    | Qt.AlignmentFlag.AlignVCenter
                    if label_alignment is not None
                    else Qt.AlignmentFlag.AlignCenter
                )
                painter.drawText(
                    content_rect,
                    _text_align,
                    option.text,  # type: ignore
                )

        painter.restore()

    def calculate_push_button_size(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QtCore.QSize,
        widget: QWidget | None,
    ) -> QtCore.QSize:
        """Calculate minimum size for push buttons with text, icons,
        and proper padding."""

        if not isinstance(option, QStyleOptionButton):
            # Fallback to parent if we don't have proper option data
            if option is not None:
                return super(AYONStyle, self.style_inst).sizeFromContents(
                    contents_type,
                    option,
                    contents_size,
                    widget,
                )
            else:
                # Return reasonable default for button if no option
                return QtCore.QSize(100, 30)

        # Set up font for text measurement
        style, _ = self.get_button_style(widget, option.state)  # type: ignore
        font = widget.font() if widget else _style_font(style, widget)

        # Create font metrics for accurate text measurement
        font_metrics = QFontMetrics(font)

        # Determine if button has icon
        has_icon = (
            self.get_button_has_icon(widget)
            if widget
            else not option.icon.isNull()  # type: ignore
        )
        has_icon = not option.icon.isNull()

        # Determine appropriate padding
        if has_icon and not option.text:  # type: ignore
            # Icon-only button
            padding = style["icon-padding"]
        else:
            # Text button or icon+text button
            padding = style["text-padding"]

        # Calculate text dimensions
        text_width = 0
        text_height = 0
        if option.text and not style.get("ignore-text", False):  # type: ignore
            text_rect = font_metrics.boundingRect(option.text)  # type: ignore
            text_width = text_rect.width()
            text_height = text_rect.height()

        # Calculate icon dimensions
        icon_width = 0
        icon_height = 0
        if has_icon:
            icon_size = option.iconSize  # type: ignore
            icon_width = icon_size.width()
            icon_height = icon_size.height()

        # Calculate content dimensions
        content_width = 0
        content_height = 0

        if has_icon and option.text:  # type: ignore
            # Icon + text: icon on left, 4px spacing, then text
            content_width = icon_width + 4 + text_width
            content_height = max(icon_height, text_height)
        elif has_icon:
            # Icon only
            content_width = icon_width
            content_height = icon_height
        elif option.text:  # type: ignore
            # Text only
            content_width = text_width
            content_height = text_height

        # Add padding (vertical, horizontal)
        total_width = content_width + (
            2 * padding[1]
        )  # horizontal padding on both sides
        total_height = content_height + (
            2 * padding[0]
        )  # vertical padding on top and bottom

        # Ensure minimum button size (reasonable minimums)
        min_width = 16
        min_height = 16

        total_width = max(total_width, min_width)
        total_height = max(total_height, min_height)

        return QtCore.QSize(total_width, total_height)

    def sub_element_rect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget,
    ):
        if element == QStyle.SubElement.SE_PushButtonContents:
            style = self.model.get_style(
                "QPushButton", self.get_button_variant(widget)
            )
            style.set_context(widget)
            if option.icon:
                padding = (
                    style["icon-padding"]
                    if not widget.text()  # type: ignore
                    else style["text-padding"]
                )
            else:
                padding = style["text-padding"]

            return option.rect.adjusted(  # type: ignore
                padding[1], padding[0], -padding[1], -padding[0]
            )

        elif element == QStyle.SubElement.SE_PushButtonFocusRect:
            return option.rect.adjusted(-2, -2, 2, 2)  # type: ignore

        raise ValueError(f"Nothing returned ! -> {element}")


# ----------------------------------------------------------------------------


class FrameDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QFrame": QFrame}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QFrame",
            ): self.draw_frame,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_Widget,
                "QFrame",
            ): self.draw_frame,
        }

    def draw_frame(self, option: QStyleOption, painter: QPainter, w: QWidget):
        # get style
        variant = getattr(w, "_variant_str", "")
        # plp: I can't remember why I did this, but it overrides incorrectly
        # some UI, so I am disabling it until I remember why it was here !
        # is_view_frame = next(
        #     (
        #         True
        #         for child in w.children()
        #         if isinstance(child, QAbstractItemView)
        #     ),
        #     False,
        # )
        # if is_view_frame or isinstance(w, QListView):
        #     variant = "item-view"
        state = "base"
        row_state = w.property("row_state") if w is not None else None
        if row_state:
            state = (
                "selected"
                if row_state & QStyle.StateFlag.State_Selected
                else "hover"
                if row_state & QStyle.StateFlag.State_MouseOver
                else "base"
            )
        style = self.model.get_style("QFrame", variant, state)
        style.set_context(w)

        # widget override for comment types
        border_width = style.get("border-width", 0)
        if hasattr(w, "get_bg_color"):
            bgc: QColor = w.get_bg_color(style["background-color"])
            style = dict(style)
            if border_width == 0:
                style["border-color"] = bgc
            style["background-color"] = bgc
            # set background color of QTextEdit widgets
            try:
                viewport = w.viewport()
            except AttributeError:
                pass
            else:
                palette = viewport.palette()
                palette.setColor(QPalette.ColorRole.Base, bgc)
                viewport.setPalette(palette)

        # pen setup
        border_color = QColor(style["border-color"])
        pen = QPen(border_color)
        pen.setWidth(border_width)
        pen.setStyle(
            Qt.PenStyle.SolidLine if border_width else Qt.PenStyle.NoPen
        )
        # brush setup
        bg_color = QColor(style["background-color"])
        brush = QBrush(bg_color)
        radius = style.get("border-radius", 0)
        # draw
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Inset rect by half border width to keep stroke within bounds
        draw_rect = option.rect
        if border_width > 0:
            half_width = border_width / 2.0
            draw_rect = QRectF(option.rect).adjusted(
                half_width, half_width, -half_width, -half_width
            )

        if radius:
            painter.drawRoundedRect(draw_rect, radius, radius)
        else:
            painter.drawRect(draw_rect)


# ----------------------------------------------------------------------------


class CheckboxDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QCheckBox": QCheckBox}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_CheckBox,
                "QCheckBox",
            ): self.draw_indicator,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                "QCheckBox",
            ): self.draw_toggle,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_FrameFocusRect,
                "QCheckBox",
            ): do_nothing,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_IndicatorWidth,
                "QCheckBox",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_IndicatorHeight,
                "QCheckBox",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing,
                "QCheckBox",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ):
        variant = getattr(widget, "_variant_str", "default")
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
        )
        style.set_context(widget)
        metrics_h = widget.fontMetrics().height() if widget else 18
        metrics_w = metrics_h * 2 if widget else 32

        if metric == QStyle.PixelMetric.PM_IndicatorWidth:
            # is indicator-width == 0, use the 2x the font height.
            return style.get("indicator-width", metrics_w) or metrics_w
        elif metric == QStyle.PixelMetric.PM_IndicatorHeight:
            # is indicator-height == 0, use the font height.
            return style.get("indicator-height", metrics_h) or metrics_h
        elif metric == QStyle.PixelMetric.PM_CheckBoxLabelSpacing:
            return style.get("checkbox-label-spacing", 8)
        return 0

    def draw_indicator(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ):
        variant = getattr(widget, "_variant_str", "default")
        state = (
            "checked" if option.state & QStyle.StateFlag.State_On else "base"
        )
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
            state=state,
        )
        style.set_context(widget)

        if style.get("background-color"):
            painter.save()
            painter.setBrush(QColor(style["background-color"]))
            painter.setPen(Qt.PenStyle.NoPen)
            radius = style.get("border-radius", 0)
            painter.drawRoundedRect(option.rect, radius, radius)
            painter.restore()

        if style.get("indicator-position", "left") == "right":
            # Manually draw a centred [label  toggle] group so that padding is
            # equal on both sides, instead of relying on Qt's layout direction.
            s = self.style_inst
            ind_w = s.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorWidth, option, widget
            )
            ind_h = s.pixelMetric(
                QStyle.PixelMetric.PM_IndicatorHeight, option, widget
            )
            spacing = s.pixelMetric(
                QStyle.PixelMetric.PM_CheckBoxLabelSpacing, option, widget
            )

            text = getattr(option, "text", "")
            fm = option.fontMetrics
            text_w = fm.horizontalAdvance(text) if text else 0
            text_h = fm.height()

            total_w = text_w + (spacing + ind_w if text_w else ind_w)

            rect = option.rect
            cx = rect.center().x()
            cy = rect.center().y()
            x = cx - total_w // 2

            painter.save()
            if text:
                painter.setPen(
                    QColor(style["color"])
                    if style.get("color")
                    else option.palette.color(QPalette.ColorRole.WindowText)
                )
                text_rect = QRect(x, cy - text_h // 2, text_w, text_h)
                painter.drawText(
                    text_rect,
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    text,
                )

            toggle_opt = QStyleOption(option)
            toggle_opt.rect = QRect(
                x + text_w + (spacing if text_w else 0),
                cy - ind_h // 2,
                ind_w,
                ind_h,
            )
            self.draw_toggle(toggle_opt, painter, widget)
            painter.restore()
            return

        if style.get("color"):
            option.palette.setColor(
                QPalette.ColorRole.WindowText, QColor(style["color"])
            )

        super(AYONStyle, self.style_inst).drawControl(
            QStyle.ControlElement.CE_CheckBox, option, painter, widget
        )

    def draw_toggle(
        self,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget | None = None,
    ):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # get style data
        checked = bool(option.state & QStyle.StateFlag.State_On)
        variant = getattr(w, "_variant_str", "default")
        style = self.model.get_style(
            "QCheckBox",
            variant=variant,
            state="checked" if checked else "base",
        )
        style.set_context(w)

        # draw toggle background
        painter.setBrush(QColor(style["indicator-background-color"]))
        if style.get("indicator-border-width", 0):
            pen = QPen(QColor(style["indicator-border-color"]))
            pen.setWidth(style.get("indicator-border-width", 0))
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        frame_rect: QRectF = option.rect.toRectF().adjusted(1, 0, -1, 0)
        radius = frame_rect.height() / 2.0
        painter.drawRoundedRect(frame_rect, radius, radius)

        # draw toggle
        painter.setBrush(QColor(style["indicator-color"]))
        offset = frame_rect.height() * 0.125
        state_rect: QRectF = frame_rect.adjusted(
            offset, offset, -offset, -offset
        )
        state_rect.setWidth(state_rect.height())
        if checked:
            state_rect.moveRight(frame_rect.right() - offset)
        painter.drawEllipse(state_rect)

        painter.restore()


# ----------------------------------------------------------------------------


class ComboBoxItemDelegate(StyleMixin, QtWidgets.QStyledItemDelegate):
    def __init__(
        self,
        parent=None,
        padding: int = 4,
        icon_size: int = 16,
        style_model: StyleData | None = None,
    ) -> None:
        super().__init__(parent)
        self._padding = padding
        self._icon_size = icon_size
        self._icon_text_spacing = 8
        self._style_model = style_model
        self._icon_cache: dict[str, QIcon] = {}

    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index
    ) -> QtCore.QSize:
        """Calculate size hint including padding."""

        # Calculate text dimensions
        font_metrics = option.fontMetrics
        text_size = font_metrics.size(0, option.text)

        # Calculate content dimensions
        content_width = text_size.width()
        content_height = max(text_size.height(), self._icon_size)

        # Add icon space if present
        if option.icon:
            content_width += self._icon_size + self._icon_text_spacing

        # Add padding to get total size
        total_width = content_width + self._padding + self._padding
        total_height = content_height + self._padding + self._padding

        # Ensure minimum height
        total_height = max(total_height, 32)

        return QtCore.QSize(total_width, total_height)

    def _get_icon(
        self, fg: QColor, bg: QColor, icon_name: str, invert: bool = True
    ) -> QIcon:
        """Get icon from cache or create new one."""
        key = f"{icon_name}-{fg.name()}-{bg.name()}-{invert}"
        if key not in self._icon_cache:
            self._icon_cache[key] = get_icon(
                icon_name,
                bg if invert else fg,
            )
        return self._icon_cache[key]

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Initialize style option and apply any custom font from model."""
        super().initStyleOption(option, index)
        option.font = self.font()
        option.fontMetrics = self.fontMetrics()
        # print(f"PAINT: font = {option.font.family()}")

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Paint combo-box items directly, bypassing QStyle.

        This avoids QStyleSheetStyle intercepting drawPrimitive /
        drawControl calls when an app-level QSS is active.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Build a copy of the option with text/palette configured
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # --- debug ---------------------------------------------
        # m = f">> {opt.text!r} -> "
        # for flag in QStyle.StateFlag:
        #     if opt.state & flag:
        #         m += f"{flag.name}, "
        # print(m)
        # -------------------------------------------------------

        # --- resolve colours -----------------------------------
        fg_data = index.data(Qt.ItemDataRole.ForegroundRole)
        bg_data = index.data(Qt.ItemDataRole.BackgroundRole)

        cb = self.parent()

        # Menu background from the AYON style JSON
        if self._style_model:
            cb_style = self._style_model.get_style("QComboBox")
            cb_style.set_context(cb)
            menu_bg = QColor(cb_style.get("menu-background-color", "#1c2026"))
        else:
            menu_bg = opt.palette.color(
                QPalette.ColorGroup.Active,
                QPalette.ColorRole.Window,
            )

        highlight_color = opt.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Dark
        )

        state = opt.state
        is_selected = bool(state & QStyle.StateFlag.State_Selected)
        is_hovered = (
            bool(state & QStyle.StateFlag.State_MouseOver) and not is_selected
        )

        if fg_data and bg_data:
            fg = fg_data.color()
            bg = bg_data.color()

            if is_hovered:
                bg_color = highlight_color
                text_color = fg
            elif is_selected:
                bg_color = fg
                text_color = bg
                # Regenerate icon with the swapped text_color
                icon_name = (
                    index.data(cb.model().IconNameRole)
                    if hasattr(cb.model(), "IconNameRole")
                    else None
                )
                if icon_name:
                    opt.icon = self._get_icon(
                        text_color, bg_color, icon_name, False
                    )
            else:
                bg_color = menu_bg
                text_color = fg
        else:
            # Fallback for items without FG/BG data
            if is_hovered or is_selected:
                bg_color = highlight_color
                text_color = opt.palette.color(
                    QPalette.ColorRole.HighlightedText
                )
            else:
                bg_color = menu_bg
                text_color = opt.palette.color(QPalette.ColorRole.Text)

        # --- draw background -----------------------------------
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(opt.rect)

        # --- draw icon -----------------------------------------
        content_left = opt.rect.left() + self._padding
        if not opt.icon.isNull():
            icon_rect = QRect(
                content_left,
                opt.rect.center().y() - self._icon_size // 2,
                self._icon_size,
                self._icon_size,
            )
            mode = (
                QIcon.Mode.Normal
                if opt.state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            state = (
                QIcon.State.On
                if (is_hovered or is_selected)
                else QIcon.State.Off
            )
            opt.icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
                state,
            )
            content_left = icon_rect.right() + self._icon_text_spacing

        # --- draw text -----------------------------------------
        if opt.text:
            text_rect = QRect(opt.rect)
            text_rect.setLeft(content_left)
            text_rect.setRight(text_rect.right() - self._padding)
            painter.setPen(text_color)
            painter.setFont(opt.font)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                opt.text,
            )

        painter.restore()


class ComboBoxDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QComboBox": QComboBox}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ComboBoxLabel,
                "QComboBox",
            ): self.draw_label,
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_ComboBox,
                "QComboBox",
            ): self.draw_box,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelItemViewItem,
                "QFrame",
            ): self.draw_panel_item_view_item,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_FrameFocusRect,
                "QFrame",
            ): do_nothing,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ContentsType,
                QStyle.ContentsType.CT_ComboBox,
                "QComboBox",
            ): self.combobox_size,
        }

    def get_fg_bg_colors(
        self, opt: QtWidgets.QStyleOptionComplex, w: QComboBox
    ) -> tuple[QColor, QColor]:
        bg_color = opt.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Base
        )
        fg_color = opt.palette.color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.ButtonText
        )

        inverted = getattr(w, "_inverted", False)
        current_index = w.currentIndex()
        if current_index >= 0:
            item_color = w.itemData(
                current_index, QtCore.Qt.ItemDataRole.ForegroundRole
            )
            if item_color is not None:
                item_color = item_color.color()
                fg_color = bg_color if inverted else item_color
                bg_color = item_color if inverted else bg_color

        return fg_color, bg_color

    def draw_box(
        self,
        opt: QtWidgets.QStyleOptionComplex,
        p: QPainter,
        w: QComboBox | None = None,
    ):
        if not isinstance(w, QComboBox):
            return

        _style = self.model.get_style(
            "QComboBox", variant=getattr(w, "_variant_str", None)
        )
        _style.set_context(w)
        style_bg_color = _style.get("background-color", None)
        opt.palette.setBrush(
            QPalette.ColorRole.Base,
            QColor(style_bg_color)
            if style_bg_color
            else self.model.base_palette.base(),
        )
        _radius = _style.get("border-radius", 0)

        # print(f"SUB_CTL: {opt.activeSubControls}")
        if not w.isEditable():
            fg_color, bg_color = self.get_fg_bg_colors(opt, w)

            # Paint background with status color
            rect = opt.rect
            p.save()
            p.setBrush(QBrush(bg_color))
            p.setPen(QtCore.Qt.PenStyle.NoPen)
            p.drawRoundedRect(rect, _radius, _radius)
            p.restore()

            # Draw expand_more arrow if show_chevron is True
            show_chevron = getattr(w, "show_chevron", True)
            if show_chevron:
                arrow_rect = super(AYONStyle, self.style_inst).subControlRect(
                    QStyle.ComplexControl.CC_ComboBox,
                    opt,
                    QStyle.SubControl.SC_ComboBoxArrow,
                    w,
                )
                arrow_icon = get_icon("expand_more", fg_color)
                if arrow_icon and not arrow_rect.isEmpty():
                    arrow_size = min(arrow_rect.width(), arrow_rect.height())
                    pixmap = arrow_icon.pixmap(arrow_size, arrow_size)
                    px = arrow_rect.x() + (arrow_rect.width() - arrow_size) // 2
                    py = arrow_rect.y() + (arrow_rect.height() - arrow_size) // 2
                    popup_open = bool(opt.state & QStyle.StateFlag.State_On)
                    if popup_open:
                        cx = px + arrow_size / 2
                        cy = py + arrow_size / 2
                        p.save()
                        p.translate(cx, cy)
                        p.rotate(180)
                        p.translate(-cx, -cy)
                        p.drawPixmap(px, py, pixmap)
                        p.restore()
                    else:
                        p.drawPixmap(px, py, pixmap)

            # set pen for text drawing
            p.setPen(fg_color)
        else:
            # editable combobox - IMPLEMENT ME
            super(AYONStyle, self.style_inst).drawComplexControl(
                QStyle.ComplexControl.CC_ComboBox, opt, p, w
            )

    def draw_label(self, opt: QStyleOptionComboBox, p: QPainter, w: QWidget):
        if not isinstance(w, QComboBox):
            return

        _style = self.model.get_style(
            "QComboBox", variant=getattr(w, "_variant_str", None)
        )
        _style.set_context(w)
        icon_padding = _style.get("icon-padding", [4, 4])
        text_padding = _style.get("text-padding", [1, 1])

        fg_color, bg_color = self.get_fg_bg_colors(opt, w)

        base_cls = super(AYONStyle, self.style_inst)
        edit_rect = base_cls.subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            opt,
            QStyle.SubControl.SC_ComboBoxEditField,
            w,
        )
        p.save()
        p.setClipRect(edit_rect)
        if opt.currentIcon:
            mode = (
                QIcon.Mode.Normal
                if opt.state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            pixmap = opt.currentIcon.pixmap(opt.iconSize, mode)
            icon_rect = QRect(edit_rect)
            icon_rect.setWidth(opt.iconSize.width() + icon_padding[0])
            icon_rect.setHeight(opt.iconSize.height() + icon_padding[1])
            icon_rect = QStyle.alignedRect(
                opt.direction,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                icon_rect.size(),
                edit_rect,
            )
            if opt.editable:
                p.fillRect(
                    icon_rect, opt.palette.brush(QPalette.ColorRole.Base)
                )
            base_cls.drawItemPixmap(
                p, icon_rect, Qt.AlignmentFlag.AlignCenter, pixmap
            )
            if opt.direction == Qt.LayoutDirection.RightToLeft:
                edit_rect.translate(-icon_padding[0] - opt.iconSize.width(), 0)
            else:
                edit_rect.translate(opt.iconSize.width() + icon_padding[0], 0)

        if opt.currentText and not opt.editable:
            base_cls.drawItemText(
                p,
                edit_rect.adjusted(
                    text_padding[0],
                    -text_padding[1],
                    -text_padding[0],
                    text_padding[1],
                ),
                QStyle.visualAlignment(
                    opt.direction,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                ),
                opt.palette,
                bool(opt.state & QStyle.StateFlag.State_Enabled),
                opt.currentText,
            )

        p.restore()

    def draw_panel_item_view_item(
        self, option: QStyleOption, painter: QPainter, w: QWidget
    ):
        cb = w.model().parent()
        if cb and getattr(cb, "_inverted", False):
            idx = option.index
            if idx:
                fgc = (
                    w.model().data(idx, Qt.ItemDataRole.ForegroundRole).color()
                )
                option.backgroundBrush.setColor(fgc)
        else:
            stl = self.model.get_style("QComboBox")
            stl.set_context(w)
            option.backgroundBrush.setColor(
                QColor(stl["menu-background-color"])
            )
        super(AYONStyle, self.style_inst).drawPrimitive(  # type: ignore
            QStyle.PrimitiveElement.PE_PanelItemViewItem, option, painter, w
        )

    def combobox_size(
        self,
        contents_type: QStyle.ContentsType,
        option: QStyleOption | None,
        contents_size: QtCore.QSize,
        widget: QWidget | None,
    ) -> QtCore.QSize:
        if not option or not isinstance(option, QStyleOptionComboBox):
            return QSize()

        style = self.model.get_style("QComboBox")
        style.set_context(widget)

        text_width = cb_height = 0
        if isinstance(widget, QComboBox):
            for i in range(widget.count()):
                t_rect = option.fontMetrics.boundingRect(
                    widget.itemData(i, Qt.ItemDataRole.DisplayRole)
                )
                text_width = max(text_width, t_rect.width())
                cb_height = max(cb_height, t_rect.height())

        text_width += style["text-padding"][0] * 2
        cb_height += style["text-padding"][1] * 2

        icon_width = 0
        if option.currentIcon:
            icon_size = getattr(widget, "_icon_size", 0)
            if icon_size == 0:
                all_sizes = option.currentIcon.availableSizes()
                icon_size = max(all_sizes[0].width(), all_sizes[0].height())
            icon_width = icon_size + style["icon-padding"][0] * 2
            icon_height = icon_size + style["icon-padding"][1] * 2
            cb_height = max(cb_height, icon_height)
            if text_width:
                icon_width += style["text-padding"][0]

        final_size = QSize(
            text_width + icon_width,
            min(getattr(widget, "_height", cb_height), cb_height),
        )
        return final_size


# ----------------------------------------------------------------------------


class ScrollBarDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._style = self.model.get_style("QScrollBar")
        self._cache = {}

    @property
    def base_class(self):
        return {"QScrollBar": QtWidgets.QScrollBar}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarSlider,
                "QScrollBar",
            ): self.draw_scrollbar_slider,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarAddPage,
                "QScrollBar",
            ): self.draw_scrollbar_page,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ScrollBarSubPage,
                "QScrollBar",
            ): self.draw_scrollbar_page,
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.ComplexControl,
                QStyle.ComplexControl.CC_ScrollBar,
                "QScrollBar",
            ): self.get_size,
        }

    def register_metrics(self):
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ScrollBarExtent,
                "QScrollBar",
            ): self.get_metric,
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_ScrollBarSliderMin,
                "QScrollBar",
            ): self.get_metric,
        }

    def get_size(
        self,
        cc: QStyle.ComplexControl,
        opt: QStyleOptionComplex,
        sc: QStyle.SubControl,
        w: QWidget | None = None,
    ) -> QRect | None:
        if not w:
            raise ValueError(
                "Widget required to calculate scrollbar sub-control rects"
            )

        if not isinstance(self.style_inst, AYONStyle):
            raise ValueError("AYONStyle instance required")

        if not isinstance(opt, (QStyleOptionSlider, QStyleOptionComplex)):
            raise ValueError(f"Unexpected option type: {type(opt)}")

        sup = super(AYONStyle, self.style_inst)  # type: ignore
        try:
            als = self._cache["add_line_size"]
        except KeyError:
            als = self._cache["add_line_size"] = sup.subControlRect(
                cc, opt, QStyle.SubControl.SC_ScrollBarAddLine, w
            ).size()
        try:
            sls = self._cache["sub_line_size"]
        except KeyError:
            sls = self._cache["sub_line_size"] = sup.subControlRect(
                cc, opt, QStyle.SubControl.SC_ScrollBarSubLine, w
            ).size()

        orientation = w.orientation()

        if sc in (
            QStyle.SubControl.SC_ScrollBarSlider,
            QStyle.SubControl.SC_ScrollBarGroove,
        ):
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, -sls.height(), 0, als.height())
            else:
                rect.adjust(-sls.width(), 0, als.width(), 0)
            return rect

        elif sc == QStyle.SubControl.SC_ScrollBarAddPage:
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, 0, 0, als.height())
            else:
                rect.adjust(0, 0, als.width(), 0)
            return rect

        elif sc == QStyle.SubControl.SC_ScrollBarSubPage:
            rect = sup.subControlRect(cc, opt, sc, w)
            if orientation == Qt.Orientation.Vertical:
                rect.adjust(0, -sls.height(), 0, 0)
            else:
                rect.adjust(-sls.width(), 0, 0, 0)
            return rect

        raise ValueError("Unexpected sub-control")

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        self._style.set_context(widget)
        if metric == QStyle.PixelMetric.PM_ScrollBarExtent:
            # Width of a vertical scroll bar and the height of a horizontal
            # scroll bar.
            return int(self._style["width"])
        elif metric == QStyle.PixelMetric.PM_ScrollBarSliderMin:
            # The minimum height of a vertical scroll bar's slider and the
            # minimum width of a horizontal scroll bar's slider.
            return int(self._style["min-length"])
        return 0

    def draw_scrollbar_slider(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the scrollbar slider/thumb."""
        style = self.model.get_style("QScrollBar")
        style.set_context(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw slider background
        painter.setBrush(QBrush(QColor(style.get("slider-color"))))
        pen = QPen(QColor(style.get("background-color")))
        pen.setWidth(style.get("border-width"))
        painter.setPen(pen)
        radius = style.get("border-radius")
        painter.drawRoundedRect(option.rect, radius, radius)

        painter.restore()

    def draw_scrollbar_page(
        self,
        option: QStyleOptionComplex,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw scrollbar page buttons."""
        style = self.model.get_style("QScrollBar")
        style.set_context(widget)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw slider background
        painter.setBrush(QBrush(QColor(style.get("background-color"))))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(option.rect)

        painter.restore()


# ----------------------------------------------------------------------------


class LineEditDrawer:
    """AYONStyle drawer for QLineEdit.

    Registers a no-op for PE_PanelLineEdit when the widget is an AYLineEdit
    instance (which paints itself fully in its own paintEvent), and falls back
    to the base QCommonStyle implementation for all other QLineEdit widgets.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst

    @property
    def base_class(self):
        return {"QLineEdit": QLineEdit}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelLineEdit,
                "QLineEdit",
            ): self.draw_panel,
        }

    def draw_panel(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        # AYLineEdit paints its own background — skip Qt's default frame.
        if type(widget).__name__ == "AYLineEdit":
            return
        super(AYONStyle, self.style_inst).drawPrimitive(
            QStyle.PrimitiveElement.PE_PanelLineEdit, option, painter, widget
        )


# ----------------------------------------------------------------------------


class LabelDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QLabel": QLabel}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QLabel",
            ): do_nothing,
        }


# ----------------------------------------------------------------------------


class TooltipDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QToolTip": QToolTip}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ShapedFrame,
                "QToolTip",
            ): self.draw_control,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelTipLabel,
                "QToolTip",
            ): partial(
                self.draw_primitive, QStyle.PrimitiveElement.PE_PanelTipLabel
            ),
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_Frame,
                "QToolTip",
            ): partial(self.draw_primitive, QStyle.PrimitiveElement.PE_Frame),
        }

    def register_sizers(self):
        return {
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_ShapedFrameContents,
                "QToolTip",
            ): self.get_rect,
            enum_to_str(
                QStyle.SubElement,
                QStyle.SubElement.SE_FrameLayoutItem,
                "QToolTip",
            ): self.get_rect,
        }

    def draw_control(
        self,
        option: QStyleOptionFrame,
        painter: QPainter,
        widget: QWidget,
    ):
        option.frameShadow = QFrame.Shadow.Plain
        option.frameShape = QFrame.Shape.StyledPanel
        super(AYONStyle, self.style_inst).drawControl(
            QStyle.ControlElement.CE_ShapedFrame, option, painter, widget
        )

    def draw_primitive(
        self,
        prim: QStyle.PrimitiveElement,
        option: QStyleOption,
        painter: QPainter,
        w: QWidget,
    ) -> None:
        if prim == QStyle.PrimitiveElement.PE_Frame:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            style = self.model.get_style("QToolTip")
            style.set_context(w)
            pen = QPen(style["border-color"])
            pen.setWidth(style["border-width"])
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            radius = int(style["border-radius"])
            painter.drawRoundedRect(
                option.rect,
                radius,
                radius,
            )
            painter.restore()

        elif prim == QStyle.PrimitiveElement.PE_PanelTipLabel:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            style = self.model.get_style("QToolTip")
            style.set_context(w)
            brush = QBrush(style["background-color"])
            painter.setBrush(brush)
            painter.setPen(Qt.PenStyle.NoPen)
            radius = int(style["border-radius"])
            painter.drawRoundedRect(
                option.rect,
                radius,
                radius,
            )
            painter.restore()

    def get_rect(
        self,
        element: QStyle.SubElement,
        option: QStyleOption,
        widget: QWidget,
    ) -> QRect:
        tt_style = self.model.get_style("QToolTip")
        tt_style.set_context(widget)
        tt_pad_x, tt_pad_y = tt_style["padding"]

        if element == QStyle.SubElement.SE_ShapedFrameContents:
            if isinstance(option, QStyleOptionFrame):
                option.features = QStyleOptionFrame.FrameFeature.Rounded
                option.frameShape = QFrame.Shape.StyledPanel
                widget.setContentsMargins(
                    tt_pad_x, tt_pad_y, tt_pad_x, tt_pad_y
                )

        elif element == QStyle.SubElement.SE_FrameLayoutItem:
            if isinstance(option, QStyleOptionFrame):
                option.features = QStyleOptionFrame.FrameFeature.Rounded
                option.frameShape = QFrame.Shape.StyledPanel
                widget.setContentsMargins(
                    tt_pad_x, tt_pad_y, tt_pad_x, tt_pad_y
                )

        return super(AYONStyle, self.style_inst).subElementRect(
            element, option, widget
        )


# ----------------------------------------------------------------------------


class ItemViewItemDrawer:
    """Drawer for item view items using QStyledItemDelegate."""

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model

    @property
    def base_class(self):
        return {"QStyledItemDelegate": QStyledItemDelegate}

    def register_drawers(self):
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_ItemViewItem,
                "QStyledItemDelegate",
            ): self.draw_item_view_item,
        }

    def get_item_view_variant(self, widget: QWidget | None) -> str:
        """Extract item view variant from widget properties."""
        if widget is None:
            return "default"
        if hasattr(widget, "itemDelegate"):
            delegate = widget.itemDelegate()
            if hasattr(delegate, "_variant_str"):
                return delegate._variant_str
        return "default"

    def get_item_view_style(
        self,
        widget: QWidget | None,
        option: QStyleOptionViewItem,
    ) -> tuple[dict, str]:
        """Get the appropriate style dictionary for the widget's variant
        and state.

        Args:
            widget: The parent widget containing the item view.
            option: The style option containing state flags.

        Returns:
            A tuple of (style dictionary, state string).
        """
        variant = self.get_item_view_variant(widget)

        wstate = "base"
        is_checked = option.checkState == Qt.CheckState.Checked
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if is_checked:
            wstate = "checked"
        elif is_hovered:
            wstate = "hover"

        style = self.model.get_style("QStyledItemDelegate", variant, wstate)
        style.set_context(widget)

        return style, wstate

    def draw_item_view_item(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None,
    ) -> None:
        """Paint a filter item with checkbox indicator.

        Hover and checked states are handled independently:
        - Background color comes from hover state when hovered
        - Checkbox background and text color come from checked state
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # For QStyleOptionViewItem, we need to check different properties
        if not isinstance(option, QStyleOptionViewItem):
            painter.restore()
            return

        # Determine hover and checked states independently
        is_checked = option.checkState == Qt.CheckState.Checked
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        text = option.text

        # Get variant for style lookups
        variant = self.get_item_view_variant(widget)

        # Get all necessary styles in a single call
        styles = self.model.get_styles(
            "QStyledItemDelegate", variant, ["base", "hover", "checked"]
        )
        base_style = styles["base"]
        hover_style = styles["hover"]
        checked_style = styles["checked"]

        # Constants from base style data
        checkbox_size = base_style.get("checkbox-size", 16)
        checkbox_margin = base_style.get("checkbox-margin", 8)
        text_padding = base_style.get("text-padding", 12)
        border_radius = base_style.get("border-radius", 2)

        # Background: use hover style if hovered, regardless of checked state
        if is_hovered:
            bg_color = QColor(
                hover_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        else:
            bg_color = QColor(
                base_style.get("background-color", "transparent")
            )

        # Text color: use checked style if checked, else base
        if is_checked:
            text_color = QColor(
                checked_style.get("color", base_style.get("color", "#8b9198"))
            )
        else:
            text_color = QColor(base_style.get("color", "#8b9198"))

        # Checkbox background: use checked style if checked, else base
        if is_checked:
            checkbox_bg_color = QColor(
                checked_style.get(
                    "checkbox-background-color",
                    base_style.get("checkbox-background-color", "#424a57"),
                )
            )
        else:
            checkbox_bg_color = QColor(
                base_style.get("checkbox-background-color", "#424a57")
            )

        # Draw background if hovered (transparent check not needed for hover)
        if is_hovered:
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(option.rect)

        # Calculate checkbox rect - positioned on right side
        cb_rect = QRect(
            option.rect.right() - checkbox_size - checkbox_margin,
            option.rect.center().y() - checkbox_size // 2,
            checkbox_size,
            checkbox_size,
        )

        # Draw checkbox background
        painter.setBrush(QBrush(checkbox_bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(cb_rect, border_radius, border_radius)

        # Draw X mark if checked
        if is_checked:
            icon = get_icon("close", color="#000000")
            icon_rect = cb_rect.adjusted(2, 2, -2, -2)
            icon.paint(painter, icon_rect)

        # Draw text
        painter.setPen(QPen(text_color))
        text_rect = option.rect.adjusted(
            text_padding,
            0,
            -(checkbox_size + checkbox_margin * 2),
            0,
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

        painter.restore()


# ----------------------------------------------------------------------------


class TreeViewItemDelegate(StyleMixin, QtWidgets.QStyledItemDelegate):
    """Item delegate for AYTreeView that paints directly, bypassing QSS.

    Reads style data from the QTreeView style entry to draw item
    backgrounds (hover, selected) and text/icons.  The paint() method
    uses raw QPainter calls so that a parent-level QStyleSheet cannot
    intercept and override the colours.

    Args:
        parent: The parent widget (expected to be an AYTreeView instance).
        style_model: StyleData instance providing colour/dimension data.
        variant: The variant string used to look up the correct style.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        style_model: StyleData | None = None,
        variant: str = "default",
        item_height: int | None = None,
        item_padding: list[int] | None = None,
    ) -> None:
        super().__init__(parent)
        self._style_model = style_model
        self._variant_str = variant
        self._icon_cache: dict[str, QIcon] = {}
        self._item_custom_height = item_height
        self._item_custom_padding = item_padding

    def _tv_styles(self) -> dict[str, dict]:
        """Return *base*, *hover* and *selected* style dicts at once."""
        if self._style_model is None:
            return {"base": {}, "hover": {}, "selected": {}}
        return self._style_model.get_styles(
            "QTreeView",
            self._variant_str,
            ["base", "hover", "selected"],
        )

    def initStyleOption(
        self,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Initialize the style option with the default implementation, then
        override any properties needed for our custom painting.

        Args:
            option: The style option to initialize.
            index: The model index of the item.
        """
        super().initStyleOption(option, index)
        option.font = self.font()
        option.fontMetrics = self.fontMetrics()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        """Return a fixed row height from the style data.

        Args:
            option: The style option for the item.
            index: The model index of the item.

        Returns:
            The size hint for the item.
        """
        if self._item_custom_height is not None:
            h = self._item_custom_height
        elif self._style_model:
            style = self._style_model.get_style("QTreeView", self._variant_str)
            h = int(style.get("item-height", 28))
        else:
            h = 28
        return QtCore.QSize(option.rect.width(), h)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Paint a tree-view item directly, bypassing QStyle completely.

        Args:
            painter: The QPainter to use.
            option: The style option for the item.
            index: The model index of the item.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        state = opt.state
        is_selected = bool(state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(state & QStyle.StateFlag.State_MouseOver)

        styles = self._tv_styles()
        base_style = styles["base"]
        hover_style = styles["hover"]
        selected_style = styles["selected"]

        item_padding = (
            self._item_custom_padding
            or base_style.get("item-padding", [4, 8])
        )
        icon_text_spacing = int(base_style.get("icon-text-spacing", 6))

        # --- background ------------------------------------------------
        if is_selected:
            bg_color = QColor(
                selected_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        elif is_hovered:
            bg_color = QColor(
                hover_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        else:
            bg_color = QColor(
                base_style.get("background-color", "transparent")
            )

        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(opt.rect)

        # --- text colour -----------------------------------------------
        if is_selected:
            text_color = QColor(
                selected_style.get(
                    "color",
                    base_style.get("color", "#f4f5f5"),
                )
            )
        else:
            text_color = QColor(base_style.get("color", "#f4f5f5"))

        # disabled dimming
        if not (state & QStyle.StateFlag.State_Enabled):
            text_color.setAlpha(
                int(
                    text_color.alpha()
                    * base_style.get("disabled-opacity", 0.5)
                )
            )

        # --- icon + text layout ----------------------------------------
        content_rect = QRect(opt.rect).adjusted(
            item_padding[1],
            item_padding[0],
            -item_padding[1],
            -item_padding[0],
        )
        content_left = content_rect.left()

        if not opt.icon.isNull():
            icon_size = opt.decorationSize
            icon_rect = QRect(
                content_left,
                opt.rect.center().y() - icon_size.height() // 2,
                icon_size.width(),
                icon_size.height(),
            )
            mode = (
                QIcon.Mode.Normal
                if state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            opt.icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
            )
            content_left = icon_rect.right() + icon_text_spacing

        if opt.text:
            text_rect = QRect(opt.rect)
            text_rect.setLeft(content_left)
            text_rect.setRight(content_rect.right())
            painter.setPen(text_color)
            painter.setFont(opt.font)
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                opt.text,
            )

        painter.restore()


# ----------------------------------------------------------------------------


class TableItemDelegate(StyleMixin, QtWidgets.QStyledItemDelegate):
    """Item delegate for AYTableView that paints cells directly, bypassing QSS.

    Reads style data from the AYTableView style entry to draw cell
    backgrounds (hover, selected) and text/icons.

    Columns that carry a ``widget_factory`` on their :class:`TableColumn`
    definition get a persistent editor via :meth:`createEditor`.  Qt calls
    :meth:`setEditorData` both when the editor is first opened and
    automatically whenever the model emits ``dataChanged`` for that index,
    so server-push updates reach live widgets without extra wiring.
    User edits are written back via :meth:`setModelData`.

    Args:
        parent: The parent widget (expected to be an AYTableView instance).
        style_model: StyleData instance providing colour/dimension data.
        variant: The variant string used to look up the correct style.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        style_model: StyleData | None = None,
        variant: str = "default",
    ) -> None:
        super().__init__(parent)
        self._style_model = style_model
        self._variant_str = variant

    def _table_styles(self) -> dict[str, dict]:
        """Return base, hover and selected style dicts at once."""
        if self._style_model is None:
            raise ValueError("TableItemDelegate requires a style model")
        return self._style_model.get_styles(
            "AYTableView",
            self._variant_str,
            ["base", "hover", "selected"],
        )

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QtCore.QSize:
        """Return a fixed row height from the style data."""
        if self._style_model:
            style = self._style_model.get_style(
                "AYTableView", self._variant_str
            )
            h = int(style.get("item-height", 32))
        else:
            h = 32
        return QtCore.QSize(option.rect.width(), h)

    def createEditor(
        self,
        parent: QWidget,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> QWidget | None:
        """Return a widget for widget-factory columns; None otherwise.

        The returned widget is kept open permanently by the view via
        ``openPersistentEditor``.  Qt calls :meth:`setEditorData` once
        here and again automatically on every ``dataChanged`` emission
        for this index, so server-push updates reach the widget for free.

        Args:
            parent: Parent widget (viewport).
            option: Style option for the cell.
            index: Model index identifying the cell.

        Returns:
            A QWidget created by the column's ``widget_factory``, or
            ``None`` if the column has no factory.
        """
        from .components.table_model import PaginatedTableModel

        src_model = index.model()
        if hasattr(src_model, "sourceModel"):
            src_model = src_model.sourceModel()
        if not isinstance(src_model, PaginatedTableModel):
            return None
        col = index.column()
        cols = src_model.columns
        if col < 0 or col >= len(cols):
            return None
        factory = cols[col].widget_factory
        if factory is None:
            return None
        return factory(index, parent)  # type: ignore[return-value]

    def setEditorData(
        self,
        editor: QWidget,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Push current model data into *editor* when the model changes.

        Called by Qt when the persistent editor is first opened and
        automatically whenever the model emits ``dataChanged`` for this
        index — server-push updates propagate to live widgets for free.

        This default implementation is a no-op suited to action widgets
        (e.g. buttons) that do not reflect model data.  Override or
        replace this method for data-reflecting widgets: read
        ``index.data(Qt.DisplayRole)`` (or a custom role) and push the
        value into *editor*.

        Args:
            editor: The persistent editor widget.
            index: Model index whose data changed.
        """

    def setModelData(
        self,
        editor: QWidget,
        model: QtCore.QAbstractItemModel,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Write committed user input from *editor* back to *model*.

        Called by Qt when the user commits an edit (e.g. presses Enter
        or the editor loses focus).

        This default implementation is a no-op suited to action widgets
        that do not write back to the model.  For interactive widget
        columns, read the current value from *editor* and call
        ``model.setData(index, value, Qt.EditRole)`` to propagate the
        change upstream (e.g. to the server).

        Args:
            editor: The persistent editor widget.
            model: The data model.
            index: Model index to write to.
        """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Paint a table cell directly, bypassing QStyle."""
        # Skip painting for cells covered by a persistent editor widget.
        from .components.table_model import PaginatedTableModel

        src_model = index.model()
        if hasattr(src_model, "sourceModel"):
            src_model = src_model.sourceModel()
        if isinstance(src_model, PaginatedTableModel):
            col = index.column()
            cols = src_model.columns
            if 0 <= col < len(cols) and cols[col].widget_factory is not None:
                return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        state = opt.state
        is_selected = bool(state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        # State_MouseOver is only set for the cell directly under the cursor.
        # When hovering the branch-indicator column, other cells in the same
        # row don't receive it.  Fall back to a y-coordinate check so the
        # entire row highlights consistently.
        if not is_hovered and not is_selected:
            _view = self.parent()
            if type(_view).__name__ == "AYTableView" and hasattr(
                _view, "viewport"
            ):
                _cursor = _view.viewport().mapFromGlobal(QtGui.QCursor.pos())
                is_hovered = opt.rect.top() <= _cursor.y() < opt.rect.bottom()
        is_item = not bool(state & QStyle.StateFlag.State_Children)

        styles = self._table_styles()
        base_style = styles["base"]
        hover_style = styles["hover"]
        selected_style = styles["selected"]

        item_padding = base_style.get("item-padding", [4, 8])
        icon_text_spacing = int(base_style.get("icon-text-spacing", 6))

        # --- background ---
        if is_selected:
            bg_color = QColor(
                selected_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        elif is_hovered:
            bg_color = QColor(
                hover_style.get(
                    "background-color",
                    base_style.get("background-color", "transparent"),
                )
            )
        else:
            bg_color = QColor(
                base_style.get(
                    "background-color-item" if is_item else "background-color",
                    "transparent",
                )
            )

        painter.setBrush(QBrush(bg_color))

        pen_width = base_style.get("border-width", 0)
        if pen_width > 0:
            pen_color = QColor(base_style.get("border-color", "#000000"))
            pen = QPen(pen_color)
            pen.setWidth(pen_width)
            painter.setPen(pen)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
        column = index.column()
        if column == 1:
            painter.fillRect(opt.rect, bg_color)
            painter.drawPolyline(
                [
                    opt.rect.topLeft(),
                    opt.rect.topRight(),
                    opt.rect.bottomRight(),
                    opt.rect.bottomLeft(),
                ]
            )
        else:
            painter.drawRect(opt.rect)

        # --- text colour ---
        index_color = index.data(role=Qt.ItemDataRole.ForegroundRole)
        if is_selected:
            text_color = (
                index_color.color()
                if index_color
                else QColor(base_style.get("color", "#f4f5f5"))
            )
        else:
            text_color = (
                index_color.color()
                if index_color
                else QColor(base_style.get("color", "#f4f5f5"))
            )

        # disabled dimming
        if not (state & QStyle.StateFlag.State_Enabled):
            text_color.setAlpha(
                int(
                    text_color.alpha()
                    * base_style.get("disabled-opacity", 0.5)
                )
            )

        # --- icon + text layout ---
        content_rect = QRect(opt.rect).adjusted(
            item_padding[1],
            item_padding[0],
            -item_padding[1],
            -item_padding[0],
        )
        content_left = content_rect.left()

        if not opt.icon.isNull():
            icon_size = opt.decorationSize
            icon_rect = QRect(
                content_left,
                opt.rect.center().y() - icon_size.height() // 2,
                icon_size.width(),
                icon_size.height(),
            )
            mode = (
                QIcon.Mode.Normal
                if state & QStyle.StateFlag.State_Enabled
                else QIcon.Mode.Disabled
            )
            opt.icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
            )
            content_left = icon_rect.right() + icon_text_spacing

        if opt.text:
            text_rect = QRect(opt.rect)
            text_rect.setLeft(content_left)
            text_rect.setRight(content_rect.right())
            painter.setPen(text_color)
            painter.setFont(self.font())
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                opt.text,
            )

        painter.restore()


# ----------------------------------------------------------------------------


class TreeViewDrawer:
    """AYONStyle drawer for QTreeView.

    Handles branch expand/collapse indicators and the indentation metric
    using colours from the QTreeView style data in ayon_style.json.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._icon_cache = {}

    @property
    def base_class(self):
        return {"QTreeView": QTreeView}

    def register_drawers(self) -> dict:
        """Register drawing functions for QTreeView primitives."""
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_IndicatorBranch,
                "QTreeView",
            ): self.draw_branch_indicator,
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelScrollAreaCorner,
                "QTreeView",
            ): self.draw_scrollbar_corner,
        }

    def register_metrics(self) -> dict:
        """Register pixel metric functions for QTreeView."""
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_TreeViewIndentation,
                "QTreeView",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Return indent width from style data.

        Args:
            metric: The pixel metric being queried.
            opt: Optional style option.
            widget: The target widget.

        Returns:
            The indent size in pixels.
        """
        if metric == QStyle.PixelMetric.PM_TreeViewIndentation:
            variant = getattr(widget, "_variant_str", "default")
            style = self.model.get_style("QTreeView", variant)
            return int(style.get("indent", 20))
        return 0

    def _draw_cell_border(
        self,
        painter: QPainter,
        rect: "QRect",
        style: dict,
    ) -> None:
        """Draw top and bottom border lines for an AYTableView cell."""
        painter.setPen(
            QPen(
                QColor(style.get("border-color")), style.get("border-width", 1)
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLines(
            [
                rect.topLeft(),
                rect.topRight(),
                rect.bottomLeft(),
                rect.bottomRight(),
            ]
        )

    def _resolve_tree_view(self, widget: QWidget | None) -> QWidget | None:
        """Resolve widget to the actual QTreeView/AYTableView."""
        if widget is not None and not isinstance(widget, QTreeView):
            return widget.parent() or widget
        return widget

    def _paint_cell_background(
        self,
        painter: QPainter,
        rect: "QRect",
        style: dict,
        is_table: bool,
        is_base_state: bool = False,
    ) -> None:
        """Paint background fill and optional cell borders.

        Args:
            painter: The QPainter to draw on.
            rect: The rectangle to fill.
            style: The style data dictionary.
            is_table: Whether this is an AYTableView cell.
            is_base_state: If True and is_table, use 'background-color-item'.
        """
        painter.save()
        if is_table and is_base_state:
            bg_key = "background-color-item"
        else:
            bg_key = "background-color"
        painter.fillRect(rect, QColor(style.get(bg_key, "transparent")))
        if is_table:
            self._draw_cell_border(painter, rect, style)
        painter.restore()

    def _paint_icon(
        self,
        painter: QPainter,
        rect: "QRect",
        icon: QIcon,
        icon_size: int | None,
    ) -> None:
        """Paint a cached icon, optionally resizing and repositioning it."""
        draw_rect = QRect(rect)
        if icon_size is not None:
            center = rect.center()
            draw_rect.setSize(QSize(icon_size, icon_size))
            draw_rect.moveTo(
                rect.right() - icon_size, center.y() - icon_size // 2
            )
        icon.paint(painter, draw_rect)

    def _paint_fallback_arrow(
        self,
        painter: QPainter,
        rect: "QRect",
        color: QColor,
        is_open: bool,
    ) -> None:
        """Paint a geometric triangle arrow when no icon is configured."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        cx, cy = rect.center().x(), rect.center().y()
        size = max(4, min(rect.width(), rect.height()) // 3)

        path = QPainterPath()
        if is_open:
            path.moveTo(cx - size, cy - size // 2)
            path.lineTo(cx + size, cy - size // 2)
            path.lineTo(cx, cy + size // 2)
        else:
            path.moveTo(cx - size // 2, cy - size)
            path.lineTo(cx - size // 2, cy + size)
            path.lineTo(cx + size // 2, cy)
        path.closeSubpath()
        painter.drawPath(path)

    def draw_branch_indicator(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw expand / collapse arrows for tree branch items.

        Args:
            option: The primitive element style option.
            painter: The QPainter to draw on.
            widget: The QTreeView widget (may be the viewport).
        """
        has_children = bool(option.state & QStyle.StateFlag.State_Children)
        tv = self._resolve_tree_view(widget)
        is_table = type(tv).__name__ == "AYTableView"
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        variant = getattr(tv, "_variant_str", "default")

        state_name = (
            "selected" if is_selected else "hover" if is_hovered else "base"
        )

        widget_class = "AYTableView" if is_table else "QTreeView"
        t_style = self.model.get_style(
            widget_class, variant=variant, state=state_name
        )

        # Items without children only need background/border painting
        if not has_children:
            self._paint_cell_background(
                painter,
                option.rect,
                t_style,
                is_table,
                is_base_state=(state_name == "base"),
            )
            return

        is_open = bool(option.state & QStyle.StateFlag.State_Open)
        color = QColor(t_style.get("branch-indicator-color", "#8b9198"))
        icon_name = t_style.get(
            "expanded-icon-name" if is_open else "expand-icon-name"
        )

        # Paint background for items with children
        self._paint_cell_background(painter, option.rect, t_style, is_table)

        if icon_name:
            key = f"{icon_name}-{color.name()}"
            if key not in self._icon_cache:
                self._icon_cache[key] = get_icon(icon_name, color=color)
            icon_size = t_style.get("expand-icon-size")
            self._paint_icon(
                painter, option.rect, self._icon_cache[key], icon_size
            )
        else:
            self._paint_fallback_arrow(painter, option.rect, color, is_open)

    def draw_scrollbar_corner(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        style = self.model.get_style("QScrollArea", variant="default")
        style.set_context(widget)
        painter.save()
        # Draw corner background
        bg = style.get("background-color", "transparent")
        painter.fillRect(option.rect, QColor(bg))

        painter.restore()


# ----------------------------------------------------------------------------


class TableHeaderDrawer:
    """AYONStyle drawer for QHeaderView used by AYTableView.

    Handles painting of header sections and labels using colours
    from the AYTableView style data in ayon_style.json.
    """

    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._icon_cache: dict[str, QIcon] = {}

    @property
    def base_class(self):
        return {"QHeaderView": QtWidgets.QHeaderView}

    def register_drawers(self) -> dict:
        return {
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_Header,
                "QHeaderView",
            ): [
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_HeaderSection,
                ),
                partial(
                    self.style_inst.drawControl,
                    QStyle.ControlElement.CE_HeaderLabel,
                ),
            ],
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_HeaderSection,
                "QHeaderView",
            ): self.draw_header_section,
            enum_to_str(
                QStyle.ControlElement,
                QStyle.ControlElement.CE_HeaderLabel,
                "QHeaderView",
            ): self.draw_header_label,
        }

    def register_metrics(self) -> dict:
        """Register pixel metrics for QHeaderView."""
        return {
            enum_to_str(
                QStyle.PixelMetric,
                QStyle.PixelMetric.PM_HeaderMargin,
                "QHeaderView",
            ): self.get_metric,
        }

    def get_metric(
        self,
        metric: QStyle.PixelMetric,
        opt: QStyleOption | None = None,
        widget: QWidget | None = None,
    ) -> int:
        """Return header margin from style data."""
        if metric == QStyle.PixelMetric.PM_HeaderMargin:
            return 4
        return 0

    def _get_table_style(self, widget: QWidget | None) -> dict:
        """Resolve the AYTableView style for the header's parent table."""
        variant = "default"
        if widget is not None:
            # QHeaderView's parent is the QTreeView/AYTableView
            table = widget.parent()
            if table is not None:
                variant = getattr(table, "_variant_str", "default")
        return self.model.get_style("AYTableView", variant)

    def draw_header_section(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the header section background and bottom border."""
        style = self._get_table_style(widget)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Background
        bg_color = QColor(style.get("header-background-color", "#272d35"))
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(option.rect)

        # Bottom border
        border_color = QColor(style.get("header-border-color", "#41474d"))
        pen = QPen(border_color)
        pen.setWidth(1)
        painter.setPen(pen)
        bottom = option.rect.bottom()
        painter.drawLine(
            option.rect.left(),
            bottom,
            option.rect.right(),
            bottom,
        )

        painter.restore()

    def draw_header_label(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        """Draw the header label text and sort indicator."""
        style = self._get_table_style(widget)
        padding = style.get("header-padding", [4, 8])

        painter.save()

        # Text
        text_color = QColor(style.get("header-color", "#c1c7ce"))
        painter.setPen(text_color)

        font = painter.font()
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)

        text_rect = option.rect.adjusted(
            padding[1], padding[0], -padding[1], -padding[0]
        )

        text = ""
        if hasattr(option, "text"):
            text = option.text or ""

        # Check for sort indicator
        sort_indicator = getattr(option, "sortIndicator", None)
        indicator_space = 0
        if sort_indicator and sort_indicator != 0:
            indicator_space = 16

        if text:
            draw_rect = QRect(text_rect)
            if indicator_space:
                draw_rect.setRight(draw_rect.right() - indicator_space)
            painter.drawText(
                draw_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                text,
            )

        # Sort indicator arrow
        if sort_indicator and sort_indicator != 0:
            indicator_color = QColor(
                style.get(
                    "header-sort-indicator-color",
                    "#8fceff",
                )
            )
            # sortIndicator: 1 = Down, 2 = Up (in QStyleOptionHeader)
            icon_name = (
                "arrow_downward" if sort_indicator == 1 else "arrow_upward"
            )
            cache_key = f"{icon_name}-{indicator_color.name()}"
            if cache_key not in self._icon_cache:
                self._icon_cache[cache_key] = get_icon(
                    icon_name, color=indicator_color
                )
            icon = self._icon_cache[cache_key]
            icon_rect = QRect(
                text_rect.right() - 14,
                text_rect.center().y() - 7,
                14,
                14,
            )
            icon.paint(painter, icon_rect)

        painter.restore()


# ----------------------------------------------------------------------------


class ScrollAreaDrawer:
    def __init__(self, style_inst: AYONStyle) -> None:
        self.style_inst = style_inst
        self.model = style_inst.model
        self._style = self.model.get_style("QScrollArea", variant="default")

    @property
    def base_class(self):
        return {"QScrollArea": QtWidgets.QScrollArea}

    def register_drawers(self) -> dict:
        return {
            enum_to_str(
                QStyle.PrimitiveElement,
                QStyle.PrimitiveElement.PE_PanelScrollAreaCorner,
                "QScrollArea",
            ): self.draw_scrollbar_corner,
        }

    def draw_scrollbar_corner(
        self,
        option: QStyleOption,
        painter: QPainter,
        widget: QWidget | None = None,
    ) -> None:
        self._style.set_context(widget)
        painter.save()
        # Draw corner background
        bg = self._style.get("background-color", "transparent")
        painter.fillRect(option.rect, QColor(bg))

        painter.restore()


# ----------------------------------------------------------------------------
W_T = {}


class AYONStyle(QCommonStyle):
    """
    AYON QStyle implementation that replaces QSS styling with native Qt painting.
    Supports widget variants: surface, tonal, filled, tertiary, text, nav, etc.
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
        if self._in_widget_key or w is None or not isValid(w):
            return ""

        if w:
            # Handle item view widgets - check parent for delegate and exclude
            # ComboBoxItemDelegate
            if hasattr(w, "itemDelegate") and not isinstance(
                w, (QComboBox, QHeaderView)
            ):
                # Calling itemDelegate() is not a simple getter - it can
                # trigger Qt's internal operations that call back into the
                # custom style methods (subElementRect, drawPrimitive,
                # pixelMetric, etc.), each of which calls widget_key() again,
                # creating infinite recursion.
                self._in_widget_key = True
                try:
                    delegate = w.itemDelegate()
                    cbd = delegate and isinstance(
                        delegate, ComboBoxItemDelegate
                    )
                    tvd = delegate and isinstance(
                        delegate, (TreeViewItemDelegate, TableItemDelegate)
                    )
                    if not cbd and not tvd:
                        return "QStyledItemDelegate"
                finally:
                    self._in_widget_key = False
            for name, wtype in self.base_classes.items():
                if issubclass(type(w), wtype):
                    if w.objectName() == "qtooltip_label":
                        return "QToolTip"
                    if isinstance(w, QLabel):
                        p = w.parent()
                        # NOTE: Qt does not use QToolTip but a QLabel (a private
                        # QLabelTip class) !!
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
        if isinstance(widget, QWidget):
            variant = getattr(widget, "_variant_str", "default")
            if hasattr(widget, "_style_data"):
                if not widget._style_data:
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

    def polish(self, widget) -> None:
        """Polish widgets to enable hover tracking and custom palette."""
        if isinstance(widget, QWidget):
            super().polish(widget)
            self.style_widget(widget)

        # elif isinstance(widget, QPalette):
        #     print("YES: QPalette")

        elif isinstance(widget, QApplication):
            super().polish(widget)
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

        try:
            draw_ce_calls = self.drawers[key]
        except KeyError:
            # no custom drawer fallback
            super().drawControl(element, option, painter, w)
            return
        else:
            if isinstance(draw_ce_calls, list):
                for draw_ce in draw_ce_calls:
                    draw_ce(option, painter, w)
            elif callable(draw_ce_calls):
                draw_ce_calls(option, painter, w)
            return

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

        try:
            draw_cc = self.drawers[key]
        except KeyError:
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

        try:
            draw_prim = self.drawers[key]
        except KeyError:
            # Fall back to parent implementation
            # print(f"no match for {k}")
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

        try:
            sizer = self.sizers[key]
        except KeyError:
            # Fall back to parent implementation
            # Catch RuntimeError in case widget's C++ object was already deleted
            try:
                if widget is not None:
                    return super().subElementRect(element, option, widget)
                else:
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

        try:
            sizer = self.sizers[key]
        except KeyError:
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
        # print(f"PM: {metric}")
        key = enum_to_str(QStyle.PixelMetric, metric, self.widget_key(widget))

        if isinstance(widget, QLabel):
            log.debug("%s %s", type(widget), key)

        try:
            metric_func = self.metrics[key]
        except KeyError:
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
        """Calculate minimum size requirements for widgets based on their content."""
        # print(f"CT: {contents_type}")
        key = enum_to_str(
            QStyle.ContentsType, contents_type, self.widget_key(widget)
        )

        if isinstance(widget, QLabel):
            log.debug("%s", widget)

        try:
            sizer = self.sizers[key]
        except KeyError:
            if option:
                return super().sizeFromContents(
                    contents_type, option, contents_size, widget
                )
            else:
                # Create a default size if no option is provided
                return QtCore.QSize(100, 32)  # reasonable default
        else:
            return sizer(contents_type, option, contents_size, widget)


# TEST ========================================================================


if __name__ == "__main__":
    import time

    from . import _get_test_data_dir
    from .components.buttons import AYButton
    from .components.check_box import AYCheckBox
    from .components.combo_box import ALL_STATUSES, AYComboBox
    from .components.container import AYContainer
    from .components.label import AYLabel
    from .components.layouts import AYHBoxLayout, AYVBoxLayout
    from .components.text_box import AYTextBox
    from .components.user_image import AYUserImage
    from .tester import Style, test
    from .variants import QPushButtonVariants

    def time_it(func):
        i = time.time()
        r = func()
        e = (time.time() - i) * 1000
        return r, e

    m, e = time_it(StyleData)
    print(f"  init time: {e:.6f} ms")

    print("> button-surface-base: -------------------------------------------")
    d, e = time_it(lambda: m.get_style("QPushButton", "surface", "base"))
    # print(json.dumps(d, indent=4))
    print(f"  style time: {e:.6f} ms")

    print("> button-surface-hover -------------------------------------------")
    d, e = time_it(lambda: m.get_style("QPushButton", "surface", "hover"))
    # print(json.dumps(d, indent=4))
    print(f"  style time: {e:.6f} ms")

    d, e = time_it(lambda: m.get_style("QPushButton", "surface", "hover"))
    print(f"  cached style time: {e:.6f} ms")

    m.dump_cache_stats()

    print("> enum_to_str benchmarking --------------------------------------")
    ee = 0
    i = 0
    s = ""
    vals = _enum_values(QStyle.ControlElement)
    for i, v in enumerate(vals):
        s, e = time_it(lambda: enum_to_str(QStyle.ControlElement, v, ""))
        ee += e
    ee /= i
    print(f"  enum_to_str = {s!r}: {ee:.6f} ms ({i} lookups)")
    s = ""
    ee = 0
    runs = 1000
    for i in range(runs):
        for i, v in enumerate(vals):
            s, e = time_it(
                lambda: enum_to_str(
                    QStyle.ControlElement,
                    QStyle.ControlElement.CE_PushButtonBevel,
                    "",
                )
            )
            ee += e
    total_runs = runs * len(vals)
    ee /= total_runs
    print(f"  cached enum_to_str = {s!r}: {ee:.6f} ms ({total_runs} runs)")

    # all_enums(QStyle)

    print("> ui test --------------------------------------------------------")

    def _ui_test():
        # Create and show the test widget
        widget = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Default,
            margin=0,
            layout_spacing=10,
            layout_margin=10,
        )

        container_1 = AYContainer(
            widget,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            margin=0,
            layout_margin=10,
            layout_spacing=10,
        )
        widget.add_widget(container_1)

        variants = [v for v in QPushButtonVariants]

        # text buttons
        l1 = AYHBoxLayout(margin=0)
        for i, var in enumerate(variants):
            b = AYButton(
                f"{var.value} button",
                variant=var,
                tooltip=f"using variant {var.value}...",
            )
            l1.addWidget(b)
        container_1.add_layout(l1)

        # text + icon buttons
        l2 = AYHBoxLayout(margin=0)
        for i, var in enumerate(variants):
            b = AYButton(f"{var.value} button", variant=var, icon="add")
            l2.addWidget(b)
        container_1.add_layout(l2)

        container_2 = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            margin=0,
            layout_margin=10,
            layout_spacing=10,
        )
        # icon buttons
        for i, var in enumerate(variants):
            b = AYButton(
                variant=var, icon="add", name_id="ICON_ONLY" if i == 0 else ""
            )
            container_2.add_widget(b)
        container_2.addStretch()
        widget.add_widget(container_2)

        container_3 = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            margin=0,
            layout_margin=10,
            layout_spacing=10,
        )
        te = AYTextBox()
        te.set_markdown(
            "## Title\nText can be **bold** or *italic*, as expected !\n"
            "- [ ] Do this\n- [ ] Do that\n"
        )
        container_3.add_widget(te)
        vblyt = AYVBoxLayout(spacing=8)
        cbb = AYComboBox(items=ALL_STATUSES)
        vblyt.addWidget(cbb)
        cbbi = AYComboBox(items=ALL_STATUSES, inverted=True)
        vblyt.addWidget(cbbi)
        cb = AYCheckBox("CheckBox")
        cb.setToolTip(("A typical switch..."))
        vblyt.addWidget(cb)
        vblyt.addWidget(AYLabel("Normal label", tool_tip="text only"))
        vblyt.addWidget(
            AYLabel("Dimmed label", dim=True, tool_tip="text dimmed")
        )
        vblyt.addWidget(
            AYLabel(
                "Icon + text label", icon="favorite", tool_tip="Icon and text"
            )
        )
        vblyt.addWidget(
            AYLabel(
                icon="token",
                icon_color="#ff8800",
                icon_size=32,
                tool_tip="32 px orange icon only",
            )
        )
        vblyt.addWidget(
            AYLabel(
                "a badge",
                icon_color="#0088ff",
                variant=AYLabel.Variants.Badge,
                tool_tip="a blue badge",
            )
        )
        usr_ly = AYHBoxLayout(spacing=8)
        usr_ly.addWidget(
            AYUserImage(
                src=_get_test_data_dir() / "avatar1.jpg"
                if _get_test_data_dir()
                else ""
            )
        )
        vblyt.addStretch()
        container_3.add_layout(vblyt)
        container_3.addStretch()

        widget.add_widget(container_3)

        return widget

    test(_ui_test, style=Style.AyonStyleOverCSS)
