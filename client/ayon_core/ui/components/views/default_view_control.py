"""Default-view segmented controls for :class:`AYViewSelector`.

Extracted from ``view_selector.py`` to keep the selector module focused
on orchestration.  :class:`DefaultViewControl` owns the Studio/Project
toggle UI and all persistence actions for default views.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QSizePolicy
from qtpy.QtWidgets import QMessageBox

from ..buttons import AYButton
from ..container import AYContainer

from .data_models import View, Visibility, Scope
from .view_manager import DEFAULT_VIEW_LABEL

if TYPE_CHECKING:
    from .view_selector import AYViewSelector

log = logging.getLogger(__name__)


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
            layout_spacing=0,
            layout_margin=0,
        )

        self._studio_control = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=0,
            layout_margin=0,
        )
        self._project_control = AYContainer(
            layout=AYContainer.Layout.HBox,
            layout_spacing=0,
            layout_margin=0,
        )

        self._rebuild_studio_control()
        self._rebuild_project_control()

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

    def _rebuild_studio_control(self) -> None:
        control = self._studio_control
        if control is None:
            return
        self._clear_control(control)

        if self.studio_default_view is None:
            add_btn = AYButton(
                "Studio",
                icon="add",
                variant=AYButton.Variants.Surface,
                fixed_width=False,
                label_alignment=Qt.AlignmentFlag.AlignLeft,
            )
            add_btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            add_btn.clicked.connect(self.on_studio_add_clicked)
            control.add_widget(add_btn, stretch=1)
            return

        close_btn = AYButton(
            icon="close",
            variant=AYButton.Variants.Checked,
            tooltip="Unset studio default",
        )
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.on_studio_close_clicked)
        control.add_widget(close_btn)

        studio_btn = AYButton(
            "Studio",
            variant=AYButton.Variants.Checked,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        studio_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        studio_btn.clicked.connect(self.load_studio_default_view)
        control.add_widget(studio_btn, stretch=1)

    def _rebuild_project_control(self) -> None:
        control = self._project_control
        if control is None:
            return
        self._clear_control(control)

        if self.project_default_view is None:
            add_btn = AYButton(
                "Project",
                icon="add",
                variant=AYButton.Variants.Surface,
                fixed_width=False,
                label_alignment=Qt.AlignmentFlag.AlignLeft,
            )
            add_btn.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            add_btn.clicked.connect(self.on_project_add_clicked)
            control.add_widget(add_btn, stretch=1)
            return

        close_btn = AYButton(
            icon="close",
            variant=AYButton.Variants.Checked,
            tooltip="Unset project default",
        )
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(self.on_project_close_clicked)
        control.add_widget(close_btn)

        project_btn = AYButton(
            "Project",
            variant=AYButton.Variants.Checked,
            fixed_width=False,
            label_alignment=Qt.AlignmentFlag.AlignLeft,
        )
        project_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        project_btn.clicked.connect(self.load_project_default_view)
        control.add_widget(project_btn, stretch=1)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _fetch_default_views(self) -> tuple[View | None, View | None]:
        """Pull the current studio and project default views from the manager."""
        sel = self._selector
        try:
            self.studio_default_view = sel._manager.get_default_studio_view(sel._view_type)
            self.project_default_view = sel._manager.get_default_project_view(sel._view_type)
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
            self._emit_action_message("Studio default view saved.")
        else:
            self._emit_action_message(
                "Failed to save studio default view.", success=False
            )

    def on_studio_close_clicked(self, _checked: bool = False) -> None:
        if self._unset_default_for_scope(Scope.STUDIO):
            self._rebuild_studio_control()
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
            self._emit_action_message("Project default view saved.")
        else:
            self._emit_action_message(
                "Failed to save project default view.", success=False
            )

    def on_project_close_clicked(self, _checked: bool = False) -> None:
        if self._unset_default_for_scope(Scope.PROJECT):
            self._rebuild_project_control()
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
