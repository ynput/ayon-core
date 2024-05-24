from qtpy import QtWidgets, QtCore

from ayon_core.lib.events import QueuedEventSystem
from ayon_core.tools.utils import PlaceholderLineEdit, GoToCurrentButton

from ayon_core.tools.common_models import HierarchyExpectedSelection
from ayon_core.tools.utils import FoldersWidget, TasksWidget


class CreateSelectionModel(object):
    """Model handling selection changes.

    Triggering events:
    - "selection.project.changed"
    - "selection.folder.changed"
    - "selection.task.changed"
    """

    event_source = "publisher.create.selection.model"

    def __init__(self, controller):
        self._controller = controller

        self._project_name = None
        self._folder_id = None
        self._task_name = None
        self._task_id = None

    def get_selected_project_name(self):
        return self._project_name

    def set_selected_project(self, project_name):
        if project_name == self._project_name:
            return

        self._project_name = project_name
        self._controller.emit_event(
            "selection.project.changed",
            {"project_name": project_name},
            self.event_source
        )

    def get_selected_folder_id(self):
        return self._folder_id

    def set_selected_folder(self, folder_id):
        if folder_id == self._folder_id:
            return

        self._folder_id = folder_id
        self._controller.emit_event(
            "selection.folder.changed",
            {
                "project_name": self._project_name,
                "folder_id": folder_id,
            },
            self.event_source
        )

    def get_selected_task_name(self):
        return self._task_name

    def get_selected_task_id(self):
        return self._task_id

    def set_selected_task(self, task_id, task_name):
        if task_id == self._task_id:
            return

        self._task_name = task_name
        self._task_id = task_id
        self._controller.emit_event(
            "selection.task.changed",
            {
                "project_name": self._project_name,
                "folder_id": self._folder_id,
                "task_name": task_name,
                "task_id": task_id,
            },
            self.event_source
        )


class CreateHierarchyController:
    """Controller for hierarchy widgets.

    Helper for handling hierarchy widgets in create tab. It handles selection
    of folder and task to properly propagate it to other widgets.

    At the same time handles expected selection so can pre-select folder and
    task based on current context.

    Args:
        controller (PublisherController): Publisher controller.

    """
    def __init__(self, controller):
        self._event_system = QueuedEventSystem()
        self._controller = controller
        self._selection_model = CreateSelectionModel(self)
        self._expected_selection = HierarchyExpectedSelection(
            self, handle_project=False
        )

    # Events system
    @property
    def event_system(self):
        return self._event_system

    def emit_event(self, topic, data=None, source=None):
        """Use implemented event system to trigger event."""

        if data is None:
            data = {}
        self.event_system.emit(topic, data, source)

    def register_event_callback(self, topic, callback):
        self.event_system.add_callback(topic, callback)

    def get_project_name(self):
        return self._controller.project_name

    def get_folder_items(self, project_name, sender=None):
        return self._controller.get_folder_items(project_name, sender)

    def get_task_items(self, project_name, folder_id, sender=None):
        return self._controller.get_task_items(
            project_name, folder_id, sender
        )

    # Selection model
    def set_selected_project(self, project_name):
        self._selection_model.set_selected_project(project_name)

    def set_selected_folder(self, folder_id):
        self._selection_model.set_selected_folder(folder_id)

    def set_selected_task(self, task_id, task_name):
        self._selection_model.set_selected_task(task_id, task_name)

    # Expected selection
    def get_expected_selection_data(self):
        return self._expected_selection.get_expected_selection_data()

    def set_expected_selection(self, project_name, folder_id, task_name):
        self._expected_selection.set_expected_selection(
            project_name, folder_id, task_name
        )

    def expected_folder_selected(self, folder_id):
        self._expected_selection.expected_folder_selected(folder_id)

    def expected_task_selected(self, folder_id, task_name):
        self._expected_selection.expected_task_selected(folder_id, task_name)


