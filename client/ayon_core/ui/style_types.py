"""Shared style types and singleton accessor for ayon_ui_qt.

This module is intentionally a **leaf** — it imports only from stdlib, Qt,
and the drawers utility layer.  No import from ``.components`` or from the
top-level ``.style`` module is performed at module-load time, which breaks
the circular dependency that would otherwise arise between ``style.py`` and
the component modules.

Exports:
    StyleDict: Context-aware dict that resolves ``@attr`` references.
    StyleData: Loads and caches data from ``ayon_style.json``.
    get_ayon_style: Returns the process-wide ``AYONStyle`` singleton.
    get_ayon_style_data: Convenience wrapper around
        ``get_ayon_style().model.get_style()``.
    hsl_to_html_color: Converts HSL CSS strings to Qt colour hex codes.
"""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qtpy.QtGui import QColor, QFont, QFontDatabase, QPalette
from qtpy.QtWidgets import QWidget

from .drawers._utils import style_font

if TYPE_CHECKING:
    from .style import AYONStyle

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def hsl_to_html_color(hsl: str) -> str:
    """Convert a CSS ``hsl(h, s%, l%)`` string to an HTML hex colour.

    Args:
        hsl: A CSS colour string such as ``"hsl(210, 50%, 40%)"``.

    Returns:
        The corresponding HTML hex colour string (e.g. ``"#336699"``).
    """
    vals = hsl[4:-1].split(", ")
    hue = int(vals[0]) / 360.0
    sat = int(vals[1][:-1]) / 100.0
    lum = int(vals[2][:-1]) / 100.0
    return QColor.fromHslF(hue, sat, lum).name()


# ---------------------------------------------------------------------------
# StyleDict
# ---------------------------------------------------------------------------


class StyleDict(dict):
    """A dict where string values starting with ``'@'`` are resolved
    via :func:`getattr` on a bound context object.

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
        """Bind a new context object for ``@attr`` resolution.

        Args:
            _context: The new context; pass ``None`` to unbind.
        """
        object.__setattr__(self, "_context", _context)
        for v in self.values():
            if isinstance(v, StyleDict):
                v.set_context(_context)

    def __getitem__(self, key: str) -> Any:
        value = super().__getitem__(key)
        return self._resolve(value)

    def get(self, key: str, default: Any = None, raw: bool = False) -> Any:
        """Return the value for *key*, resolving ``@attr`` references.

        Args:
            key: Dict key to look up.
            default: Value to return when *key* is absent.
            raw: If ``True``, skip ``@attr`` resolution.

        Returns:
            The resolved (or raw) value, or *default*.
        """
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


# ---------------------------------------------------------------------------
# StyleData
# ---------------------------------------------------------------------------


class StyleData:
    """Loads ``ayon_style.json`` and provides cached style lookups.

    Attributes:
        data: The raw parsed JSON data.
        base_palette: A ``QPalette`` built from the ``palette`` section.
    """

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

    @property
    def base_font(self) -> QFont:
        """Return the base application font, loading it lazily.

        Returns:
            A copy of the configured base ``QFont``.
        """
        # delayed to make sure QApplication is initialized
        if self._base_font is None:
            self._base_font = style_font(
                self.data.get("global", {}), QWidget()
            )
            _load_fonts()
        return QFont(self._base_font)

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

        Args:
            widget: The widget to build the palette for.
            widget_key: The style key identifying the widget class.

        Returns:
            A ``QPalette`` configured for the widget.
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

    def dump_cache_stats(self) -> None:
        """Print cache statistics to stdout (debug aid)."""
        print(f"[StyleData] cached {len(self._cache)} styles.")
        print(f"[StyleData]   >> {list(self._cache.keys())}")

    def widget_variants(self, widget_cls: str) -> list[str]:
        """Return all variant names registered for *widget_cls*.

        Args:
            widget_cls: The widget class key (e.g. ``"QPushButton"``).

        Returns:
            A list of variant name strings.
        """
        return list(
            self.data["widgets"].get(widget_cls, {}).get("variants", {}).keys()
        )

    def widget_states(self, widget_cls: str) -> list[str]:
        """Return the list of states for *widget_cls*, always including
        ``"base"`` as the first entry.

        Args:
            widget_cls: The widget class key.

        Returns:
            Ordered list of state name strings.
        """
        states = list(
            self.data["widgets"].get(widget_cls, {}).get("states", [])
        )
        return states if "base" in states else ["base"] + states

    def widget_data(self, widget_cls: str) -> dict:
        """Return the raw widget data block for *widget_cls*.

        Args:
            widget_cls: The widget class key.

        Returns:
            The raw data dict (empty dict if not found).
        """
        return self.data["widgets"].get(widget_cls, {})

    def widget_list(self) -> list[str]:
        """Return all registered widget class keys.

        Returns:
            List of widget class key strings.
        """
        return list(self.data["widgets"].keys())

    def default_variant(self, widget_data: dict) -> str:
        """Return the default variant name for *widget_data*.

        Args:
            widget_data: The raw widget data block.

        Returns:
            The default variant name string.
        """
        variants = widget_data.get("variants", {})
        return widget_data.get(
            "default-variant", next(iter(variants.keys()), "default")
        )

    def validate_variant(self, widget_data: dict, variant: str) -> str:
        """Return *variant* if valid, otherwise return the default variant.

        Args:
            widget_data: The raw widget data block.
            variant: The requested variant name.

        Returns:
            A valid variant name string.
        """
        if variant not in widget_data.get("variants", {}):
            return self.default_variant(widget_data)
        return variant

    def palette(self) -> dict:
        """Return the resolved colour palette mapping.

        Returns:
            Dict mapping palette key strings to HTML hex colours.
        """
        return self._palette

    def get_style(
        self,
        widget_cls: str,
        variant: str | None = None,
        state: str = "base",
    ) -> StyleDict:
        """Return a style dict for a widget, variant and state.

        Args:
            widget_cls: The widget class key.
            variant: Optional variant name.
            state: State to retrieve; ``"all"`` returns every state merged.

        Returns:
            A :class:`StyleDict` for the requested combination.
        """
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
            # Override palette variables with the current state's values and
            # remove all states. That way, we can directly use
            # "background-color" without checking the widget's state.
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
        """Return styles for a widget, variant and multiple states at once.

        This is more efficient than calling :meth:`get_style` multiple times
        when you need styles for several states of the same widget/variant.

        Args:
            widget_cls: The widget class name, e.g. ``"QStyledItemDelegate"``.
            variant: The variant name (e.g., ``"default"``). Defaults to None.
            states: List of states to retrieve (e.g., ``["base", "hover",
                "checked"]``). Defaults to all defined states.

        Returns:
            A :class:`StyleDict` mapping state names to their style dicts.
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

    def current_style(self) -> StyleDict:
        """Return the most recently computed style entry from cache.

        Returns:
            The last :class:`StyleDict` placed into the cache.
        """
        return self._cache[self.last_key]

    def get_widget_color(
        self,
        color_name: str,
        style: dict,
        w: QWidget,
        default: str | QColor,
    ) -> QColor:
        """Process color definitions referencing a widget attribute/property
        using the ``@`` syntax.

        Args:
            color_name: The color name to retrieve.
            style: The style dictionary.
            w: The widget to get the color from.
            default: The default color to use if the attribute is not found.

        Returns:
            The resolved :class:`QColor`.
        """
        color = style[color_name]
        if isinstance(color, str) and color.startswith("@"):
            color = getattr(w, color[1:], default)
        return QColor(color)


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

