from typing import Optional, Callable

import ayon_api
from qtpy import QtCore, QtWidgets, QtGui

from ayon_core.tools.utils import get_qt_icon, DeselectableTreeView
from ayon_core.tools.launcher.abstract import AbstractLauncherFrontEnd

VERSION_ROLE = QtCore.Qt.UserRole + 1
WORKFILE_ID_ROLE = QtCore.Qt.UserRole + 2
PUBLISHED_ROLE = QtCore.Qt.UserRole + 3


class WorkfilesModel(QtGui.QStandardItemModel):
    """Qt model for listing saved or published launcher workfiles."""

    refreshed = QtCore.Signal()

    def __init__(
        self,
        controller: AbstractLauncherFrontEnd,
        show_published_enabled: Callable[[], bool],
        show_local_only_enabled: Callable[[], bool],
    ) -> None:
        super().__init__()

        self.setColumnCount(1)
        self.setHeaderData(0, QtCore.Qt.Horizontal, "Workfiles")

        controller.register_event_callback(
            "selection.project.changed",
            self._on_selection_project_changed,
        )
        controller.register_event_callback(
            "selection.folder.changed",
            self._on_selection_folder_changed,
        )
        controller.register_event_callback(
            "selection.task.changed",
            self._on_selection_task_changed,
        )

        self._controller = controller
        self._show_published_enabled = show_published_enabled
        self._show_local_only_enabled = show_local_only_enabled
        self._selected_project_name = None
        self._selected_folder_id = None
        self._selected_task_id = None

        self._transparent_icon = None

        self._cached_icons = {}

    def refresh(self) -> None:
        """Refresh workfile rows for the currently selected context."""
        root_item = self.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        if self._show_published_enabled():
            workfile_items = self._controller.get_published_workfile_items(
                self._selected_project_name,
                self._selected_folder_id,
                self._selected_task_id,
            )
        else:
            workfile_items = self._controller.get_workfile_items(
                self._selected_project_name, self._selected_task_id
            )
        new_items = []
        for workfile_item in workfile_items:
            if (
                not self._show_published_enabled()
                and self._show_local_only_enabled()
                and not workfile_item.exists
            ):
                continue
            icon = self._get_icon(workfile_item.icon)
            item = QtGui.QStandardItem(workfile_item.filename)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(workfile_item.version, VERSION_ROLE)
            item.setData(workfile_item.workfile_id, WORKFILE_ID_ROLE)
            item.setData(workfile_item.published, PUBLISHED_ROLE)
            flags = QtCore.Qt.NoItemFlags
            if workfile_item.exists:
                flags = QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable
            item.setFlags(flags)
            new_items.append(item)

        if not new_items:
            title = "< No workfiles >"
            if not self._selected_project_name:
                title = "< Select a project >"
            elif not self._selected_folder_id:
                title = "< Select a folder >"
            elif not self._selected_task_id:
                title = "< Select a task >"
            item = QtGui.QStandardItem(title)
            item.setFlags(QtCore.Qt.NoItemFlags)
            new_items.append(item)
        root_item.appendRows(new_items)

        self.refreshed.emit()

    def _on_selection_project_changed(self, event: dict[str, str]) -> None:
        """React to project selection change and refresh workfiles."""
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = None
        self._selected_task_id = None
        self.refresh()

    def _on_selection_folder_changed(self, event: dict[str, str]) -> None:
        """React to folder selection change and refresh workfiles."""
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = None
        self.refresh()

    def _on_selection_task_changed(self, event: dict[str, str]) -> None:
        """React to task selection change and refresh workfiles."""
        self._selected_project_name = event["project_name"]
        self._selected_folder_id = event["folder_id"]
        self._selected_task_id = event["task_id"]
        self.refresh()

    def _get_transparent_icon(self) -> QtGui.QIcon:
        if self._transparent_icon is None:
            self._transparent_icon = get_qt_icon({
                "type": "transparent", "size": 256
            })
        return self._transparent_icon

    def _get_icon(self, icon_url: Optional[str]) -> QtGui.QIcon:
        if icon_url is None:
            return self._get_transparent_icon()
        icon = self._cached_icons.get(icon_url)
        if icon is not None:
            return icon

        base_url = ayon_api.get_base_url()
        if icon_url.startswith(base_url):
            icon_def = {
                "type": "ayon_url",
                "url": icon_url[len(base_url) + 1:],
            }
        else:
            icon_def = {
                "type": "url",
                "url": icon_url,
            }

        icon = get_qt_icon(icon_def)
        if icon is None:
            icon = self._get_transparent_icon()
        self._cached_icons[icon_url] = icon
        return icon


