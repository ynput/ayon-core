import qtawesome
from qtpy import QtWidgets, QtCore

from ayon_core.tools.utils import (
    SquareButton,
    RefreshButton,
    ProjectsCombobox,
    FoldersWidget,
    TasksWidget,
)
from ayon_core.tools.utils.folders_widget import FoldersFiltersWidget

from .workfiles_page import WorkfilesPage


class LauncherFoldersWidget(FoldersWidget):
    focused_in = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._folders_view.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FocusIn:
            self.focused_in.emit()
        return False


class LauncherTasksWidget(TasksWidget):
    focused_in = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tasks_view.installEventFilter(self)

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

        btn_back_icon = qtawesome.icon("fa.angle-left", color="white")
        btn_back = SquareButton(header_widget)
        btn_back.setIcon(btn_back_icon)

        projects_combobox = ProjectsCombobox(controller, header_widget)

        refresh_btn = RefreshButton(header_widget)

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(btn_back, 0)
        header_layout.addWidget(projects_combobox, 1)
        header_layout.addWidget(refresh_btn, 0)

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
        folders_widget = LauncherFoldersWidget(controller, content_body)
        folders_widget.set_header_visible(True)
        folders_widget.set_deselectable(True)

        # - Tasks widget
        tasks_widget = LauncherTasksWidget(controller, content_body)

        # - Third page - Workfiles
        workfiles_page = WorkfilesPage(controller, content_body)

        content_body.addWidget(folders_widget)
        content_body.addWidget(tasks_widget)
        content_body.addWidget(workfiles_page)
        content_body.setStretchFactor(0, 120)
        content_body.setStretchFactor(1, 85)
        content_body.setStretchFactor(2, 220)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
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

        self._is_visible = False
        self._controller = controller

        self._btn_back = btn_back
        self._projects_combobox = projects_combobox
        self._folders_widget = folders_widget
        self._tasks_widget = tasks_widget
        self._workfiles_page = workfiles_page

        self._project_name = None

        # Post init
        projects_combobox.set_listen_to_selection_change(self._is_visible)

    def set_page_visible(self, visible, project_name=None):
        if self._is_visible == visible:
            return
        self._is_visible = visible
        self._projects_combobox.set_listen_to_selection_change(visible)
        if visible and project_name:
            self._projects_combobox.set_selection(project_name)
        self._project_name = project_name

    def refresh(self):
        self._folders_widget.refresh()
        self._tasks_widget.refresh()
        self._workfiles_page.refresh()

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

    def _on_folders_focus(self):
        self._workfiles_page.deselect()

    def _on_tasks_focus(self):
        self._workfiles_page.deselect()
