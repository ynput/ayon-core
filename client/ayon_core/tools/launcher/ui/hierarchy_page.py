from qtpy import QtWidgets, QtCore

from ayon_core.tools.utils import (
    ProjectsCombobox,
    FoldersWidget,
    TasksWidget,
)
from ayon_core.tools.utils.folders_widget import FoldersFiltersWidget
from ayon_core.ui.components import (
    AYButton,
    AYHBoxLayout,
    AYVBoxLayout,
)

from .workfiles_page import WorkfilesPage
from .recent_actions_widget import RecentActionsButton


class LauncherFoldersWidget(FoldersWidget):
    focused_in = QtCore.Signal()
    # Folder that should be selected is hidden by a filter
    filtered_folder_requested = QtCore.Signal(str)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._folders_view.installEventFilter(self)

    def is_folder_filtered(self, folder_id: str) -> bool:
        """Folder is available but hidden by a filter."""
        index = self._folders_model.get_index_by_id(folder_id)
        if not index.isValid():
            return False
        return not self._folders_proxy_model.mapFromSource(index).isValid()

    def set_selected_folder(self, folder_id):
        if folder_id is not None and self.is_folder_filtered(folder_id):
            # Give a chance to turn off what hides the folder
            self.filtered_folder_requested.emit(folder_id)
        return super().set_selected_folder(folder_id)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusIn:
            self.focused_in.emit()
        return False


class LauncherTasksWidget(TasksWidget):
    focused_in = QtCore.Signal()
    # Task that should be selected is hidden by a filter
    filtered_task_requested = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tasks_view.installEventFilter(self)

    def _set_expected_selection(self):
        expected = self._expected_selection_data
        if (
            expected is not None
            and expected["task_name"] is not None
            and expected["folder_id"] == self._tasks_model.get_last_folder_id()
        ):
            index = self._tasks_model.get_index_by_name(
                expected["task_name"]
            )
            if (
                index.isValid()
                and not self._tasks_proxy_model.mapFromSource(index).isValid()
            ):
                # Give a chance to turn off what hides the task
                self.filtered_task_requested.emit()
        return super()._set_expected_selection()

    def deselect(self):
        sel_model = self._tasks_view.selectionModel()
        sel_model.clearSelection()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusIn:
            self.focused_in.emit()
        return False


