"""Modal dialog for editing :class:`View` metadata.

The dialog is intentionally *metadata only*: it edits label, scope,
visibility, access level and the ``working`` flag.  The actual UI
configuration (columns, sort, filter…) is captured by
:meth:`ViewBindings.capture` at the call site and merged with the
metadata into the returned :class:`View` by the caller.

The dialog never talks to a :class:`ViewManager` directly — it just
collects values and exposes them through :meth:`get_view` after the
user accepts.  The :class:`AYViewSelector` is responsible for invoking
``manager.save_view(view)``.
"""

from __future__ import annotations

import logging
from enum import IntEnum

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QSizePolicy,
    QWidget,
)

from ...style_types import get_ayon_style
from ..buttons import AYButton
from ..combo_box import AYComboBox
from ..container import AYContainer
from ..layouts import AYVBoxLayout
from ..line_edit import AYLineEdit
from .data_models import Scope, View, Visibility

log = logging.getLogger(__name__)


class AYViewEditor(QDialog):
    """Modal editor for the metadata fields of a :class:`View`.

    Args:
        view: The :class:`View` to edit.  Pass a fresh ``View()`` with
            an empty ``id`` to create a new view.
        current_user: User identifier of the editor.  Used to gate the
            studio scope when applicable.
        allow_studio_scope: Whether ``Scope.STUDIO`` is offered to the
            user.  Consumer apps gate this via their permission model.
        parent: Optional parent widget.
    """

    class Mode(IntEnum):
        """Dialog mode: create or edit."""

        CREATE = 0
        EDIT = 1

    def __init__(
        self,
        view: View,
        current_user: str = "",
        current_project: str = "",
        allow_studio_scope: bool = False,
        user_list: list | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._dialog_mode = (
            AYViewEditor.Mode.EDIT if view.id else AYViewEditor.Mode.CREATE
        )

        super().__init__(parent)
        self.setStyle(get_ayon_style())
        self.setWindowTitle(
            "Edit View"
            if self._dialog_mode == AYViewEditor.Mode.EDIT
            else "Create New View"
        )
        self.setModal(True)
        self.setContentsMargins(0, 0, 0, 0)

        self._view = view
        self._current_user = current_user
        self._user_list = user_list  # TODO: use to validate and display users
        self._current_project = current_project
        self._allow_studio_scope = bool(allow_studio_scope)
        self._delete_requested = False

        self._build_ui()
        self._load_from_view(view)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the form and button row."""
        root = AYVBoxLayout(self, spacing=8, margin=0)

        form = AYContainer(
            layout=AYContainer.Layout.Form,
            variant=AYContainer.Variants.Default,
            layout_spacing=(16, 16),
            layout_margin=16,
        )

        # view name field — required.
        self._view_name_edit = AYLineEdit(placeholder="View name")
        form.add_row("View name", self._view_name_edit)

        # Scope combo (project / all projects).
        self._scope_combo = AYComboBox()
        scope_items = [
            {
                "text": f"Project - {self._current_project}",
                "short_text": "Project",
            }
        ]
        if self._allow_studio_scope:
            scope_items.append(
                {"text": "All Projects", "short_text": "All Projects"}
            )
        self._scope_combo.update_items(scope_items)
        form.add_row("Scope", self._scope_combo)

        # user access — required.
        self._user_access_edit = AYLineEdit(
            placeholder="Add people or access groups"
        )
        form.add_row("People with access", self._user_access_edit)

        root.addWidget(form)

        # OK / Cancel button row.
        save_btn = AYButton(
            "Save"
            if self._dialog_mode == AYViewEditor.Mode.EDIT
            else "Create",
            variant=AYButton.Variants.Filled,
            icon="check",
        )
        cancel_btn = AYButton("Cancel")
        delete_btn = AYButton(
            "Delete", variant=AYButton.Variants.Danger, icon="delete"
        )
        buttons = QDialogButtonBox()
        if self._dialog_mode == AYViewEditor.Mode.EDIT:
            buttons.addButton(
                save_btn,
                QDialogButtonBox.ButtonRole.AcceptRole,
            )
            buttons.addButton(
                cancel_btn,
                QDialogButtonBox.ButtonRole.RejectRole,
            )
            buttons.addButton(
                delete_btn,
                QDialogButtonBox.ButtonRole.DestructiveRole,
            )
            delete_btn.clicked.connect(self._on_delete)
        else:
            buttons.addButton(
                save_btn,
                QDialogButtonBox.ButtonRole.AcceptRole,
            )
            buttons.addButton(
                cancel_btn,
                QDialogButtonBox.ButtonRole.RejectRole,
            )

        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        buttons.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        form.add_row(buttons)

        self.setMinimumWidth(500)
        self.setContentsMargins(0, 0, 0, 0)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_from_view(self, view: View) -> None:
        """Populate widgets from *view*.

        Args:
            view: The view to copy values from.
        """
        self._view_name_edit.setText(view.label)

        # Scope: select matching item, falling back to project when
        # studio is disallowed but the view is scoped studio.
        if view.scope == Scope.STUDIO and self._allow_studio_scope:
            self._scope_combo.setCurrentIndex(1)
        else:
            self._scope_combo.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Accept handling
    # ------------------------------------------------------------------

    def _on_accept(self) -> None:
        """Validate inputs and accept the dialog.

        Labels must be non-empty; the dialog stays open otherwise.
        """
        label = self._view_name_edit.text().strip()
        if not label:
            self._view_name_edit.setFocus(Qt.FocusReason.OtherFocusReason)
            return

        self.accept()

    def _on_delete(self) -> None:
        """Delete the view and close the dialog."""
        self._delete_requested = True
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mode(self) -> AYViewEditor.Mode:
        """Return the dialog mode: create or edit."""
        return self._dialog_mode

    def delete_requested(self) -> bool:
        """Whether the user requested deletion of the view."""
        return self._delete_requested

    def get_view(self) -> View:
        """Return the edited :class:`View`.

        The original :attr:`View.settings`, :attr:`View.id`,
        :attr:`View.view_type`, :attr:`View.owner`, :attr:`View.access`,
        :attr:`View.position` and :attr:`View.extra` are kept intact;
        only the metadata edited in this dialog is mutated.

        Returns:
            The (mutated) original :class:`View` instance.
        """
        view = self._view
        view.label = self._view_name_edit.text().strip()

        if self._scope_combo.currentIndex() == 1 and self._allow_studio_scope:
            view.scope = Scope.STUDIO
        else:
            view.scope = Scope.PROJECT

        # TODO: IMPLEMENT user access parsing and validation.

        if not view.owner and self._current_user:
            view.owner = self._current_user

        return view


__all__ = ("AYViewEditor",)


if __name__ == "__main__":
    import sys

    from qtpy.QtWidgets import QApplication

    from .data_models import ViewSettings

    app = QApplication(sys.argv)

    view = View(
        id="1234",
        label="Test View",
        view_type="test",
        scope=Scope.PROJECT,
        visibility=Visibility.SHARED,
        access_level=50,
        working=True,
        owner="user",
        settings=ViewSettings(),
        position=0,
        extra={},
    )

    dialog = AYViewEditor(
        view,
        allow_studio_scope=True,
        current_user="Donald",
        current_project="Make_Projects_Great_Again",
    )
    if dialog.exec_():
        if dialog.delete_requested():
            print(">> View deletion requested")
        elif dialog.mode() == AYViewEditor.Mode.CREATE:
            print(">> View created:", dialog.get_view())
        else:
            print(">> View edited:", dialog.get_view())
    else:
        print(">> View rejected")
