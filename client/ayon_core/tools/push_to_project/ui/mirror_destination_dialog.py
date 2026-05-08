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
        self.setMinimumSize(520, 420)

        self._controller = PushToContextController()

        projects_combobox = ProjectsCombobox(self._controller, self)
        projects_combobox.set_select_item_visible(True)
        projects_combobox.set_standard_filter_enabled(True)

        folders_widget = FoldersWidget(self._controller, self)
        folders_widget.set_deselectable(True)

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
        layout.addWidget(QtWidgets.QLabel("Destination project", self))
        layout.addWidget(projects_combobox, 0)
        layout.addWidget(
            QtWidgets.QLabel(
                "Parent folder (optional — mirrors under project root if none)",
                self,
            )
        )
        layout.addWidget(folders_widget, 1)
        layout.addLayout(include_tasks_row)
        layout.addLayout(recursive_row)
        layout.addWidget(SeparatorWidget(parent=self))
        layout.addWidget(button_box)

        self._projects_combobox = projects_combobox
        self._folders_widget = folders_widget
        self._include_tasks_cb = include_tasks_cb
        self._recursive_cb = recursive_cb
        self._first_show = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(load_stylesheet())
        self._projects_combobox.refresh()

    def get_values(
        self,
    ) -> Tuple[Optional[str], Optional[str], bool, bool]:
        """Return dest project, dest parent folder id, tasks, recursive."""
        return (
            self._controller.get_selected_project_name(),
            self._controller.get_selected_folder_id(),
            self._include_tasks_cb.isChecked(),
            self._recursive_cb.isChecked(),
        )
