from __future__ import annotations


class SelectionModel(object):
    """Model handling selection changes.

    Triggering events:
    - "selection.project.changed"
    - "selection.folders.changed"
    - "selection.versions.changed"
    """

    event_source = "selection.model"

    def __init__(self, controller):
        self._controller = controller

        self._project_name = None
        self._folder_ids = set()
        self._task_ids = set()
        self._version_ids = set()
        self._version_selection_rows: list = []
        self._representation_ids = set()

    def get_selected_project_name(self):
        return self._project_name

    def set_selected_project(self, project_name):
        if self._project_name == project_name:
            return

        self._project_name = project_name
        self._controller.emit_event(
            "selection.project.changed",
            {"project_name": self._project_name},
            self.event_source,
        )

    def get_selected_folder_ids(self):
        return self._folder_ids

    def set_selected_folders(self, folder_ids):
        if folder_ids == self._folder_ids:
            return

        self._folder_ids = folder_ids
        self._controller.emit_event(
            "selection.folders.changed",
            {
                "project_name": self._project_name,
                "folder_ids": folder_ids,
            },
            self.event_source,
        )

    def get_selected_task_ids(self):
        return self._task_ids

    def set_selected_tasks(self, task_ids):
        if task_ids == self._task_ids:
            return

        self._task_ids = task_ids
        self._controller.emit_event(
            "selection.tasks.changed",
            {
                "project_name": self._project_name,
                "task_ids": task_ids,
            },
            self.event_source,
        )

    def get_selected_version_ids(self):
        return self._version_ids

    def set_selected_versions(self, version_ids, selection_rows=None):
        # Always emit event even if version_ids are the same
        # Products can share a version id but need distinct thumbnails
        # Cache invalidation in window.py ensures fresh data
        self._version_ids = version_ids
        self._version_selection_rows = list(selection_rows or ())
        self._controller.emit_event(
            "selection.versions.changed",
            {
                "project_name": self._project_name,
                "folder_ids": self._folder_ids,
                "version_ids": self._version_ids,
                "version_selection_rows": self._version_selection_rows,
            },
            self.event_source,
        )

    def get_selected_version_selection_rows(self):
        """Per-row selection detail including ``product_id`` for rep cache scope."""
        return list(self._version_selection_rows)

    def get_selected_representation_ids(self):
        return self._representation_ids

    def set_selected_representations(self, repre_ids):
        if repre_ids == self._representation_ids:
            return

        self._representation_ids = repre_ids
        self._controller.emit_event(
            "selection.representations.changed",
            {
                "project_name": self._project_name,
                "folder_ids": self._folder_ids,
                "version_ids": self._version_ids,
                "representation_ids": self._representation_ids,
            },
        )
