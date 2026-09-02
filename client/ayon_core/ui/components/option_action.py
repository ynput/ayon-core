"""Menu action with an option box button (Maya-style option box pattern).

Provides AYON-styled menus and a widget action composed of a standard
action area (icon + label) and a small option target on the far right.
Clicking the main area fires the normal ``triggered`` signal; clicking
the option target emits ``AYOptionalAction.option_clicked`` instead.

Typical usage::

    menu = AYOptionalMenu("My Menu", parent)
    action = AYOptionalAction(
        label="Run Process",
        icon_name="play_arrow",
        use_option=True,
        parent=menu,
    )
    action.triggered.connect(lambda: run_process())
    action.option_clicked.connect(lambda: open_options_dialog())
    menu.addAction(action)
"""

from __future__ import annotations

from qtmaterialsymbols import get_icon
from qtpy import QtCore, QtGui, QtWidgets

from ..style_types import StyleDict, get_ayon_style
from .buttons import AYButton


class AYOptionBox(AYButton):
    """Option box widget used as the right-hand button in an action row.

    Emits :attr:`clicked` when the user presses this button.  It is a
    standard :class:`AYButton` styled with the ``Optional_Action``
    variant.
    """

    def __init__(
        self,
        icon_name: str = "check_box_outline_blank",
        icon_size: int = 16,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            variant=AYButton.Variants.Optional_Action,
            icon=icon_name,
            icon_size=icon_size,
            fixed_width=False,
        )

    def is_hovered(self, global_pos: QtCore.QPoint) -> bool:
        """Return whether a global cursor position is inside the button."""
        pos = self.mapFromGlobal(global_pos)
        if isinstance(pos, QtCore.QPointF):
            pos = pos.toPoint()
        return self.rect().contains(pos)