class WorkfilesView(DeselectableTreeView):
    """Tree view with hidden branch decoration for single-column list."""

    def drawBranches(self, painter, rect, index):
        return


class WorkfilesPage(QtWidgets.QWidget):
    """Workfiles section with published/local filtering controls."""

    def __init__(
        self,
        controller: AbstractLauncherFrontEnd,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        show_published_checkbox = QtWidgets.QCheckBox("Published", self)
        show_local_only_checkbox = QtWidgets.QCheckBox("Local only", self)
        workfiles_view = WorkfilesView(self)
        workfiles_view.setIndentation(0)
        workfiles_model = WorkfilesModel(
            controller,
            show_published_checkbox.isChecked,
            show_local_only_checkbox.isChecked,
        )
        workfiles_proxy = QtCore.QSortFilterProxyModel()
        workfiles_proxy.setSourceModel(workfiles_model)

        workfiles_view.setModel(workfiles_proxy)

        # When published is enabled, local-only filtering does not apply.
        show_local_only_checkbox.setEnabled(
            not show_published_checkbox.isChecked()
        )

        toggles_row = QtWidgets.QHBoxLayout()
        toggles_row.addWidget(show_published_checkbox)
        toggles_row.addWidget(show_local_only_checkbox)
        toggles_row.addStretch()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(toggles_row, 0)
        layout.addWidget(workfiles_view, 1)

        workfiles_view.selectionModel().selectionChanged.connect(
            self._on_selection_changed
        )
        workfiles_model.refreshed.connect(self._on_refresh)
        show_published_checkbox.toggled.connect(self._on_show_published_toggle)
        show_local_only_checkbox.toggled.connect(self._on_show_local_only_toggle)
        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_changed,
        )

        self._controller = controller
        self._show_published_checkbox = show_published_checkbox
        self._show_local_only_checkbox = show_local_only_checkbox
        self._workfiles_view = workfiles_view
        self._workfiles_model = workfiles_model
        self._workfiles_proxy = workfiles_proxy

    def refresh(self) -> None:
        """Refresh the workfiles model."""
        self._workfiles_model.refresh()

    def deselect(self) -> None:
        """Clear current item selection in workfiles list."""
        sel_model = self._workfiles_view.selectionModel()
        sel_model.clearSelection()

    def _on_refresh(self) -> None:
        """Apply sorting after model data refresh."""
        self._workfiles_proxy.sort(0, QtCore.Qt.DescendingOrder)

    def _on_selection_changed(self, selected, _deselected) -> None:
        """Update selected workfile from current view selection."""
        workfile_id = None
        published = False
        for index in selected.indexes():
            workfile_id = index.data(WORKFILE_ID_ROLE)
            published = bool(index.data(PUBLISHED_ROLE))
        self._controller.set_selected_workfile(workfile_id, published)

    def _on_show_published_toggle(self, checked: bool) -> None:
        """Disable local-only toggle when published mode is enabled."""
        self._show_local_only_checkbox.setEnabled(not checked)
        self._workfiles_model.refresh()

    def _on_show_local_only_toggle(self, _checked: bool) -> None:
        """Refresh list after local-only toggle change."""
        self._workfiles_model.refresh()

    def _on_project_changed(self, event: dict[str, str]) -> None:
        """Apply project defaults for local-only toggle and refresh list."""
        project_name = event["project_name"]
        show_local_only = (
            self._controller.get_show_local_workfiles_only_default(
                project_name
            )
        )
        with QtCore.QSignalBlocker(self._show_local_only_checkbox):
            self._show_local_only_checkbox.setChecked(show_local_only)
        self._workfiles_model.refresh()
