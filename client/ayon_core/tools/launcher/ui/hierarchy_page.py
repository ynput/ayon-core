import qtawesome
from qtpy import QtWidgets, QtCore

from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    SquareButton,
    RefreshButton,
    ProjectsCombobox,
    FoldersWidget,
    TasksWidget,
    NiceCheckbox,
)
from ayon_core.tools.utils.lib import checkstate_int_to_enum


class HierarchyPage(QtWidgets.QWidget):
    def __init__(self, controller, parent):
        super().__init__(parent)

        # Header
        header_widget = QtWidgets.QWidget(self)

        btn_back_icon = qtawesome.icon("fa.angle-left", color="white")
        btn_back = SquareButton(header_widget)
        btn_back.setIcon(btn_back_icon)

        projects_combobox = ProjectsCombobox(controller, header_widget)

        my_tasks_label = QtWidgets.QLabel("My tasks", header_widget)
        my_tasks_checkbox = NiceCheckbox(header_widget)
        my_tasks_checkbox.setChecked(False)

        refresh_btn = RefreshButton(header_widget)

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(btn_back, 0)
        header_layout.addWidget(projects_combobox, 1)
        header_layout.addWidget(my_tasks_label, 0)
        header_layout.addWidget(my_tasks_checkbox, 0)
        header_layout.addWidget(refresh_btn, 0)

        # Body - Folders + Tasks selection
        content_body = QtWidgets.QSplitter(self)
        content_body.setContentsMargins(0, 0, 0, 0)
        content_body.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        content_body.setOrientation(QtCore.Qt.Horizontal)

        # - Folders widget with filter
        folders_wrapper = QtWidgets.QWidget(content_body)

        folders_filter_text = PlaceholderLineEdit(folders_wrapper)
        folders_filter_text.setPlaceholderText("Filter folders...")

        folders_widget = FoldersWidget(controller, folders_wrapper)

        folders_wrapper_layout = QtWidgets.QVBoxLayout(folders_wrapper)
        folders_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        folders_wrapper_layout.addWidget(folders_filter_text, 0)
        folders_wrapper_layout.addWidget(folders_widget, 1)

        # - Tasks widget
        tasks_widget = TasksWidget(controller, content_body)

        content_body.addWidget(folders_wrapper)
        content_body.addWidget(tasks_widget)
        content_body.setStretchFactor(0, 100)
        content_body.setStretchFactor(1, 65)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(header_widget, 0)
        main_layout.addWidget(content_body, 1)

        btn_back.clicked.connect(self._on_back_clicked)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        folders_filter_text.textChanged.connect(self._on_filter_text_changed)
        my_tasks_checkbox.stateChanged.connect(
            self._on_my_tasks_checkbox_state_changed
        )

        self._is_visible = False
        self._controller = controller

        self._btn_back = btn_back
        self._projects_combobox = projects_combobox
        self._my_tasks_checkbox = my_tasks_checkbox
        self._folders_widget = folders_widget
        self._tasks_widget = tasks_widget

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
        self._on_my_tasks_checkbox_state_changed(
            self._my_tasks_checkbox.checkState()
        )

    def _on_back_clicked(self):
        self._controller.set_selected_project(None)

    def _on_refresh_clicked(self):
        self._controller.refresh()

    def _on_filter_text_changed(self, text):
        self._folders_widget.set_name_filter(text)

    def _on_my_tasks_checkbox_state_changed(self, state):
        folder_ids = None
        task_ids = None
        state = checkstate_int_to_enum(state)
        if state == QtCore.Qt.Checked:
            entity_ids = self._controller.get_my_tasks_entity_ids(
                self._project_name
            )
            folder_ids = entity_ids["folder_ids"]
            task_ids = entity_ids["task_ids"]
        self._folders_widget.set_folder_ids_filter(folder_ids)
        self._tasks_widget.set_task_ids_filter(task_ids)