class AYOptionalActionWidget(QtWidgets.QWidget):
    """Self-painted menu row with main and option action hit regions.

    Args:
        label: Display text for the action.
        icon_name: Material symbol name or an already resolved icon.
        use_option: Whether to show the option action.
        parent: Optional parent widget.
    """

    main_clicked = QtCore.Signal()
    option_clicked = QtCore.Signal()

    def __init__(
        self,
        label: str,
        icon_name: str | QtGui.QIcon = "none",
        use_option: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._icon_name = icon_name
        self._use_option = use_option
        self._shortcut_text = ""
        self._hovered = False
        self._option_hovered = False
        self.setMouseTracking(True)

    def set_shortcut_text(self, shortcut_text: str) -> None:
        self._shortcut_text = shortcut_text
        self.updateGeometry()
        self.update()

    def _menu_style(self, state: str = "base") -> StyleDict:
        style = get_ayon_style().model.get_style("QMenu", state=state)
        style.set_context(self.parentWidget())
        return style

    def _option_rect(self) -> QtCore.QRect:
        if not self._use_option:
            return QtCore.QRect()
        row_height = self.height()
        return QtCore.QRect(
            self.width() - row_height,
            0,
            row_height,
            row_height,
        )

    def _set_row_hover(self, hovered: bool) -> None:
        if self._hovered != hovered:
            self._hovered = hovered
            self.update()

    def _resolved_icon(self) -> QtGui.QIcon:
        if isinstance(self._icon_name, QtGui.QIcon):
            return QtGui.QIcon(self._icon_name)
        if not self._icon_name or self._icon_name == "none":
            return QtGui.QIcon()
        color = QtGui.QColor(
            self._menu_style().get("color", "#f4f5f5")
        )
        return get_icon(self._icon_name, color=color.name())

    def _style_option(self) -> QtWidgets.QStyleOptionMenuItem:
        option = QtWidgets.QStyleOptionMenuItem()
        option.initFrom(self)
        option.menuItemType = (
            QtWidgets.QStyleOptionMenuItem.MenuItemType.Normal
        )
        option.checkType = (
            QtWidgets.QStyleOptionMenuItem.CheckType.NotCheckable
        )
        option.text = self._label
        if self._shortcut_text:
            option.text += f"\t{self._shortcut_text}"
        option.icon = self._resolved_icon()
        option.maxIconWidth = int(
            self._menu_style().get("icon-size", 16)
        )
        if self._hovered:
            option.state |= (
                QtWidgets.QStyle.StateFlag.State_Selected
            )
        return option

    def sizeHint(self) -> QtCore.QSize:
        option = self._style_option()
        size = get_ayon_style().sizeFromContents(
            QtWidgets.QStyle.ContentsType.CT_MenuItem,
            option,
            QtCore.QSize(),
            self.parentWidget(),
        )
        if self._use_option:
            size.setWidth(size.width() + size.height())
        return size

    def paintEvent(self, _event: QtGui.QPaintEvent) -> None:
        option_rect = self._option_rect()
        menu_rect = self.rect()
        if option_rect.isValid():
            menu_rect.setRight(option_rect.left() - 1)

        option = self._style_option()
        option.rect = menu_rect
        painter = QtGui.QPainter(self)
        get_ayon_style().drawControl(
            QtWidgets.QStyle.ControlElement.CE_MenuItem,
            option,
            painter,
            self.parentWidget(),
        )

        if option_rect.isValid():
            state = "hover" if self._hovered else "base"
            style = self._menu_style(state)
            if self._option_hovered:
                painter.fillRect(
                    option_rect,
                    QtGui.QColor(
                        style.get("shortcut-background-color", "#353b46")
                    ),
                )
            icon_size = int(style.get("icon-size", 16))
            color = QtGui.QColor(style.get("color", "#f4f5f5"))
            option_icon = get_icon(
                "check_box_outline_blank",
                color=color.name(),
            )
            option_icon.paint(
                painter,
                QtCore.QRect(
                    option_rect.center().x() - icon_size // 2,
                    option_rect.center().y() - icon_size // 2,
                    icon_size,
                    icon_size,
                ),
            )
        painter.end()

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._set_row_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_row_hover(False)
        self._option_hovered = False
        super().leaveEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        option_hovered = self._option_rect().contains(event.pos())
        if self._option_hovered != option_hovered:
            self._option_hovered = option_hovered
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._option_rect().contains(event.pos()):
            self.option_clicked.emit()
        else:
            self.main_clicked.emit()
        event.accept()

    def is_option_hovered(self, global_pos: QtCore.QPoint) -> bool:
        local_pos = self.mapFromGlobal(global_pos)
        return self._option_rect().contains(local_pos)

    def trigger_option(self) -> None:
        self.option_clicked.emit()


class AYOptionalAction(QtWidgets.QWidgetAction):
    """Menu action with an optional right-hand option box button.

    Subclasses :class:`QtWidgets.QWidgetAction` to embed a custom
    :class:`AYOptionalActionWidget` inside a standard ``QMenu``.

    Set ``use_option=True`` to show the option box and connect to
    :attr:`option_clicked` for the secondary action.

    Args:
        label: Display text.
        icon_name: Material symbol name, resolved icon, or ``"none"``.
        use_option: Whether to show the option box button.
        parent: Parent widget (typically the owning menu).
    """

    option_clicked = QtCore.Signal()

    def __init__(
        self,
        label: str,
        icon_name: str | QtGui.QIcon | None = "none",
        use_option: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._icon_name = icon_name or "none"
        self._use_option = use_option
        self.widget: AYOptionalActionWidget | None = None
        self.setText(label)

    def createWidget(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Instantiate and configure the custom action row widget.

        Called by Qt when the action is added to a menu.

        Args:
            parent: The menu widget that will own the row widget.

        Returns:
            The newly created :class:`AYOptionalActionWidget`.
        """
        widget = AYOptionalActionWidget(
            self._label,
            icon_name=self._icon_name,
            use_option=self._use_option,
            parent=parent,
        )
        widget.setEnabled(self.isEnabled())
        widget.set_shortcut_text(self.shortcut().toString())
        self.widget = widget
        widget.main_clicked.connect(self.trigger)
        widget.main_clicked.connect(self._close_menu_chain)
        widget.option_clicked.connect(self.option_clicked.emit)
        widget.option_clicked.connect(self._close_menu_chain)

        return widget

    def _close_menu_chain(self) -> None:
        """Close the menu (and any parent menus) hosting this action."""
        w = self.widget
        while w is not None:
            if isinstance(w, QtWidgets.QMenu):
                w.close()
            w = w.parentWidget()

    def set_highlight(
        self,
        highlighted: bool,
        _global_pos: QtCore.QPoint | None = None,
    ) -> None:
        """Synchronize hover styling for legacy optional menus."""
        if self.widget is not None:
            self.widget._set_row_hover(highlighted)


class AYMenu(QtWidgets.QMenu):
    """QMenu that paints itself using the AYON style.

    Replicates :meth:`QMenu.paintEvent` but routes every primitive and
    control draw call through :func:`get_ayon_style`, so the menu is
    painted consistently with the rest of the AYON UI without assigning
    the shared AYON style instance to the transient menu.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        get_ayon_style().style_widget(self)

    def paintEvent(self, arg__1: QtGui.QPaintEvent) -> None:
        """Paint the menu using AYON's QStyle implementation.

        Mirrors Qt's own ``QMenu::paintEvent`` order:
        1. Draw the menu panel background (``PE_PanelMenu``).
        2. Draw each visible action row (``CE_MenuItem``).
        3. Draw the menu frame on top (``PE_FrameMenu``).

        Args:
            arg__1: The paint event delivered by Qt.
        """
        style = get_ayon_style()
        painter = QtGui.QPainter(self)

        # --- Shared base option (used for panel + frame) ---
        menu_opt = QtWidgets.QStyleOptionMenuItem()
        menu_opt.initFrom(self)
        menu_opt.state = QtWidgets.QStyle.StateFlag.State_None
        menu_opt.checkType = (
            QtWidgets.QStyleOptionMenuItem.CheckType.NotCheckable
        )
        menu_opt.maxIconWidth = 0
        try:
            menu_opt.reservedShortcutWidth = 0
        except AttributeError:
            # Older Qt versions expose tabWidth instead.
            menu_opt.tabWidth = 0
        menu_opt.rect = self.rect()
        menu_opt.menuRect = self.rect()

        # --- 1. Panel background ---
        style.drawPrimitive(
            QtWidgets.QStyle.PrimitiveElement.PE_PanelMenu,
            menu_opt,
            painter,
            self,
        )

        # --- 2. Action rows ---
        event_region = arg__1.region()
        for action in self.actions():
            action_rect = self.actionGeometry(action)
            if not event_region.intersects(action_rect):
                continue

            opt = QtWidgets.QStyleOptionMenuItem()
            self.initStyleOption(opt, action)
            opt.rect = action_rect
            if action is self.activeAction():
                opt.state |= QtWidgets.QStyle.StateFlag.State_Selected

            style.drawControl(
                QtWidgets.QStyle.ControlElement.CE_MenuItem,
                opt,
                painter,
                self,
            )

        # --- 3. Frame on top ---
        frame_width = style.pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_MenuPanelWidth, menu_opt, self
        )
        if frame_width > 0:
            frame_opt = QtWidgets.QStyleOptionFrame()
            frame_opt.initFrom(self)
            frame_opt.rect = self.rect()
            frame_opt.state = QtWidgets.QStyle.StateFlag.State_None
            frame_opt.lineWidth = frame_width
            frame_opt.midLineWidth = 0
            style.drawPrimitive(
                QtWidgets.QStyle.PrimitiveElement.PE_FrameMenu,
                frame_opt,
                painter,
                self,
            )

        painter.end()


class AYOptionalMenu(AYMenu):
    """AYON-styled menu that supports optional-action widget rows."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.hovered.connect(self._apply_action_hover)
        self.aboutToHide.connect(self._clear_action_highlights)

    def _apply_action_hover(
        self,
        hovered_action: QtWidgets.QAction,
    ) -> None:
        for action in self.actions():
            if isinstance(action, AYOptionalAction):
                action.set_highlight(action is hovered_action)
        self.update()

    def _clear_action_highlights(self) -> None:
        for action in self.actions():
            if isinstance(action, AYOptionalAction):
                action.set_highlight(False)
