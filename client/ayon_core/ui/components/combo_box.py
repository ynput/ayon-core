"""Combo-box components for the AYON UI Qt library.

This module provides :class:`AYComboBox`, a styled :class:`QComboBox`
subclass that supports per-item coloured icons, a short-text display mode,
and an icon-only display mode via :class:`~ayon_core.ui.data_models.MenuSize`.
A dropdown arrow is drawn using the Material Symbol ``arrow_drop_down``
icon so the widget is visually recognizable as a dropdown when show_chevron
is true.

It also exposes :class:`AYComboBoxModel`, the default
:class:`QStandardItemModel` subclass that adds two extra item-data roles:

- ``ShortTextRole`` - an abbreviated label shown when the combo-box is in
  :attr:`~ayon_core.ui.data_models.MenuSize.Short` mode.
- ``IconNameRole`` - the Material Symbol icon name used to regenerate icons
  when the *inverted* colour mode is toggled.

A drop-in sample dataset :data:`ALL_STATUSES` is included for quick
prototyping and automated tests.

Typical usage::

    from ayon_core.ui.components.combo_box import AYComboBox, ALL_STATUSES

    combo = AYComboBox(parent=my_widget, items=ALL_STATUSES)
    combo.set_size("short")   # or MenuSize.Short
    combo.set_inverted(True)

Custom model usage (must expose ``ShortTextRole`` and ``IconNameRole``)::

    model = MyCustomModel(parent=combo)
    combo.setModel(model)

Note:
    When a custom model that does **not** expose ``ShortTextRole`` / \
``IconNameRole`` is set via :meth:`AYComboBox.setModel`, the widget
    falls back to displaying ``"< INCOMPATIBLE MODEL >"`` in short mode and
    raises :exc:`RuntimeError` when :meth:`AYComboBox.add_item` or
    :meth:`AYComboBox.update_items` is called.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from qtmaterialsymbols import get_icon  # type: ignore
from qtpy import QtCore, QtWidgets
from qtpy.QtCore import QRect, Qt
from qtpy.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPaintEvent,
    QPalette,
    QStandardItem,
    QStandardItemModel,
)
from qtpy.QtWidgets import QStyle

from ..data_models import MenuSize
from ..style_types import StyleData, get_ayon_style
from ..variants import QComboBoxVariants
from .style_mixin import StyleMixin

# Configure logging
logger = logging.getLogger(__name__)


ALL_STATUSES = [
    {
        "text": "Not ready",
        "short_text": "NRD",
        "icon": "fiber_new",
        "color": "#434a56",
    },
    {
        "text": "Ready to start",
        "short_text": "RDY",
        "icon": "timer",
        "color": "#bababa",
    },
    {
        "text": "In progress",
        "short_text": "PRG",
        "icon": "play_arrow",
        "color": "#3498db",
    },
    {
        "text": "Pending review",
        "short_text": "RVW",
        "icon": "visibility",
        "color": "#ff9b0a",
    },
    {
        "text": "Approved",
        "short_text": "APP",
        "icon": "task_alt",
        "color": "#00f0b4",
    },
    {
        "text": "On hold",
        "short_text": "HLD",
        "icon": "back_hand",
        "color": "#fa6e46",
    },
    {
        "text": "Omitted",
        "short_text": "OMT",
        "icon": "block",
        "color": "#cb1a1a",
    },
]
"""Sample status definitions for prototyping and tests.

Each entry is a :class:`dict` with the following keys:

- ``"text"``       - Full display label shown in
  :attr:`~ayon_core.ui.data_models.MenuSize.Full` mode.
- ``"short_text"`` - Abbreviated label (≤ 3 chars) shown in
  :attr:`~ayon_core.ui.data_models.MenuSize.Short` mode.