class _LocalContext:
    ayon_style_instance: AYONStyle | None = None
    font_ids: list[int] | None = None


def _load_fonts() -> None:
    """Load and register fonts into Qt application."""
    from ayon_core.style import _load_font

    # Load fonts from old ayon stylesheets too (monospaced font).
    _load_font()

    # Check if font ids are still loaded
    if _LocalContext.font_ids is not None:
        for font_id in tuple(_LocalContext.font_ids):
            font_families = QFontDatabase.applicationFontFamilies(
                font_id
            )
            # Reset font if font id is not available
            if not font_families:
                _LocalContext.font_ids = None
                break

    if _LocalContext.font_ids is None:
        _LocalContext.font_ids = []
        path = Path(__file__).parent / "resources" / "NunitoSans.ttf"

        font_path = str(path)
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id == -1:
            log.error(f"Failed to load base font from {font_path}")
        else:
            _LocalContext.font_ids.append(font_id)
            family = QFontDatabase.applicationFontFamilies(font_id)
            log.debug(f"Loaded base font file {font_path} ('{family}')")


def get_ayon_style() -> AYONStyle:
    """Return the process-wide :class:`~ayon_ui_qt.style.AYONStyle` singleton.

    The ``AYONStyle`` class is imported lazily on the first call to avoid
    a circular import at module load time.

    Returns:
        The singleton ``AYONStyle`` instance.
    """
    if _LocalContext.ayon_style_instance is not None:
        return _LocalContext.ayon_style_instance

    from .style import AYONStyle

    instance = AYONStyle()
    _LocalContext.ayon_style_instance = instance
    return instance


def get_ayon_style_data(
    widget_cls: str, variant: str | None = None
) -> StyleDict:
    """Return style data for *widget_cls* / *variant* (all states merged).

    Args:
        widget_cls: The widget class key (e.g. ``"QPushButton"``).
        variant: Optional variant name.

    Returns:
        A :class:`StyleDict` with all states merged.
    """
    return get_ayon_style().model.get_style(
        widget_cls, variant=variant, state="all"
    )
