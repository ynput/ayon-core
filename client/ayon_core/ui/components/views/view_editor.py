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
    QWidget,
    QHBoxLayout,
    QLabel,
)

from ...style_types import get_ayon_style
from ..buttons import AYButton
from ..combo_box import AYComboBox
from ..container import AYContainer
from ..label import AYLabel
from ..layouts import AYVBoxLayout
from ..line_edit import AYLineEdit
from .data_models import Scope, View, Visibility

log = logging.getLogger(__name__)

# Access level constants
ACCESS_LEVELS = {
    0: "No access",
    10: "Viewer",
    20: "Editor",
    30: "Admin",
}
ACCESS_LEVEL_VALUES = list(ACCESS_LEVELS.keys())


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
        usernames_and_groups: dict[str, list[str]] | None = None,
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
        self.usernames_and_groups = usernames_and_groups or {"users": [], "groups": []}
        self._current_project = current_project
        self._allow_studio_scope = bool(allow_studio_scope)
        self._delete_requested = False

        # Access control state: {key: access_level} where key is "user:name" or "group:name"
        self._access_dict: dict[str, int] = {}
        # Stores row widgets by access key
        self._access_row_widgets: dict[str, QWidget] = {}

        self._build_ui()
        self._load_from_view(view)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Create the form and button row."""
        root = AYVBoxLayout(self, spacing=0, margin=0)

        self._form = AYContainer(
            layout=AYContainer.Layout.Form,
            variant=AYContainer.Variants.Default,
            layout_spacing=(16, 16),
            layout_margin=16,
        )

        # view name field — required.
        self._view_name_edit = AYLineEdit(placeholder="View name")
        self._form.add_row("View name", self._view_name_edit)

        # Scope combo (project / all projects).
        self._scope_combo = AYComboBox()
        scope_items = [
            {
                "text": f"Project - {self._current_project}",
                "short_text": "Project",
            }
        ]
        #TODO: its not working as expected, need to check
        if self._allow_studio_scope:
            scope_items.append(
                {"text": "All Projects", "short_text": "All Projects"}
            )
        self._scope_combo.update_items(scope_items)
        self._form.add_row("Scope", self._scope_combo)

        # User/group selector dropdown
        self._user_selector = AYComboBox()
        self._update_user_dropdown()
        self._form.add_row(
            "Add people or access groups",
            self._user_selector
        )
        self._user_selector.activated.connect(self._on_user_selected)

        root.addWidget(self._form)
        root.addStretch()

        # Button row - positioned at bottom with Delete on left, Save on right
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(16, 16, 16, 16)
        button_layout.setSpacing(8)

        save_btn = AYButton(
            "Save"
            if self._dialog_mode == AYViewEditor.Mode.EDIT
            else "Create",
            variant=AYButton.Variants.Filled,
            icon="check",
        )
        delete_btn = AYButton(
            "Delete", variant=AYButton.Variants.Danger, icon="delete"
        )

        if self._dialog_mode == AYViewEditor.Mode.EDIT:
            # Delete on left, stretch, Save on right
            button_layout.addWidget(delete_btn)
            button_layout.addStretch()
            button_layout.addWidget(save_btn)
            delete_btn.clicked.connect(self._on_delete)
        else:
            # Just Save on right for create mode
            button_layout.addStretch()
            button_layout.addWidget(save_btn)

        save_btn.clicked.connect(self._on_accept)

        root.addWidget(button_container)

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

        # Load access data from view
        self._access_dict = dict(view.access) if view.access else {}
        self._populate_access_rows()

    def _update_user_dropdown(self) -> None:
        #TODO: update replace user: and group: with avatars
        """Update dropdown to show only users/groups not yet added."""
        added_keys = set(self._access_dict.keys())
 
        items = []
        users = self.usernames_and_groups.get("users", [])
        groups = self.usernames_and_groups.get("groups", [])
        if users:
            for user in users:
                user_key = f"user:{user}"
                if user_key not in added_keys:
                    items.append({"text": f"{user_key}"})
 
        for group in groups:
            group_key = f"group:{group}"
            if group_key not in added_keys:
                items.append({"text": f"{group_key}"})
        if not items:
            items.append({"text": "No more users to add"})

        self._user_selector.update_items(items)

    def _on_user_selected(self, index: int) -> None:
        """Handle user selection from dropdown."""
        selected_text = self._user_selector.itemText(index).strip()
        if not selected_text or selected_text == "No more users to add":
            return

        access_key = selected_text

        self._add_access_row(access_key, 10)  # Default to Viewer access
        self._update_user_dropdown()

    def _add_access_row(self, key: str, access_level: int) -> None:
        """Add an access control row for the given user/group.

        Args:
            key: The access key (e.g., "user:name" or "group:name").
            access_level: The access level (0, 10, 20, or 30).
        """
        if key in self._access_dict:
            return  # Already exists

        self._access_dict[key] = access_level
        self._populate_access_rows()

    def _remove_access_row(self, key: str) -> None:
        """Remove an access control row.

        Args:
            key: The access key to remove.
        """
        if key not in self._access_dict:
            return

        del self._access_dict[key]

        self._populate_access_rows()
        self._update_user_dropdown()

    def _render_dynamic_access_row(self, key: str, access_level: int) -> None:
        """Render a single dynamic access row without mutating _access_dict."""
        row_widget = QWidget(self._form)
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(8)

        access_combo = AYComboBox()
        access_items = [{"text": ACCESS_LEVELS[level]} for level in ACCESS_LEVEL_VALUES]
        access_combo.update_items(access_items)

        if access_level not in ACCESS_LEVEL_VALUES:
            access_level = 10
        access_combo.setCurrentIndex(ACCESS_LEVEL_VALUES.index(access_level))

        def on_access_changed(idx: int) -> None:
            self._access_dict[key] = ACCESS_LEVEL_VALUES[idx]

        access_combo.currentIndexChanged.connect(on_access_changed)
        row_layout.addWidget(access_combo)

        remove_btn = AYButton("", icon="close")
        remove_btn.clicked.connect(lambda: self._remove_access_row(key))
        row_layout.addWidget(remove_btn)
        row_layout.addStretch()

        self._form.add_row(key, row_widget)
        self._access_row_widgets[key] = row_widget

    def _populate_access_rows(self) -> None:
        """Populate access control rows from _access_dict."""
        # Clear existing rows
        for widget in self._access_row_widgets.values():
            widget.deleteLater()
        self._access_row_widgets.clear()

        # Clear access-related rows that were added dynamically
        # (Owner, Everyone, and user/group rows)
        layout = self._form.layout()
        while layout.rowCount() > 3:
            layout.removeRow(3)

        # Add Owner row
        owner_name = self._view.owner or self._current_user or "-"
        self._form.add_row("Owner", QLabel(owner_name))

        # Add Everyone row
        everyone_combo = AYComboBox()
        access_items = [{"text": ACCESS_LEVELS[level]} for level in ACCESS_LEVEL_VALUES]
        everyone_combo.update_items(access_items)

        everyone_level = self._access_dict.get("__everyone__", 0)
        if everyone_level not in ACCESS_LEVEL_VALUES:
            everyone_level = 0
        everyone_combo.setCurrentIndex(ACCESS_LEVEL_VALUES.index(everyone_level))
        self._access_dict["__everyone__"] = everyone_level

        def on_everyone_changed(idx: int) -> None:
            self._access_dict["__everyone__"] = ACCESS_LEVEL_VALUES[idx]

        everyone_combo.currentIndexChanged.connect(on_everyone_changed)
        self._form.add_row("Everyone", everyone_combo)

        # Add dynamic user/group rows
        for key in sorted(self._access_dict.keys()):
            if key == "__everyone__":
                continue
            self._render_dynamic_access_row(key, int(self._access_dict[key]))

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

        view.access = dict(self._access_dict)

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
        visibility=Visibility.PUBLIC,
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
