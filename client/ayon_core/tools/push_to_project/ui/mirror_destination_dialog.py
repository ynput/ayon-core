"""Modal dialog: destination project, parent folder, mirror options."""

from __future__ import annotations

from typing import Optional, Tuple

from qtpy import QtWidgets, QtGui

from ayon_core.style import get_app_icon_path, load_stylesheet
from ayon_core.tools.push_to_project.control import PushToContextController
from ayon_core.tools.utils import (
    FoldersWidget,
    NiceCheckbox,
    ProjectsCombobox,
    SeparatorWidget,
)


class MirrorFoldersDestinationDialog(QtWidgets.QDialog):
    """Pick destination project, optional parent folder, and mirror flags."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mirror folders to project")
        self.setWindowIcon(QtGui.QIcon(get_app_icon_path()))
        self.setMinimumSize(560, 480)

        self._controller = PushToContextController()

        library_header = QtWidgets.QWidget(self)
        library_only_label = QtWidgets.QLabel(
            "Show only libraries", library_header
        )
        library_only_checkbox = NiceCheckbox(False, parent=library_header)
        library_header_layout = QtWidgets.QHBoxLayout(library_header)
        library_header_layout.setContentsMargins(0, 0, 0, 0)
        library_header_layout.addStretch(1)
        library_header_layout.addWidget(library_only_label, 0)
        library_header_layout.addWidget(library_only_checkbox, 0)

        projects_combobox = ProjectsCombobox(self._controller, self)
        projects_combobox.set_select_item_visible(True)
        projects_combobox.set_standard_filter_enabled(
            library_only_checkbox.isChecked()
        )

        dest_folders_label = QtWidgets.QLabel(
            "Folders in destination project",
            self,
        )

        folders_widget = FoldersWidget(self._controller, self)
        folders_widget.setMinimumHeight(160)
        folders_widget.set_deselectable(True)

        mirror_upstream_cb = NiceCheckbox(True, parent=self)
        mirror_upstream_label = QtWidgets.QLabel(
            "Recreate upstream folder hierarchy under destination",
            self,
        )
        mirror_upstream_label.setWordWrap(True)
        mirror_upstream_row = QtWidgets.QHBoxLayout()
        mirror_upstream_row.setContentsMargins(0, 0, 0, 0)
        mirror_upstream_row.addWidget(mirror_upstream_cb, 0)
        mirror_upstream_row.addWidget(mirror_upstream_label, 1)

        mirror_upstream_hint = QtWidgets.QLabel(
            "When enabled, parent folders from the source path are created "
            "under the destination so branches keep their depth. When off, "
            "only folders from the Loader selection (and optional children) "
            "are mirrored under the destination parent.",
            self,
        )
        mirror_upstream_hint.setWordWrap(True)

        include_tasks_cb = NiceCheckbox(True, parent=self)
        include_tasks_label = QtWidgets.QLabel("Include tasks", self)
        include_tasks_row = QtWidgets.QHBoxLayout()
        include_tasks_row.setContentsMargins(0, 0, 0, 0)
        include_tasks_row.addWidget(include_tasks_cb, 0)
        include_tasks_row.addWidget(include_tasks_label, 1)

        recursive_cb = NiceCheckbox(True, parent=self)
        recursive_label = QtWidgets.QLabel(
            "Mirror child folders (recursive)",
            self,
        )
        recursive_label.setWordWrap(True)
        recursive_row = QtWidgets.QHBoxLayout()
        recursive_row.setContentsMargins(0, 0, 0, 0)
        recursive_row.addWidget(recursive_cb, 0)
        recursive_row.addWidget(recursive_label, 1)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(library_header, 0)
        layout.addWidget(QtWidgets.QLabel("Destination project", self))
        layout.addWidget(projects_combobox, 0)
        layout.addWidget(dest_folders_label, 0)
        layout.addWidget(folders_widget, 1)
        layout.addLayout(mirror_upstream_row)
        layout.addWidget(mirror_upstream_hint, 0)
        layout.addLayout(include_tasks_row)
        layout.addLayout(recursive_row)
        layout.addWidget(SeparatorWidget(parent=self))
        layout.addWidget(button_box)

        mirror_upstream_cb.setToolTip(
            "Include ancestors of each selected source folder up to the "
            "project root in the mirror operation."
        )

        library_only_checkbox.stateChanged.connect(self._on_library_only_change)

        self._projects_combobox = projects_combobox
        self._folders_widget = folders_widget
        self._library_only_checkbox = library_only_checkbox
        self._mirror_upstream_cb = mirror_upstream_cb
        self._include_tasks_cb = include_tasks_cb
        self._recursive_cb = recursive_cb
        self._first_show = True

        projects_combobox.refreshed.connect(self._sync_destination_folder_tree)
        projects_combobox.selection_changed.connect(
            self._sync_destination_folder_tree
        )

    def _sync_destination_folder_tree(self) -> None:
        """Keep folder tree in sync with the combobox project selection."""
        project_name = self._projects_combobox.get_selected_project_name()
        self._controller.set_selected_project(project_name)

    def _on_library_only_change(self) -> None:
        self._projects_combobox.set_standard_filter_enabled(
            self._library_only_checkbox.isChecked()
        )
        self._projects_combobox.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(load_stylesheet())
        self._projects_combobox.refresh()

    def get_values(
        self,
    ) -> Tuple[
        Optional[str],
        Optional[str],
        bool,
        bool,
        bool,
    ]:
        """Return dest project, dest parent folder id, tasks, recursive, upstream."""
        return (
            self._controller.get_selected_project_name(),
            self._controller.get_selected_folder_id(),
            self._include_tasks_cb.isChecked(),
            self._recursive_cb.isChecked(),
            self._mirror_upstream_cb.isChecked(),
        )
