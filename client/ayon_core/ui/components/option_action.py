"""Menu action with an option box button (Maya-style option box pattern).

Provides four classes that together implement a menu item composed of a
standard action area (icon + label) and a small option button on the far
right.  Clicking the main area fires the normal ``triggered`` signal;
clicking the option button emits ``OptionBox.clicked`` instead.

Typical usage::

    menu = OptionalMenu("My Menu", parent)
    action = OptionalAction(
        label="Run Process",
        icon=some_icon,
        use_option=True,
        parent=menu,
    )
    action.triggered.connect(lambda: run_process())
    action.widget.option.clicked.connect(lambda: open_options_dialog())
    menu.addAction(action)
"""

from __future__ import annotations

import logging

from qtpy import QtCore, QtGui, QtWidgets

from .label import AYLabel
from .buttons import AYButton
from .layouts import AYHBoxLayout

logger = logging.getLogger(__name__)


class OptionBox(AYButton):
    """Option box widget used as the right-hand button in an action row.

    Emits :attr:`clicked` when the user releases the mouse over this
    widget (the click is detected by the parent :class:`OptionalMenu`).
    """

    def __init__(
        self,
        icon_name: str = "check_box_outline_blank",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            variant=AYButton.Variants.Optional_Action,
            icon=icon_name,
            icon_size=16,
            fixed_width=False,
        )


class OptionalActionWidget(QtWidgets.QWidget):
    """Row widget that combines a body area and an :class:`OptionBox`.

    The body contains an icon label and a text label.  The option box is
    pinned to the far right.  Both sections respond to hover state via
    :meth:`set_hover_properties`.

    Args:
        label: Display text for the action.
        parent: Optional parent widget.
    """

    def __init__(
        self,
        label: str,
        icon_name: str = "none",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        body_widget = QtWidgets.QWidget(self)
        body_widget.setObjectName("OptionalActionBody")

        label_wdgt = AYLabel(
            label,
            variant=AYLabel.Variants.Optional_Action,
            icon=icon_name,
            icon_size=16,
            icon_fill=False,
            parent=body_widget,
        )
        label_wdgt.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
            QtWidgets.QSizePolicy.Policy.MinimumExpanding,
        )

        option_box = OptionBox(parent=body_widget)
        option_box.setObjectName("OptionalActionOption")
        option_box.setFixedSize(30, 30)

        body_layout = AYHBoxLayout(body_widget, spacing=2, margin=0)
        body_layout.addWidget(label_wdgt)

        layout = AYHBoxLayout(self, spacing=0, margin=0)
        layout.addWidget(body_widget)
        layout.addWidget(option_box)

        body_widget.setMouseTracking(True)
        self.setMouseTracking(True)

        self.icon: QtGui.QIcon = QtGui.QIcon()
        self.label: AYLabel = label_wdgt
        self.option: OptionBox = option_box
        self.body: QtWidgets.QWidget = body_widget


class OptionalAction(QtWidgets.QWidgetAction):
    """Menu action with an optional right-hand option box button.

    Subclasses :class:`QtWidgets.QWidgetAction` to embed a custom
    :class:`OptionalActionWidget` inside a standard ``QMenu``.

    Set ``use_option=True`` to show the option box and connect to
    ``widget.option.clicked`` for the secondary action.

    Args:
        label: Display text.
        icon: Optional action icon.
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
        self.widget: OptionalActionWidget | None = None

    def createWidget(self, parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Instantiate and configure the custom action row widget.

        Called by Qt when the action is added to a menu.

        Args:
            parent: The menu widget that will own the row widget.

        Returns:
            The newly created :class:`OptionalActionWidget`.
        """
        widget = OptionalActionWidget(
            self._label,
            icon_name=self._icon_name,
            parent=parent,
        )
        widget.setEnabled(self.isEnabled())
        self.widget = widget

        if self._use_option:
            widget.option.clicked.connect(self.option_clicked.emit)
        else:
            widget.option.setVisible(False)

        return widget
