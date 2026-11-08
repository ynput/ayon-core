"""Guide shown next to the placeholders when none is being edited."""

from __future__ import annotations

from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.ui.components import AYContainer, AYLabel

from .utils import (
    HIGHEST_SURFACE_COLOR,
    ON_PRIMARY_COLOR,
    ON_SURFACE_COLOR,
    OUTLINE_COLOR,
    PRIMARY_COLOR,
    get_palette_color,
)

STEP_TODO = "todo"
STEP_ACTIVE = "active"
STEP_DONE = "done"

# Steps of building a template as (title, explanation)
GUIDE_STEPS = (
    (
        "Add a placeholder",
        "Each one loads or creates something when the template is built.",
    ),
    (
        "Check the preview",
        (
            "Select a placeholder to see what it would load. Use"
            " \"Preview as\" to try a real asset or shot."
        ),
    ),
    (
        "Test the template",
        (
            "Run all populates every placeholder in the open scene for the"
            " \"Preview as\" context. Reopen the template to undo it."
        ),
    ),
)

ARROW_SIZE = QtCore.QSize(72, 48)
# Vertical position of the arrow tip. Matches the middle of the "Add" button
#   at the top of the placeholders panel next to the guide.
ARROW_TIP_Y = 15
ARROW_SPACING = 8
STEP_BADGE_SIZE = 22
# Space between the steps of the guide
STEP_SPACING = 14


