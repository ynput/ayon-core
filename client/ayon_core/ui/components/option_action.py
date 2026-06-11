"""Menu action with an option box button (Maya-style option box pattern).

Provides three classes that together implement a menu item composed of
a standard action area (icon + label) and a small option button on the
far right.  Clicking the main area fires the normal ``triggered``
signal; clicking the option button emits ``OptionalAction.option_clicked``
instead.

Typical usage::

    menu = QMenu("My Menu", parent)
    action = OptionalAction(
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

import logging

from qtpy import QtCore, QtGui, QtWidgets

from ..style_types import get_ayon_style
from .buttons import AYButton
from .frame import AYFrame
from .label import AYLabel
from .layouts import AYHBoxLayout

logger = logging.getLogger(__name__)


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


class AYOptionalActionWidget(QtWidgets.QWidget):
    """Row widget that combines a body area and an :class:`AYOptionBox`.

    The body contains an icon label and a text label.  The option box
    is pinned to the far right.  Both sections respond to hover state
    via :meth:`_set_row_hover` and :meth:`_sync_row_hover`.

    Args:
        label: Display text for the action.
        icon_name: Material symbol icon name for the label.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        label: str,
        icon_name: str = "none",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        _style = get_ayon_style().model.get_style(
            "QLabel", variant=AYLabel.Variants.Optional_Action.value
        )
        icon_size = _style.get("icon-size", 16)

        body_widget = AYFrame(self, variant=AYFrame.Variants.Contextual_Menu)
        body_widget.setObjectName("OptionalActionBody")

        label_wdgt = AYLabel(
            label,
            variant=AYLabel.Variants.Optional_Action,
            icon=icon_name,
            icon_size=icon_size,
            icon_fill=False,
            parent=body_widget,
        )
        min_h = int(
            get_ayon_style().model.get_style("QMenu").get("min-item-height", 0)
        )
        self.setMinimumHeight(min_h)

        option_box = AYOptionBox(icon_size=icon_size, parent=body_widget)
        option_box.setObjectName("OptionalActionOption")

        body_layout = AYHBoxLayout(body_widget, spacing=2, margin=0)
        body_layout.addWidget(label_wdgt, stretch=1)

        layout = AYHBoxLayout(self, spacing=0, margin=0)
        layout.addWidget(body_widget)
        layout.addWidget(option_box)

        body_widget.setMouseTracking(True)
        self.setMouseTracking(True)

        self.icon: QtGui.QIcon = QtGui.QIcon()
        self.label: AYLabel = label_wdgt
        self.option: AYOptionBox = option_box
        self.body: QtWidgets.QWidget = body_widget

        # Watch the children's hover transitions so we can keep them in sync
        # while the cursor moves between them.
        self.label.installEventFilter(self)
        self.option.installEventFilter(self)

    # -- hover propagation ------------------------------------------------

    def _set_row_hover(self, hovered: bool) -> None:
        for child in (self.body, self.label, self.option):
            child.setAttribute(QtCore.Qt.WA_UnderMouse, hovered)
            child.update()

    def _sync_row_hover(self) -> None:
        # ``underMouse()`` on the parent stays True as long as the cursor is
        # anywhere inside this row, even while crossing child borders.
        self._set_row_hover(self.underMouse())

    def enterEvent(self, event: QtCore.QEvent) -> None:
        self._set_row_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_row_hover(False)
        super().leaveEvent(event)

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if obj in (self.body, self.label, self.option) and event.type() in (
            QtCore.QEvent.Type.Enter,
            QtCore.QEvent.Type.Leave,
        ):
            # Qt is about to flip WA_UnderMouse on this child.  Defer to
            # the next event-loop tick so Qt's own handling has finished,
            # then re-assert hover state based on the parent.
            QtCore.QTimer.singleShot(0, self._sync_row_hover)
        return super().eventFilter(obj, event)


class AYOptionalAction(QtWidgets.QWidgetAction):
    """Menu action with an optional right-hand option box button.

    Subclasses :class:`QtWidgets.QWidgetAction` to embed a custom
    :class:`AYOptionalActionWidget` inside a standard ``QMenu``.

    Set ``use_option=True`` to show the option box and connect to
    :attr:`option_clicked` for the secondary action.

    Args:
        label: Display text.
        icon_name: Material symbol icon name (or ``"none"``).
        use_option: Whether to show the option box button.
        parent: Parent widget (typically the owning menu).
    """

    option_clicked = QtCore.Signal()

    def __init__(
        self,
        label: str,
        icon_name: str | None = "none",
        use_option: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._icon_name = icon_name or "none"
        self._use_option = use_option
        self.widget: AYOptionalActionWidget | None = None

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
            parent=parent,
        )
        widget.setEnabled(self.isEnabled())
        self.widget = widget

        if self._use_option:
            widget.option.clicked.connect(self.option_clicked.emit)
            widget.option.clicked.connect(self._close_menu_chain)
        else:
            widget.option.setVisible(False)

        return widget

    def _close_menu_chain(self) -> None:
        """Close the menu (and any parent menus) hosting this action."""
        w = self.widget
        while w is not None:
            if isinstance(w, QtWidgets.QMenu):
                w.close()
            w = w.parentWidget()


class AYMenu(QtWidgets.QMenu):
    """QMenu that paints itself using the AYON style.

    Replicates :meth:`QMenu.paintEvent` but routes every primitive and
    control draw call through :func:`get_ayon_style`, so the menu is
    painted consistently with the rest of the AYON UI even when the
    application style isn't AYONStyle.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setStyle(get_ayon_style())

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