class CreateContextWidget(QtWidgets.QWidget):
    folder_changed = QtCore.Signal()
    task_changed = QtCore.Signal()

    def __init__(self, controller, parent):
        super(CreateContextWidget, self).__init__(parent)

        self._controller = controller
        self._enabled = True
        self._last_project_name = None
        self._last_folder_id = None
        self._last_selected_task_name = None

        headers_widget = QtWidgets.QWidget(self)

        folder_filter_input = PlaceholderLineEdit(headers_widget)
        folder_filter_input.setPlaceholderText("Filter folders..")

        current_context_btn = GoToCurrentButton(headers_widget)
        current_context_btn.setToolTip("Go to current context")
        current_context_btn.setVisible(False)

        headers_layout = QtWidgets.QHBoxLayout(headers_widget)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        headers_layout.addWidget(folder_filter_input, 1)
        headers_layout.addWidget(current_context_btn, 0)

        hierarchy_controller = CreateHierarchyController(controller)

        folders_widget = FoldersWidget(
            hierarchy_controller, self, handle_expected_selection=True
        )
        folders_widget.set_deselectable(True)

        tasks_widget = TasksWidget(
            hierarchy_controller, self, handle_expected_selection=True
        )

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(headers_widget, 0)
        main_layout.addWidget(folders_widget, 2)
        main_layout.addWidget(tasks_widget, 1)

        folders_widget.selection_changed.connect(self._on_folder_change)
        tasks_widget.selection_changed.connect(self._on_task_change)
        current_context_btn.clicked.connect(self._on_current_context_click)
        folder_filter_input.textChanged.connect(self._on_folder_filter_change)

        self._folder_filter_input = folder_filter_input
        self._current_context_btn = current_context_btn
        self._folders_widget = folders_widget
        self._tasks_widget = tasks_widget
        self._hierarchy_controller = hierarchy_controller

    def get_selected_folder_id(self):
        return self._folders_widget.get_selected_folder_id()

    def get_selected_folder_path(self):
        return self._folders_widget.get_selected_folder_path()

    def get_selected_task_name(self):
        return self._tasks_widget.get_selected_task_name()

    def get_selected_task_type(self):
        return self._tasks_widget.get_selected_task_type()

    def update_current_context_btn(self):
        # Hide set current folder if there is no one
        folder_path = self._controller.current_folder_path
        self._current_context_btn.setVisible(bool(folder_path))

    def set_selected_context(self, folder_id, task_name):
        self._hierarchy_controller.set_expected_selection(
            self._controller.project_name,
            folder_id,
            task_name
        )

    def is_enabled(self):
        return self._enabled

    def set_enabled(self, enabled):
        if enabled is self._enabled:
            return

        self.setEnabled(enabled)
        self._enabled = enabled

        if not enabled:
            self._last_folder_id = self.get_selected_folder_id()
            self._folders_widget.set_selected_folder(None)
            last_selected_task_name = self.get_selected_task_name()
            if last_selected_task_name:
                self._last_selected_task_name = last_selected_task_name
            self._clear_selection()

        elif self._last_selected_task_name is not None:
            self._hierarchy_controller.set_expected_selection(
                self._last_project_name,
                self._last_folder_id,
                self._last_selected_task_name
            )

    def refresh(self):
        self._last_project_name = self._controller.project_name
        folder_id = self._last_folder_id
        task_name = self._last_selected_task_name
        if folder_id is None:
            folder_path = self._controller.current_folder_path
            folder_id = self._controller.get_folder_id_from_path(folder_path)
            task_name = self._controller.current_task_name
        self._hierarchy_controller.set_selected_project(
            self._last_project_name
        )
        self._folders_widget.set_project_name(self._last_project_name)
        self._hierarchy_controller.set_expected_selection(
            self._last_project_name, folder_id, task_name
        )

    def _clear_selection(self):
        self._folders_widget.set_selected_folder(None)

    def _on_folder_change(self):
        self.folder_changed.emit()

    def _on_task_change(self):
        self.task_changed.emit()

    def _on_current_context_click(self):
        folder_path = self._controller.current_folder_path
        task_name = self._controller.current_task_name
        folder_id = self._controller.get_folder_id_from_path(folder_path)
        self._hierarchy_controller.set_expected_selection(
            self._last_project_name, folder_id, task_name
        )

    def _on_folder_filter_change(self, text):
        self._folders_widget.set_name_filter(text)
