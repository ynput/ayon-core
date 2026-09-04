"""Default-view segmented controls for :class:`AYViewSelector`.

Extracted from ``view_selector.py`` to keep the selector module focused
on orchestration.  :class:`DefaultViewControl` owns the Studio/Project
toggle UI and all persistence actions for default views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from qtpy.QtCore import QPointF, QRect, QRectF, Qt
from qtpy.QtGui import QBrush, QColor, QPainter
from qtpy.QtWidgets import (
    QMessageBox,
    QSizePolicy,
    QStyle,
    QStyleOptionButton,
)

from ..buttons import AYButton
from ..container import AYContainer
from ..frame import RowHoverTracker
from ...style_types import get_ayon_style, get_ayon_style_data

from .data_models import View, Visibility, Scope, ViewSettings
from .view_manager import DEFAULT_VIEW_LABEL

if TYPE_CHECKING:
    from .view_selector import AYViewSelector

log = logging.getLogger(__name__)

# Side length of the icon's hoverable badge — a bit larger than the
# icon glyph itself (14px) so it reads as a distinct clickable target.
# "chip"/"chip-active"'s icon-padding[0] (4) is tuned to this exact
# value: it puts the icon's center at size/2 from the pill's own left
# edge, the minimum that lets a badge this size fit without clipping.
# Changing one without the other reintroduces clipping or an
# unnecessarily large left-padding — see _icon_badge_rect().
_ICON_BADGE_SIZE = 16


class _DefaultViewPillButton(AYButton):
    """A default-view pill's single icon+label button.

    Always one button with the icon fixed on the left and the label on
    the right, so the label never shifts between the pill's "unset"
    (dashed, ``+``) and "active" (filled, ``x``) look — only the icon
    glyph changes. In the "unset" state the icon is purely decorative
    and non-interactive: a click anywhere (including over the icon)
    saves the current view as the default, and the icon never gets its
    own hover badge, since ``_icon_click`` is ``None`` there and every
    hover/click check below is gated on it. In the "active" state, a
    click on the icon specifically removes the default instead of
    loading it, and hovering it paints its own badge — centered on the
    actual painted icon glyph — so it still reads as a separate action
    from the rest of the pill.
    """

    def __init__(
        self,
        *args,
        icon_click: Callable[[], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._icon_click = icon_click
        self._icon_hovered = False
        if icon_click is not None:
            self.setMouseTracking(True)

    def _icon_center(self) -> QPointF:
        """Return where the drawer paints the icon glyph's center.

        Mirrors ``ButtonDrawer``'s icon+text layout — icon centered at
        ``(content_rect.left() + icon-padding[0], content_rect.center().y())``
        — so the hover badge and the icon-click hit zone both land
        exactly on the glyph instead of an independently-guessed
        offset. Note this is ``content_rect``'s own vertical center,
        not the button widget's — they aren't always the same.
        """
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = self.rect()
        content_rect = self.style().subElementRect(
            QStyle.SubElement.SE_PushButtonContents, option, self
        )
        style = get_ayon_style_data("QPushButton", self._variant_str)
        icon_padding_x = style.get("icon-padding", [4, 4])[0]
        return QPointF(
            content_rect.left() + icon_padding_x, content_rect.center().y()
        )

    def _icon_badge_rect(self) -> QRectF:
        # Cap to the button's own height (minus a small margin) — a
        # no-op at _ICON_BADGE_SIZE's current tuning, kept as a safety
        # net for a future shorter button.
        size = min(_ICON_BADGE_SIZE, self.height() - 4)
        # Always centered on the icon (see _ICON_BADGE_SIZE for why
        # this fits without clipping); paintEvent still clips to the
        # button's own rect defensively rather than shifting the badge
        # off-center to force a fit.
        center = self._icon_center()
        return QRectF(center.x() - size / 2, center.y() - size / 2, size, size)

    def _is_in_icon_zone(self, x: int) -> bool:
        if self._icon_click is None:
            return False
        badge = self._icon_badge_rect()
        return badge.left() <= x <= badge.right()

    def _set_icon_hovered(self, hovered: bool) -> None:
        if hovered == self._icon_hovered:
            return
        self._icon_hovered = hovered
        self.update()

    def mouseMoveEvent(self, event) -> None:
        self._set_icon_hovered(self._is_in_icon_zone(event.pos().x()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_icon_hovered(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.pos())
            and self._is_in_icon_zone(event.pos().x())
        ):
            self.setDown(False)
            self._icon_click()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        # Deliberately not a plain ``super().paintEvent()`` call: this
        # button needs to paint its hover badge *between* the button's
        # background and its icon/text, so both layers stay under one
        # continuous QPainter session. A badge painted before calling
        # ``super().paintEvent()`` (in its own, separate QPainter
        # session) was silently erased once the base paint ran its own
        # QPainter session on this widget — reproducible only once
        # nested inside a real selected "Pill" container, not when
        # tested standalone. Mirrors ``AYButton.paintEvent()``'s own
        # size-hint handling, then calls the same two style elements it
        # would (bevel, then label) with the badge painted in between.
        painter = QPainter(self)
        option = QStyleOptionButton()
        self.initStyleOption(option)
        size = self.sizeHint()
        if self.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed:
            self.setFixedSize(size)
            option.rect = QRect(0, 0, size.width(), size.height())
        else:
            self.setFixedHeight(size.height())

        style = get_ayon_style()
        style.drawControl(
            QStyle.ControlElement.CE_PushButtonBevel, option, painter, self,
        )

        # Guard on _icon_click (not just _icon_hovered): the "unset"
        # ("+") state is meant to render as a plain, non-interactive
        # icon, never with its own hover badge.
        if self._icon_hovered and self._icon_click is not None:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            # The badge is centered on the icon, which can put its left
            # edge past x=0 when the icon sits close to the pill's own
            # left edge — clip to the button's own rect rather than
            # shifting the badge right, which would throw off centering.
            painter.setClipRect(self.rect())
            # The pill's own "selected" background is already
            # ``surface-container-highest-dark`` (#424a57); its "hover"
            # sibling is only ~11 units brighter per channel — too
            # subtle once anti-aliased at this size — so use the
            # outline token for a badge that reads clearly regardless
            # of the pill's exact surrounding shade.
            palette = style.model.palette()
            badge_color = palette.get(
                "--md-sys-color-outline-dark",
                "#8b9198",
            )
            painter.setBrush(QBrush(QColor(badge_color)))
            painter.drawRoundedRect(self._icon_badge_rect(), 6, 6)
            painter.restore()

        style.drawControl(
            QStyle.ControlElement.CE_PushButtonLabel, option, painter, self,
        )


class DefaultViewControl:
    """Manages the Default View row UI and persistence for a selector.

    Owns:
    - Building the two-scope row widget (``build_row``).
    - In-place rebuilding of either scope control without recreating the
      full row.
    - Save / unset actions for studio and project default views.

    The owning :class:`AYViewSelector` is passed in and used for access
    to ``_bindings``, ``_manager``, ``_view_type``, ``_current_user``
    and ``_suspend_auto_apply``.
    """

    def __init__(self, selector: "AYViewSelector") -> None:
        self._selector = selector

        self.studio_default_view: View | None = None
        self.project_default_view: View | None = None

        self._studio_control: AYContainer | None = None
        self._project_control: AYContainer | None = None

    # ------------------------------------------------------------------
    # Row builder
    # ------------------------------------------------------------------

    def build_row(self) -> AYContainer:
        """Build and return the full Studio + Project default-view row."""
        self.studio_default_view, self.project_default_view = (
            self._fetch_default_views()
        )

        row = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Popover,
            layout_spacing=6,
            layout_margin=0,
        )

        self._studio_control = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Pill,
            layout_spacing=0,
            layout_margin=2,
            hover_enabled=True,
        )
        self._project_control = AYContainer(
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Pill,
            layout_spacing=0,
            layout_margin=2,
            hover_enabled=True,
        )

        self._rebuild_studio_control()
        self._rebuild_project_control()

        # Both pills share the row evenly instead of hugging their own
        # content width, so together they fill the panel.
        row.add_widget(self._studio_control, stretch=1)
        row.add_widget(self._project_control, stretch=1)
        return row

    # ------------------------------------------------------------------
    # Scope control builders
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_control(control: AYContainer | None) -> None:
        if control is None:
            return
        layout = control.layout()
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def _build_pill(
        self,
        control: AYContainer,
        label: str,
        is_active: bool,
        on_click: Callable[[], None],
        on_icon_click: Callable[[], None] | None,
    ) -> None:
        """Populate *control* with the pill's single icon+label button.

        Args:
            control: The pill's wrapping frame (carries the
                selected/hover look; already cleared by the caller).
            label: "Studio" or "Project".
            is_active: Whether a default view is currently set — picks
                the icon (``x``/``add``), the variant (bright/dim) and
                whether the icon becomes its own click target.
            on_click: Handler for a click anywhere but the icon
                (always fires in the unset state, since there the icon
                isn't a distinct target).
            on_icon_click: Handler for a click on the icon
                specifically; only used when ``is_active``.
        """
        control.set_selected(is_active)
        btn = _DefaultViewPillButton(
            label,
            icon="close" if is_active else "add",
            icon_size=14,
            variant=(
                AYButton.Variants.Chip_Active
                if is_active
                else AYButton.Variants.Chip
            ),
            fixed_width=False,
            icon_click=on_icon_click if is_active else None,
        )
        btn.clicked.connect(on_click)
        control.addStretch(1)
        control.add_widget(btn)
        control.addStretch(1)
        RowHoverTracker(control).watch(btn)

    def _rebuild_studio_control(self) -> None:
        control = self._studio_control
        if control is None:
            return
        self._clear_control(control)
        is_active = self.studio_default_view is not None
        self._build_pill(
            control,
            "Studio",
            is_active,
            on_click=(
                self.load_studio_default_view
                if is_active
                else self.on_studio_add_clicked
            ),
            on_icon_click=self.on_studio_close_clicked if is_active else None,
        )

    def _rebuild_project_control(self) -> None:
        control = self._project_control
        if control is None:
            return
        self._clear_control(control)
        is_active = self.project_default_view is not None
        self._build_pill(
            control,
            "Project",
            is_active,
            on_click=(
                self.load_project_default_view
                if is_active
                else self.on_project_add_clicked
            ),
            on_icon_click=self.on_project_close_clicked if is_active else None,
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _fetch_default_views(self) -> tuple[View | None, View | None]:
        """Pull current studio and project default views from manager."""
        sel = self._selector
        try:
            self.studio_default_view = sel._manager.get_default_studio_view(
                sel._view_type
            )
            self.project_default_view = sel._manager.get_default_project_view(
                sel._view_type
            )
            return self.studio_default_view, self.project_default_view
        except Exception:
            log.exception(
                "Failed to retrieve default views for %r", sel._view_type
            )
            return None, None

    def _set_default_for_scope(self, scope: Scope) -> View | None:
        sel = self._selector
        default_view = (
            self.studio_default_view
            if scope == Scope.STUDIO
            else self.project_default_view
        )
        if default_view is None:
            default_view = View(
                label=DEFAULT_VIEW_LABEL,
                settings=sel._bindings.capture(),
                working=False,
                scope=scope,
                visibility=Visibility.PRIVATE,
                view_type=sel._view_type,
                owner=sel._current_user,
            )
        else:
            default_view.settings = sel._bindings.capture()

        saved = sel._save_view(default_view)
        if saved is None:
            return None

        if scope == Scope.STUDIO:
            self.studio_default_view = saved
        else:
            self.project_default_view = saved
        return saved

    def _emit_action_message(self, message: str, success: bool = True) -> None:
        self._selector.emit_default_view_message(message, success)

    def _unset_default_for_scope(self, scope: Scope) -> bool:
        sel = self._selector
        default_view = (
            self.studio_default_view
            if scope == Scope.STUDIO
            else self.project_default_view
        )
        if default_view is None or not default_view.id:
            return False

        if not self._confirm_unset_default(scope):
            return False

        try:
            sel._manager.delete_view(default_view.id)
        except Exception:
            log.exception("Failed to delete default view %r", default_view.id)
            scope_label = "Studio" if scope == Scope.STUDIO else "Project"
            self._emit_action_message(
                f"Failed to unset {scope_label.lower()} default view.",
                success=False,
            )
            return False

        if scope == Scope.STUDIO:
            self.studio_default_view = None
        else:
            self.project_default_view = None
        return True

    # ------------------------------------------------------------------
    # Studio callbacks
    # ------------------------------------------------------------------

    def on_studio_add_clicked(self, _checked: bool = False) -> None:
        if self._set_default_for_scope(Scope.STUDIO) is not None:
            self._rebuild_studio_control()
            self._selector.refresh_dropdown_size()
            self._emit_action_message("Studio default view saved.")
        else:
            self._emit_action_message(
                "Failed to save studio default view.", success=False
            )

    def on_studio_close_clicked(self, _checked: bool = False) -> None:
        if self._unset_default_for_scope(Scope.STUDIO):
            self._rebuild_studio_control()
            self._selector.refresh_dropdown_size()
            self._emit_action_message("Studio default view removed.")

    def load_studio_default_view(self, _checked: bool = False) -> None:
        self._fetch_default_views()
        if self.studio_default_view is None:
            self._emit_action_message(
                "No studio default view configured.",
                success=False,
            )
            return
        try:
            self._selector._apply_view(self.studio_default_view, emit=True)
            self._emit_action_message("Loaded studio default view.")
        except Exception:
            self._emit_action_message(
                "Failed to load studio default view.",
                success=False,
            )

    # ------------------------------------------------------------------
    # Project callbacks
    # ------------------------------------------------------------------

    def on_project_add_clicked(self, _checked: bool = False) -> None:
        if self._set_default_for_scope(Scope.PROJECT) is not None:
            self._rebuild_project_control()
            self._selector.refresh_dropdown_size()
            self._emit_action_message("Project default view saved.")
        else:
            self._emit_action_message(
                "Failed to save project default view.", success=False
            )

    def on_project_close_clicked(self, _checked: bool = False) -> None:
        if self._unset_default_for_scope(Scope.PROJECT):
            self._rebuild_project_control()
            self._selector.refresh_dropdown_size()
            self._emit_action_message("Project default view removed.")

    def load_project_default_view(self, _checked: bool = False) -> None:
        self._fetch_default_views()
        if self.project_default_view is None:
            self._emit_action_message(
                "No project default view configured.",
                success=False,
            )
            return
        try:
            self._selector._apply_view(self.project_default_view, emit=True)
            self._emit_action_message("Loaded project default view.")
        except Exception:
            self._emit_action_message(
                "Failed to load project default view.",
                success=False,
            )

    def make_default_view_settings(self):
        """
        Apply the default view settings to the selector's bindings.
        """
        default_view = ViewSettings()
        self._selector._bindings.apply(default_view)
        self._selector._clear_modified()
        self._selector._close_menu()
        self._emit_action_message("Reset to defaults.")

    def _confirm_unset_default(self, scope: Scope) -> bool:
        """Ask for user confirmation before removing a default view."""
        scope_label = "Studio" if scope == Scope.STUDIO else "Project"
        message_box = QMessageBox(self._selector)
        message_box.setIcon(QMessageBox.Icon.Warning)
        message_box.setWindowTitle(f"Remove {scope_label} view")
        message_box.setText(
            f"Are you sure you want to remove {scope_label.lower()} view?"
        )

        remove_button = message_box.addButton(
            "Remove",
            QMessageBox.ButtonRole.AcceptRole,
        )
        message_box.addButton(
            "Cancel",
            QMessageBox.ButtonRole.RejectRole,
        )
        message_box.setDefaultButton(remove_button)

        message_box.exec()
        return message_box.clickedButton() == remove_button


__all__ = ("DefaultViewControl",)