- ``"icon"``       - Material Symbol icon name passed to ``get_icon()``.
- ``"color"``      - Hex colour string used as the item foreground.
"""


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
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
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
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Initialize style option and apply any custom font from model."""
        super().initStyleOption(option, index)
        option.font = self.font()
        option.fontMetrics = self.fontMetrics()

    def paint(
        self,
        painter: QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex | QtCore.QPersistentModelIndex,
    ) -> None:
        """Paint combo-box items directly, bypassing QStyle.

        This avoids QStyleSheetStyle intercepting drawPrimitive /
        drawControl calls when an app-level QSS is active.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Build a copy of the option with text/palette configured
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

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
            icon_state = (
                QIcon.State.On
                if (is_hovered or is_selected)
                else QIcon.State.Off
            )
            opt.icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
                mode,
                icon_state,
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


def txt_color(bg_color: str | QColor) -> QColor:
    """Return a legible foreground colour for the given background colour.

    Uses the HSV *value* (brightness) component to decide between a light
    and a dark foreground:

    - Backgrounds with ``value < 0.9`` are considered dark → returns
      ``QColor("#eee")`` (near-white).
    - Backgrounds with ``value >= 0.9`` are considered light → returns
      ``QColor("#222")`` (near-black).

    Args:
        bg_color: Background colour as a CSS hex string (e.g. ``"#3498db"``)
            or a :class:`QColor` instance.

    Returns:
        A :class:`QColor` suitable for text rendered on *bg_color*.
    """
    value = QColor(bg_color).valueF()
    return QColor("#eee") if value < 0.9 else QColor("#222")


class AYComboBoxModel(QStandardItemModel):
    """Default item model for :class:`AYComboBox`.

    Extends :class:`QStandardItemModel` with two additional item-data roles
    required by :class:`AYComboBox` for short-text and icon-regeneration
    support.

    Attributes:
        ShortTextRole: Custom data role (``UserRole + 1``) that stores the
            abbreviated label displayed in
            :attr:`~ayon_core.ui.data_models.MenuSize.Short` mode.
        IconNameRole: Custom data role (``UserRole + 2``) that stores the
            Material Symbol icon name so icons can be regenerated when the
            *inverted* colour mode changes.
    """

    ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
    IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2


class AYComboBox(StyleMixin, QtWidgets.QComboBox):
    """AYON-styled combo-box with icon, short-text, and inverted-colour
    support.

    :class:`AYComboBox` wraps :class:`QComboBox` and adds:

    - **Three display modes** controlled by
      :class:`~ayon_core.ui.data_models.MenuSize`:

      - ``Full``  - shows the full item label (default).
      - ``Short`` - shows the abbreviated ``ShortTextRole`` label.
      - ``Icon``  - hides the text and shows only the item icon.

    - **Inverted colour mode** - swaps the icon foreground/background colours
      so the icon appears on a coloured pill rather than a neutral background.
    - **Placeholder text** support for an empty selection state.
    - **Custom model** support: any model that exposes ``ShortTextRole`` and
      ``IconNameRole`` attributes is accepted. Models without those attributes
      are flagged as incompatible; :meth:`add_item` and :meth:`update_items`
      will raise :exc:`RuntimeError` when such a model is active.

    The default model is :class:`AYComboBoxModel`.

    Args:
        parent: Optional parent widget.
        items: Initial list of item dictionaries.  Each dict may contain:

            - ``"text"``       *(required)* - Display label.
            - ``"color"``      - Hex foreground colour (default ``"#ffffff"``).
            - ``"icon"``       - Material Symbol icon name.
            - ``"short_text"`` - Abbreviated label for short mode
              (default ``"< UNDEFINED >"``).

        size: Initial display mode.  Accepts a
            :class:`~ayon_core.ui.data_models.MenuSize` value or its string
            equivalent (``"full"``, ``"short"``, ``"icon"``).
        height: Fixed maximum height in pixels (default ``30``).
        placeholder: Placeholder string shown when no item is selected.
        inverted: When ``True`` the icon foreground and background colours are
            swapped (default ``False``).
        icon_size: Icon size in pixels (default ``20``).
        show_chevron: If False, the dropdown chevron (arrow) will not be drawn
            in the custom style. Default is False.

        **kwargs: Additional keyword arguments forwarded to
            :class:`QComboBox`.

    Example:
        Basic usage with the built-in status list::

            combo = AYComboBox(
                parent=my_widget,
                items=ALL_STATUSES,
                size=MenuSize.Short,
                placeholder="Select status…",
            )
            combo.currentTextChanged.connect(on_status_changed)

        Switching modes at runtime::

            combo.set_size("icon")
            combo.set_inverted(True)
    """

    Variants = QComboBoxVariants

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        items: List[dict] | None = None,
        size: MenuSize | str = MenuSize.Full,
        height: int = 30,
        placeholder: Optional[str] = None,
        inverted: bool = False,
        icon_size: int = 20,
        variant: Variants = Variants.Default,
        show_chevron: bool = False,
        **kwargs,
    ) -> None:
        self._uses_incompatible_model = False
        super().__init__(parent, **kwargs)
        self._variant_str = variant.value

        self.setStyle(get_ayon_style())
        self.setMouseTracking(True)
        self.setMaximumHeight(height)

        # Initialize properties
        self._size: MenuSize = (
            size if isinstance(size, MenuSize) else MenuSize(size)
        )
        self._height: int = height
        self._inverted: bool = inverted
        self._icon_size: int = icon_size
        self._inverted_icons: dict[str, QIcon] = {}
        self.show_chevron: bool = show_chevron

        if placeholder:
            self.setPlaceholderText(placeholder)

        # setup model
        model = AYComboBoxModel(self)
        self.setModel(model)

        self.update_items(items)

    def _assert_compatible_model(self) -> None:
        """Raise :exc:`RuntimeError` when an incompatible model is active.

        Called by :meth:`add_item` and :meth:`update_items` to guard against
        direct item mutations when a custom model that does not expose
        ``ShortTextRole`` / ``IconNameRole`` has been set via
        :meth:`setModel`.
        """
        if self._uses_incompatible_model:
            raise RuntimeError(
                "Cannot modify items directly when a custom "
                "model is in use. Modify the model instead."
            )

    def setModel(self, model: QtCore.QAbstractItemModel) -> None:
        """Set the item model and detect compatibility with AYComboBox roles.

        If *model* is not an :class:`AYComboBoxModel` instance **and** it
        does not expose both ``ShortTextRole`` and ``IconNameRole``
        attributes, it is marked as *incompatible*.  In that state:

        - :meth:`add_item` and :meth:`update_items` will raise
          :exc:`RuntimeError`.
        - Short mode falls back to ``"< INCOMPATIBLE MODEL >"`` as the
          displayed text.

        Args:
            model: The new item model to attach to the combo-box.
        """
        mtype = type(model)
        self._uses_incompatible_model = mtype is not AYComboBoxModel and (
            not hasattr(model, "IconNameRole")
            or not hasattr(model, "ShortTextRole")
        )
        super().setModel(model)

    def _make_icon(
        self,
        fg_color: QColor,
        bg_color: QColor,
        icon_name: str | None,
        inverted: bool = False,
    ) -> QIcon | None:
        """Assign a Material Symbol icon to *data_item*.

        Reads the item's background and foreground colours and passes them
        to ``get_icon()``.  When *inverted* mode is active the icon's normal
        colour uses the **background** colour so the icon appears on a
        coloured pill; otherwise it uses the foreground colour.

        Does nothing when *icon_name* is ``None`` or an empty string.

        Args:
            fg_color: Icon color.
            bg_color: Background color.
            icon_name: A Material Symbol identifier (e.g. ``"play_arrow"``),
                or ``None`` / ``""`` to skip icon assignment.
            inverted: When ``True``, the icon's normal colour is taken from
                the item's **background** colour so it renders as a coloured
                icon on a neutral background.  Defaults to ``False``.
        """
        icon = None
        if icon_name:
            icon = get_icon(
                icon_name,
                color=bg_color if inverted else fg_color,
                # TODO: add fill support to get_icon and
                #       pass self._icon_fill here
            )
        return icon

    def _get_inverted_icon(self, default: QIcon) -> QIcon:
        """Return the inverted-colour icon for the currently selected item.

        Looks up the ``IconNameRole`` of the current item and returns a
        cached inverted icon.  If the icon has not been generated yet it is
        created via :meth:`_make_icon` with ``inverted=True`` and stored in
        :attr:`_inverted_icons` for future calls.

        Args:
            default: Fallback icon returned when the current item has no
                ``IconNameRole`` value.

        Returns:
            A :class:`QIcon` rendered with inverted colours, or *default*
            when no icon name is available.
        """
        idx = self.currentIndex()
        if idx < 0:
            return default

        icon_name = self.currentData(self.model().IconNameRole)
        if not icon_name:
            return default

        fg = self.currentData(QtCore.Qt.ItemDataRole.ForegroundRole).color()
        bg = self.currentData(QtCore.Qt.ItemDataRole.BackgroundRole).color()
        key = f"{icon_name}:{fg.name()}:{bg.name()}"

        if key not in self._inverted_icons:
            self._inverted_icons[key] = (
                self._make_icon(fg, bg, icon_name, inverted=True) or default
            )

        return self._inverted_icons[key]

    def add_item(self, item: dict[str, str]):
        """Append a single item to the combo-box model.

        Constructs a :class:`QStandardItem` from *item*, sets its foreground
        colour, background colour (from the current palette), icon, short
        text, and icon name, then appends it to the model.

        Raises:
            RuntimeError: If a custom incompatible model is currently set
                (see :meth:`setModel`).

        Args:
            item: A dict with the following keys:

                - ``"text"``       *(required)* - Display label.
                - ``"color"``      - Hex foreground colour
                  (default ``"#ffffff"``).
                - ``"icon"``       - Material Symbol icon name.
                - ``"short_text"`` - Abbreviated label stored in
                  ``ShortTextRole`` (default ``"< UNDEFINED >"``).
        """
        self._assert_compatible_model()

        bg_color = self.palette().color(
            QPalette.ColorGroup.Active, QPalette.ColorRole.Window
        )
        fg_color = QColor(item.get("color", "#ffffff"))

        text = item.get("text")
        if not text:
            raise ValueError(
                f"Item dict must contain a non-empty 'text' key; got: {item!r}"
            )

        data_item = QStandardItem(text)
        data_item.setData(
            QBrush(fg_color),
            QtCore.Qt.ItemDataRole.ForegroundRole,
        )
        data_item.setData(
            QBrush(bg_color), QtCore.Qt.ItemDataRole.BackgroundRole
        )
        icon = self._make_icon(fg_color, bg_color, item.get("icon"))
        if icon:
            data_item.setIcon(icon)
        data_item.setData(
            item.get("short_text", "< UNDEFINED >"),
            self.model().ShortTextRole,
        )  # type: ignore
        data_item.setData(item.get("icon"), self.model().IconNameRole)  # type: ignore
        self.model().appendRow(data_item)  # type: ignore

    def update_items(self, item_list: list[dict] | None = None):
        """Replace all items in the model with the provided list.

        Clears the model and calls :meth:`add_item` for every entry in
        *item_list*.  If *item_list* is ``None`` or empty the model is left
        unchanged.

        Raises:
            RuntimeError: If a custom incompatible model is currently set
                (see :meth:`setModel`).

        Args:
            item_list: List of item dicts as accepted by :meth:`add_item`.
                Pass ``None`` or an empty list to keep the current items.
        """
        if item_list:
            self._assert_compatible_model()
            self.model().clear()  # type: ignore
            for item in item_list:
                self.add_item(item)

    def set_inverted(self, state: bool):
        """Toggle the inverted colour mode and schedule a repaint.

        In *inverted* mode the icon's normal colour is drawn using the item's
        **background** colour instead of its foreground colour, producing a
        coloured icon on a neutral background.

        Inverted icons are generated lazily on first paint via
        :meth:`_get_inverted_icon` and cached in :attr:`_inverted_icons`.
        Calling this method triggers a repaint so the change is visible
        immediately.

        Args:
            state: ``True`` to enable inverted mode, ``False`` to disable.
        """
        self._inverted = state
        self.update()

    def set_size(self, size: MenuSize | str):
        """Change the display mode and repaint the widget.

        Args:
            size: New display mode.  Accepts a
                :class:`~ayon_core.ui.data_models.MenuSize` value or its
                lowercase string equivalent (``"full"``, ``"short"``,
                ``"icon"``).
        """
        self._size = (
            size if isinstance(size, MenuSize) else MenuSize(size.lower())
        )
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        """Return the preferred size for the combo-box.

        Delegates to the AYON style's
        :meth:`QStyle.sizeFromContents` so that the hint respects the
        custom theme's metrics rather than the system default.

        Returns:
            The preferred :class:`QSize` for this widget.
        """

        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        return get_ayon_style().sizeFromContents(
            QtWidgets.QStyle.ContentsType.CT_ComboBox,
            option,
            self.rect().size(),
            self,
        )

    def _resolve_current_text(self, idx: int) -> str | None:
        """Return the display text for the current item.

        Args:
            idx: The current combo-box index.

        Returns:
            The text to display, or ``None`` when the option should be left
            unchanged (e.g. no item is selected and no placeholder applies).
        """
        if idx < 0:
            return None

        if self._size == MenuSize.Full:
            return self.currentData(QtCore.Qt.ItemDataRole.DisplayRole)
        if self._size == MenuSize.Short:
            return (
                self.currentData(self.model().ShortTextRole)
                if hasattr(self.model(), "ShortTextRole")
                else "< INCOMPATIBLE MODEL >"
            )
        return ""  # MenuSize.Icon

    def paintEvent(self, arg__1: QPaintEvent) -> None:
        """Render the combo-box using the AYON custom style.

        Overrides the default :meth:`QComboBox.paintEvent` to:

        1. Draw the combo-box frame/control via the AYON style.
        2. Substitute placeholder text (rendered in ``placeholderText``
           palette colour) when no item is selected.
        3. Render the label according to the current
           :class:`~ayon_core.ui.data_models.MenuSize` mode:

           - ``Full``  → item's full text.
           - ``Short`` → item's ``ShortTextRole`` value, or
             ``"< INCOMPATIBLE MODEL >"`` if the role is unavailable.
           - ``Icon``  → empty string (icon only).

        Args:
            arg__1: The paint event delivered by Qt.
        """

        p = QPainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)

        p.setFont(self.font())
        option.fontMetrics = self.fontMetrics()

        if self._inverted:
            option.currentIcon = self._get_inverted_icon(option.currentIcon)

        _style = get_ayon_style()
        _style.drawComplexControl(
            QtWidgets.QStyle.ComplexControl.CC_ComboBox, option, p, self
        )

        idx = self.currentIndex()

        if idx < 0 and self.placeholderText():
            option.palette.setBrush(  # type: ignore
                QPalette.ColorRole.ButtonText,
                option.palette.placeholderText(),  # type: ignore
            )
            option.currentText = self.placeholderText()  # type: ignore

        text = self._resolve_current_text(idx)
        if text is not None:
            option.currentText = text  # type: ignore

        _style.drawControl(
            QtWidgets.QStyle.ControlElement.CE_ComboBoxLabel,
            option,
            p,
            self,
        )


# TEST  =======================================================================


if __name__ == "__main__":
    # Run an interactive test window that exercises AYComboBox scenarios:
    # - default AYComboBoxModel with ALL_STATUSES
    # - custom compatible model
    # - inverted-colour toggle and size switcher
    import os

    from ..tester import Style, test
    from .check_box import AYCheckBox
    from .container import AYContainer
    from .label import AYLabel

    class CustomModel(QStandardItemModel):
        ShortTextRole = QtCore.Qt.ItemDataRole.UserRole + 1
        IconNameRole = QtCore.Qt.ItemDataRole.UserRole + 2

        def __init__(self, parent=None):
            super().__init__(parent)

        def add_item(
            self,
            text: str,
            color: QColor,
            icon_name: str | None = None,
            short: str = "",
        ):
            bg_color = (
                self.parent()
                .palette()
                .color(QPalette.ColorGroup.Active, QPalette.ColorRole.Window)
            )
            item = QStandardItem(text)
            item.setForeground(QBrush(color))
            item.setBackground(QBrush(bg_color))
            if icon_name:
                item.setIcon(
                    get_icon(
                        icon_name,
                        color_normal=bg_color,
                        color_selected=color,
                        # TODO: add fill support to get_icon and
                        #       pass self._icon_fill here
                    )
                )
                item.setData(icon_name, self.IconNameRole)
            if short:
                item.setData(short, self.ShortTextRole)
            self.appendRow(item)

    def build():
        w = AYContainer(
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=6,
            layout_margin=20,
        )
        w.setMinimumWidth(250)

        w.add_widget(AYLabel("AYComboBox Tests", rel_text_size=6, bold=True))
        w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))

        w.add_widget(AYLabel("Default Model", dim=True, bold=True))
        cb = AYComboBox(items=ALL_STATUSES)
        w.add_widget(
            cb, stretch=0, alignment=QtCore.Qt.AlignmentFlag.AlignLeft
        )
        inv = AYCheckBox("inverted", parent=w)
        w.add_widget(inv)
        size = AYComboBox(w)
        size.addItems([s.name for s in MenuSize])
        w.add_widget(size)

        w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))

        # custom model test
        w.add_widget(AYLabel("Custom Model: invert ON", dim=True, bold=True))
        custom = AYComboBox(w, inverted=True)
        model = CustomModel(parent=custom)
        model.add_item(
            "Custom Model Item 1",
            QColor("#ee6666"),
            icon_name="map",
            short="CUST 1",
        )
        model.add_item(
            "Custom Model Item 2",
            QColor("#66ee66"),
            icon_name="map",
            short="CUST 2",
        )
        model.add_item(
            "Custom Model Item 3",
            QColor("#6666ee"),
            icon_name="map",
            # short="CUST 3",   # check for empty case !
        )
        custom.setModel(model)
        w.add_widget(custom)
        cust_inv = AYCheckBox("inverted", parent=w)
        cust_inv.setChecked(True)
        w.add_widget(cust_inv)
        cust_size = AYComboBox(w)
        cust_size.addItems([s.name for s in MenuSize])
        w.add_widget(cust_size)

        w._layout.addSpacerItem(QtWidgets.QSpacerItem(16, 16))
        w.add_widget(AYLabel("Backward compatibility"))
        back = AYComboBox(w, items=ALL_STATUSES, inverted=True)
        w.add_widget(back)

        # configure
        inv.clicked.connect(lambda x: cb.set_inverted(x))
        size.currentTextChanged.connect(lambda x: cb.set_size(x))
        cust_inv.clicked.connect(lambda x: custom.set_inverted(x))
        cust_size.currentTextChanged.connect(lambda x: custom.set_size(x))

        return w

    os.environ["QT_SCALE_FACTOR"] = "1"

    test(build, style=Style.AYONStyleOverCSS)