class HierarchyPage(QtWidgets.QWidget):
    def __init__(self, controller, parent):
        super().__init__(parent)

        # Header
        header_widget = QtWidgets.QWidget(self)

        btn_back = AYButton(
            icon="arrow_back",
            variant=AYButton.Variants.Surface,
            parent=header_widget,
        )

        projects_combobox = ProjectsCombobox(controller, header_widget)

        refresh_btn = AYButton(
            icon="sync",
            variant=AYButton.Variants.Surface,
            parent=header_widget,
        )

        recent_actions_btn = RecentActionsButton(controller, header_widget)

        header_layout = AYHBoxLayout(header_widget, margin=0, spacing=4)
        header_layout.addWidget(btn_back, 0)
        header_layout.addWidget(projects_combobox, 1)
        header_layout.addWidget(refresh_btn, 0)
        header_layout.addWidget(recent_actions_btn, 0)

        # Body - Folders + Tasks selection
        content_body = QtWidgets.QSplitter(self)
        content_body.setContentsMargins(0, 0, 0, 0)
        content_body.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        content_body.setOrientation(QtCore.Qt.Horizontal)

        # - filters
        filters_widget = FoldersFiltersWidget(self)

        # - Folders widget
        folders_widget = LauncherFoldersWidget(
            controller,
            content_body,
            handle_expected_selection=True,
        )
        folders_widget.set_header_visible(True)
        folders_widget.set_status_column_visible(True)

        # - Tasks widget
        tasks_widget = LauncherTasksWidget(
            controller,
            content_body,
            handle_expected_selection=True,
        )
        tasks_widget.set_status_column_visible(True)

        # - Third page - Workfiles
        workfiles_page = WorkfilesPage(controller, content_body)

        content_body.addWidget(folders_widget)
        content_body.addWidget(tasks_widget)
        content_body.addWidget(workfiles_page)
        content_body.setStretchFactor(0, 120)
        content_body.setStretchFactor(1, 110)
        content_body.setStretchFactor(2, 220)

        main_layout = AYVBoxLayout(self, margin=0, spacing=4)
        main_layout.addWidget(header_widget, 0)
        main_layout.addWidget(filters_widget, 0)
        main_layout.addWidget(content_body, 1)

        btn_back.clicked.connect(self._on_back_clicked)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        filters_widget.text_changed.connect(self._on_filter_text_changed)
        filters_widget.my_tasks_changed.connect(
            self._on_my_tasks_checkbox_state_changed
        )
        folders_widget.focused_in.connect(self._on_folders_focus)
        tasks_widget.focused_in.connect(self._on_tasks_focus)
        folders_widget.filtered_folder_requested.connect(
            self._on_filtered_folder_requested
        )
        tasks_widget.filtered_task_requested.connect(
            self._on_filtered_task_requested
        )

        self._is_visible = False
        self._controller = controller

        self._filters_widget = filters_widget
        self._btn_back = btn_back
        self._projects_combobox = projects_combobox
        self._folders_widget = folders_widget
        self._tasks_widget = tasks_widget
        self._workfiles_page = workfiles_page

        self._project_name = None

        # Post init
        projects_combobox.set_listen_to_selection_change(self._is_visible)

    def set_folders_loading_delay(self, delay: int) -> None:
        """Delay before loading placeholder shows in folders.

        Args:
            delay (int): Delay in milliseconds.

        """
        self._folders_widget.set_loading_delay(delay)

    def set_page_visible(self, visible, project_name=None):
        if self._is_visible == visible:
            return
        self._is_visible = visible
        self._projects_combobox.set_listen_to_selection_change(visible)
        if visible and project_name:
            self._projects_combobox.set_selection(project_name)
        self._project_name = project_name

    def set_selected_project(self, project_name):
        """Show project in the header when it was selected elsewhere.

        The header only tells the backend about projects picked in it, a
        project selected through the projects list while this page is
        already open (e.g. by navigating to a recent action) has to be
        shown there too.
        """
        self._projects_combobox.set_selection(project_name)

    def refresh(self):
        self._folders_widget.refresh()
        self._tasks_widget.refresh()
        self._workfiles_page.refresh()
        # Update my tasks
        self._on_my_tasks_checkbox_state_changed(
            self._filters_widget.is_my_tasks_checked()
        )

    def _on_back_clicked(self):
        self._controller.set_selected_project(None)

    def _on_refresh_clicked(self):
        self._controller.refresh()

    def _on_filter_text_changed(self, text):
        self._folders_widget.set_name_filter(text)

    def _on_my_tasks_checkbox_state_changed(self, enabled: bool) -> None:
        folder_ids = None
        task_ids = None
        if enabled:
            entity_ids = self._controller.get_my_tasks_entity_ids(
                self._project_name
            )
            folder_ids = entity_ids["folder_ids"]
            task_ids = entity_ids["task_ids"]

        self._folders_widget.set_folder_ids_filter(folder_ids)
        self._tasks_widget.set_task_ids_filter(task_ids)

    def _on_filtered_folder_requested(self, folder_id: str) -> None:
        """Turn off only what hides a folder that is navigated to."""
        filters_widget = self._filters_widget
        text = filters_widget.text()
        if text:
            filters_widget.set_text("")
            if not self._folders_widget.is_folder_filtered(folder_id):
                return

        if filters_widget.is_my_tasks_checked():
            filters_widget.set_my_tasks_checked(False)
            # It may have been just 'my tasks' that was hiding the folder
            if text:
                filters_widget.set_text(text)
                if self._folders_widget.is_folder_filtered(folder_id):
                    filters_widget.set_text("")

    def _on_filtered_task_requested(self) -> None:
        # Tasks are only filtered by 'my tasks'
        self._filters_widget.set_my_tasks_checked(False)

    def _on_folders_focus(self):
        self._workfiles_page.deselect()

    def _on_tasks_focus(self):
        self._workfiles_page.deselect()