class _ArrowWidget(QtWidgets.QWidget):
    """Hand drawn arrow that points to the left, at the "Add" button."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setFixedSize(ARROW_SIZE)
        self._color = QtGui.QColor(get_palette_color(PRIMARY_COLOR))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(self._color, 2)
        pen.setCapStyle(QtCore.Qt.RoundCap)
        pen.setJoinStyle(QtCore.Qt.RoundJoin)
        painter.setPen(pen)

        # A swoop with a small loop, drawn in a 72x48 box from the bottom
        #   right towards the tip on the left.
        point = QtCore.QPointF
        tip = point(3, ARROW_TIP_Y)
        path = QtGui.QPainterPath(point(68, 44))
        path.cubicTo(point(56, 46), point(46, 40), point(44, 30))
        path.cubicTo(point(42, 20), point(52, 16), point(54, 24))
        path.cubicTo(point(56, 32), point(44, 36), point(34, 30))
        path.cubicTo(point(24, 24), point(12, 16), tip)
        painter.drawPath(path)
        painter.drawLine(tip, QtCore.QPointF(11, ARROW_TIP_Y - 6))
        painter.drawLine(tip, QtCore.QPointF(10, ARROW_TIP_Y + 7))


class _StepBadge(QtWidgets.QWidget):
    """Number of a step, or a check mark when the step is done."""

    def __init__(
        self, number: int, parent: Optional[QtWidgets.QWidget] = None
    ):
        super().__init__(parent)
        self.setFixedSize(STEP_BADGE_SIZE, STEP_BADGE_SIZE)
        self._number = number
        self._state = STEP_TODO

    def get_state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if self._state == STEP_ACTIVE:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(get_palette_color(PRIMARY_COLOR)))
            painter.drawEllipse(rect)
            self._draw_number(
                painter, get_palette_color(ON_PRIMARY_COLOR)
            )
            return

        if self._state == STEP_DONE:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(
                QtGui.QColor(get_palette_color(HIGHEST_SURFACE_COLOR))
            )
            painter.drawEllipse(rect)
            pen = QtGui.QPen(
                QtGui.QColor(get_palette_color(ON_SURFACE_COLOR)), 2
            )
            pen.setCapStyle(QtCore.Qt.RoundCap)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            painter.setPen(pen)
            size = STEP_BADGE_SIZE
            check = QtGui.QPainterPath(QtCore.QPointF(size * 0.3, size * 0.5))
            check.lineTo(size * 0.45, size * 0.65)
            check.lineTo(size * 0.72, size * 0.36)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawPath(check)
            return

        outline_color = get_palette_color(OUTLINE_COLOR)
        painter.setPen(QtGui.QPen(QtGui.QColor(outline_color), 1))
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawEllipse(rect)
        self._draw_number(painter, outline_color)

    def _draw_number(self, painter: QtGui.QPainter, color: str) -> None:
        font = QtGui.QFont(self.font())
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QtGui.QColor(color))
        painter.drawText(
            self.rect(), QtCore.Qt.AlignCenter, str(self._number)
        )


class _StepsWidget(QtWidgets.QWidget):
    """Numbered steps of the guide with a short explanation each.

    A single grid keeps badges, titles and word wrapped explanations
    aligned and lets the explanations take the height they need.
    """

    def __init__(
        self,
        steps: tuple[tuple[str, str], ...],
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)

        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(2)
        layout.setColumnStretch(1, 1)

        badges = []
        row = 0
        for number, (title, text) in enumerate(steps, 1):
            if row:
                layout.setRowMinimumHeight(row, STEP_SPACING)
                row += 1
            badge = _StepBadge(number, self)
            title_label = AYLabel(title, parent=self, bold=True)
            text_label = AYLabel(
                text, parent=self, dim=True, flexible=True
            )
            text_label.setWordWrap(True)
            layout.addWidget(
                badge, row, 0, 2, 1, QtCore.Qt.AlignTop
            )
            layout.addWidget(title_label, row, 1)
            layout.addWidget(text_label, row + 1, 1)
            badges.append(badge)
            row += 2

        self._badges = badges

    def get_states(self) -> list[str]:
        return [badge.get_state() for badge in self._badges]

    def set_states(self, states: tuple[str, ...]) -> None:
        for badge, state in zip(self._badges, states):
            badge.set_state(state)


class PlaceholderGuideWidget(AYContainer):
    """Guide through building a template, shown when nothing is edited.

    Points to the "Add" button of the placeholders panel when there are no
    placeholders yet and shows the steps of building a template. Shows only
    a message when placeholders can't be created in the host.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=0,
        )

        # --- Pointer to the "Add" button ---
        pointer_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=ARROW_SPACING,
        )
        arrow_widget = _ArrowWidget(pointer_widget)
        pointer_label = AYLabel(
            "Start here: add your first placeholder",
            parent=pointer_widget,
            text_color=get_palette_color(PRIMARY_COLOR),
            rel_text_size=1,
        )
        pointer_widget.add_widget(arrow_widget)
        pointer_widget.layout().addWidget(
            pointer_label, 0, QtCore.Qt.AlignBottom
        )
        pointer_widget.addStretch(1)

        # --- Guide ---
        # Texts are aligned with the text next to the arrow
        content_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_spacing=20,
        )
        content_widget.setContentsMargins(
            ARROW_SIZE.width() + ARROW_SPACING, 0, 0, 0
        )
        content_widget.setMaximumWidth(
            ARROW_SIZE.width() + ARROW_SPACING + 480
        )

        header_widget = AYContainer(
            content_widget,
            layout=AYContainer.Layout.VBox,
            layout_spacing=6,
        )
        title_label = AYLabel(
            parent=header_widget, rel_text_size=4, bold=True
        )
        # Word wrapped labels are flexible, otherwise they require width of
        #   the whole text and the wrapped lines are cut off.
        message_label = AYLabel(
            parent=header_widget, dim=True, flexible=True
        )
        message_label.setWordWrap(True)
        header_widget.add_widget(title_label)
        header_widget.add_widget(message_label)

        steps_widget = _StepsWidget(GUIDE_STEPS, content_widget)

        content_widget.add_widget(header_widget)
        content_widget.add_widget(steps_widget)

        self.add_widget(pointer_widget)
        self.layout().addSpacing(24)
        self.add_widget(content_widget)
        self.addStretch(1)

        self._pointer_widget = pointer_widget
        self._title_label = title_label
        self._message_label = message_label
        self._steps_widget = steps_widget

    def set_guide(self, has_placeholders: bool) -> None:
        """Show the steps of building a template.

        Args:
            has_placeholders (bool): The scene already has placeholders, so
                the first step is done.

        """
        if has_placeholders:
            title = "Select a placeholder"
            message = (
                "Pick a placeholder on the left to change its options and"
                " see what it would do, or add another one."
            )
            states = (STEP_DONE, STEP_ACTIVE, STEP_TODO)
        else:
            title = "Build your first template"
            message = (
                "Placeholders tell AYON what to load or create when an"
                " artist starts a workfile from this template."
            )
            states = (STEP_ACTIVE, STEP_TODO, STEP_TODO)

        self._title_label.setText(title)
        self._message_label.setText(message)
        self._steps_widget.set_states(states)
        self._pointer_widget.setVisible(not has_placeholders)
        self._steps_widget.setVisible(True)

    def set_unavailable(self, title: str, message: str) -> None:
        """Explain why placeholders can't be created.

        Args:
            title (str): Heading of the message.
            message (str): Explanation shown under the heading.

        """
        self._title_label.setText(title)
        self._message_label.setText(message)
        self._pointer_widget.setVisible(False)
        self._steps_widget.setVisible(False)
