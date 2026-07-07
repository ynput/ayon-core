"""AYOrder – a drag-and-drop reorderable list of labelled options.

Drag is implemented entirely via mouse events (no QDrag / OS overlay).
The ghost and drop-indicator are child widgets of the AYOrder container,
so they are automatically clipped to its boundaries.
"""

from __future__ import annotations

from typing import Optional

from qtpy.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from qtpy.QtGui import (
    QMouseEvent,
    QPixmap,
)
from qtpy.QtWidgets import (
    QApplication,
    QGraphicsOpacityEffect,
    QLabel,
    QSizePolicy,
    QWidget,
)

from ..variants import QFrameVariants
from .container import AYContainer
from .label import AYLabel


# ---------------------------------------------------------------------------
# Internal: drag ghost
# ---------------------------------------------------------------------------


class _AYOrderGhost(QLabel):
    """Opaque grab of the dragged option.

    Rendered as a child widget of :class:`AYOrder` so it is naturally
    confined to the container's bounding rectangle.  Mouse events pass
    straight through via ``WA_TransparentForMouseEvents``.
    """

    def __init__(
        self,
        pixmap: QPixmap,
        logical_size: QSize,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self.setPixmap(pixmap)
        # Fix to logical size so the pixmap renders at 1:1 on HiDPI too.
        self.setFixedSize(logical_size)
        self.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.raise_()
        self.show()


# ---------------------------------------------------------------------------
# Internal: draggable option row
# ---------------------------------------------------------------------------


class _AYOrderOption(AYLabel):
    """A single draggable row inside :class:`AYOrder`.

    Displays an icon and a text label. Initiates the parent's drag
    logic once the cursor has moved past Qt's start-drag threshold.
    """

    def __init__(
        self,
        text: str,
        icon: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(
            text,
            icon=icon,
            icon_size=20,
            variant=AYLabel.Variants.Order_Option,
            parent=parent,
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_start: Optional[QPoint] = None
        self._dragging: bool = False

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            parent = self.parent()
            if isinstance(parent, AYOrder):
                parent._end_drag()
        self._drag_start = None
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            parent = self.parent()
            if isinstance(parent, AYOrder):
                if not self._dragging:
                    moved = (event.pos() - self._drag_start).manhattanLength()
                    if moved >= QApplication.startDragDistance():
                        self._dragging = True
                        parent._begin_drag(self, event.globalPos())
                else:
                    parent._update_drag(event.globalPos())
        super().mouseMoveEvent(event)


# ---------------------------------------------------------------------------
# Public: AYOrder
# ---------------------------------------------------------------------------


class AYOrder(AYContainer):
    """A vertically-stacked, mouse-drag reorderable list of options.

    Each option is rendered as a labelled row with an icon. Dragging a
    row shows a ghost widget constrained to the container's bounds and a
    drop-indicator line.  On release the :attr:`order_changed` signal is
    emitted with the updated label list.

    Args:
        options: Display names for each option row.
        icons: Material icon names, one per option.  Falls back to
            ``"drag_indicator"`` for every item when *None*.
        variant: :class:`~ayon_core.ui.variants.QFrameVariants` applied to
            the surrounding container frame.
        parent: Optional parent widget.
        **kwargs: Forwarded to :class:`AYContainer`.

    Raises:
        ValueError: When *icons* is provided but its length differs from
            *options*.
    """

    Variant = QFrameVariants

    order_changed = Signal(list)

    def __init__(
        self,
        options: list[str],
        icons: Optional[list[str]] = None,
        variant: QFrameVariants = QFrameVariants.Default,
        parent: Optional[QWidget] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            layout=AYContainer.Layout.VBox,
            variant=variant,
            parent=parent,
            **kwargs,
        )
        if icons is not None and len(icons) != len(options):
            raise ValueError(
                f"icons length ({len(icons)}) must match options "
                f"length ({len(options)})"
            )

        self._options: list[_AYOrderOption] = []

        # Drag state
        self._drag_active: bool = False
        self._drag_index: int = -1
        self._drop_index: int = -1
        self._ghost: Optional[_AYOrderGhost] = None
        self._anim_group: Optional[QParallelAnimationGroup] = None

        # Live-preview state (set at drag start, cleared afterwards)
        self._drag_start_slot_ys: list[int] = []
        self._preview_group: Optional[QParallelAnimationGroup] = None

        _icons = (
            icons if icons is not None else ["drag_indicator"] * len(options)
        )
        for text, icon in zip(options, _icons):
            opt = _AYOrderOption(text, icon, parent=self)
            self._options.append(opt)
            self.add_widget(opt)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_order(self) -> list[str]:
        """Return option labels in their current top-to-bottom order.

        Returns:
            List of option display strings.
        """
        return [opt._text for opt in self._options]

    # ------------------------------------------------------------------
    # Drag lifecycle (called from _AYOrderOption)
    # ------------------------------------------------------------------

    def _stop_animations(self) -> None:
        """Stop any running animations and restore managed layout."""
        if self._anim_group is not None:
            self._anim_group.stop()
            for opt in self._options:
                self._layout.removeWidget(opt)
            for opt in self._options:
                self._layout.addWidget(opt)
            self._layout.activate()
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self._anim_group = None

        if self._preview_group is not None:
            self._preview_group.stop()
            self._preview_group.deleteLater()
            self._preview_group = None

    def _begin_drag(self, option: _AYOrderOption, global_pos: QPoint) -> None:
        """Start a visual drag for *option*.

        Args:
            option: The option widget being dragged.
            global_pos: Initial global cursor position.
        """
        self._stop_animations()

        self._drag_active = True
        self._drag_index = self._options.index(option)

        # Snapshot original slot y-positions for stable insertion math
        # and live-preview target computation throughout the drag.
        self._drag_start_slot_ys = [opt.pos().y() for opt in self._options]

        # Create the ghost from a live render of the option.
        pixmap: QPixmap = option.grab()
        # Make the source row invisible (opacity 0) so the layout keeps
        # the blank space while the ghost floats above.
        invisible = QGraphicsOpacityEffect(option)
        invisible.setOpacity(0.0)
        option.setGraphicsEffect(invisible)
        self._ghost = _AYOrderGhost(pixmap, option.size(), self)

        self._update_drag(global_pos)

    def _update_drag(self, global_pos: QPoint) -> None:
        """Reposition the ghost and drop indicator.

        When the effective insertion index changes, the non-dragged
        widgets are animated to reflect the new drop position.

        Args:
            global_pos: Current global cursor position.
        """
        if not self._drag_active:
            return

        local = self.mapFromGlobal(global_pos)
        opt_src = self._options[self._drag_index]

        # ---- ghost position (clamped to container) -------------------
        if self._ghost is not None:
            gh_h = self._ghost.height()
            x = opt_src.pos().x()
            y = local.y() - gh_h // 2
            y = max(0, min(y, self.height() - gh_h))
            self._ghost.move(x, y)
            self._ghost.raise_()

        # ---- drop indicator + live preview ---------------------------
        new_drop = self._insertion_index(local)
        if new_drop != self._drop_index:
            self._drop_index = new_drop
            self._animate_preview()

    def _end_drag(self) -> None:
        """Finalise the drag: clean up visuals and apply the reorder."""
        if not self._drag_active:
            return

        from_idx = self._drag_index
        to_idx = self._drop_index

        # Remove ghost.
        if self._ghost is not None:
            self._ghost.deleteLater()
            self._ghost = None

        # Remove the invisible effect to restore the source option.
        if 0 <= from_idx < len(self._options):
            self._options[from_idx].setGraphicsEffect(None)

        self._drag_active = False
        self._drag_index = -1
        self._drop_index = -1

        # Snap preview to end values: non-dragged widgets will be at
        # their correct final positions, so _reorder only animates the
        # dragged widget into its new slot.
        self._snap_preview()
        self._reorder(from_idx, to_idx)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _insertion_index(self, pos: QPoint) -> int:
        """Return the insertion index for a drop at *pos*.

        Uses original slot positions during a drag to prevent feedback
        loops caused by live-preview animations shifting widget geometry.

        Args:
            pos: Drop position in widget-local coordinates.

        Returns:
            An index in the range ``[0, len(options)]``.
        """
        if self._drag_active and self._drag_start_slot_ys:
            h = self._options[0].height() if self._options else 0
            for i in range(len(self._options)):
                if pos.y() < self._drag_start_slot_ys[i] + h // 2:
                    return i
            return len(self._options)

        for i, opt in enumerate(self._options):
            if pos.y() < opt.geometry().center().y():
                return i
        return len(self._options)

    def _compute_preview_targets(
        self, drag_idx: int, drop_idx: int
    ) -> dict[_AYOrderOption, int]:
        """Compute target y-positions for non-dragged widgets.

        Uses original slot y-positions as a stable reference so preview
        targets are independent of current animated geometry.

        Args:
            drag_idx: Index of the widget being dragged.
            drop_idx: Current insertion index from the drop indicator.

        Returns:
            Mapping of each non-dragged option to its target y.
        """
        # No-op drop → all non-dragged widgets return to start ys.
        if drop_idx in (drag_idx, drag_idx + 1):
            return {
                opt: self._drag_start_slot_ys[i]
                for i, opt in enumerate(self._options)
                if i != drag_idx
            }

        insert_at = drop_idx - 1 if drop_idx > drag_idx else drop_idx
        virtual = [opt for i, opt in enumerate(self._options) if i != drag_idx]
        result: dict[_AYOrderOption, int] = {}
        slot = 0
        for vi, opt in enumerate(virtual):
            if vi == insert_at:
                slot += 1  # Skip the slot reserved for the dragged item.
            result[opt] = self._drag_start_slot_ys[slot]
            slot += 1
        return result

    def _animate_preview(self) -> None:
        """Slide non-dragged widgets to reflect the current drop position.

        Cancels any in-flight preview and starts a fresh parallel group.
        Widgets remain in the layout; the animation uses the ``pos``
        property directly, which the layout will not override during the
        short animation window.
        """
        if not self._drag_active or not self._drag_start_slot_ys:
            return

        # Cancel previous preview; widgets stay at their current pos.
        if self._preview_group is not None:
            self._preview_group.stop()
            self._preview_group.deleteLater()
            self._preview_group = None

        targets = self._compute_preview_targets(
            self._drag_index, self._drop_index
        )
        group = QParallelAnimationGroup(self)
        for opt, target_y in targets.items():
            current_y = opt.pos().y()
            if current_y == target_y:
                continue
            anim = QPropertyAnimation(opt, b"pos", group)
            anim.setDuration(120)
            anim.setStartValue(QPoint(opt.pos().x(), current_y))
            anim.setEndValue(QPoint(opt.pos().x(), target_y))
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            group.addAnimation(anim)

        if group.animationCount() > 0:
            group.start()
            self._preview_group = group
        else:
            group.deleteLater()

    def _snap_preview(self) -> None:
        """Instantly complete any in-flight preview animation.

        Called just before :meth:`_reorder` so that non-dragged widgets
        are already at their correct final positions.
        """
        if self._preview_group is None:
            return
        for i in range(self._preview_group.animationCount()):
            anim = self._preview_group.animationAt(i)
            if isinstance(anim, QPropertyAnimation):
                anim.setCurrentTime(anim.duration())
        self._preview_group.stop()
        self._preview_group.deleteLater()
        self._preview_group = None

    def _reorder(self, from_idx: int, to_idx: int) -> None:
        """Move one option and emit :attr:`order_changed`.

        Widgets displaced by the move are animated to their new
        positions.  A no-op when the item would end up in its current
        position.

        When preceded by a drag gesture (live preview active), non-
        dragged widgets are already at their final positions; only the
        dragged widget then needs to be animated into its new slot.

        Args:
            from_idx: Current index of the item to move.
            to_idx: Insertion index *before* removal, as returned by
                :meth:`_insertion_index`.
        """
        if to_idx in (from_idx, from_idx + 1):
            self._drag_start_slot_ys = []
            return

        old_ys = (
            list(self._drag_start_slot_ys)
            if self._drag_start_slot_ys
            else [opt.pos().y() for opt in self._options]
        )
        self._drag_start_slot_ys = []

        old_positions = {opt: QPoint(opt.pos()) for opt in self._options}

        # Logical reorder.
        item = self._options.pop(from_idx)
        insert_at = to_idx - 1 if to_idx > from_idx else to_idx
        self._options.insert(insert_at, item)

        # Build per-widget target positions.
        new_positions = {
            opt: QPoint(old_positions[opt].x(), old_ys[i])
            for i, opt in enumerate(self._options)
        }

        self._animate_reorder(old_positions, new_positions)
        self.order_changed.emit(self.current_order())

    def _animate_reorder(
        self,
        old_positions: dict[_AYOrderOption, QPoint],
        new_positions: dict[_AYOrderOption, QPoint],
    ) -> None:
        """Animate widgets from old to new positions, then restore layout.

        Args:
            old_positions: Mapping of options to their starting positions.
            new_positions: Mapping of options to their target positions.
        """
        # Detach widgets from layout and lock height during animation.
        for opt in self._options:
            self._layout.removeWidget(opt)
        self.setFixedHeight(self.height())

        for opt, dst in new_positions.items():
            if old_positions[opt] != dst:
                opt.move(dst)

        self._restore_layout()

    def _restore_layout(self) -> None:
        """Re-add widgets to layout and restore dynamic sizing."""
        for opt in self._options:
            self._layout.addWidget(opt)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self._anim_group = None
