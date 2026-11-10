from __future__ import annotations

from typing import Any, Optional

from ayon_core.tools.common_models import HierarchyExpectedSelection


class LauncherExpectedSelection(HierarchyExpectedSelection):
    """Selection the launcher UI is asked to navigate to.

    The backend never changes the selection on its own - widgets do, and
    report it through the 'set_selected_*' methods of the controller. To
    navigate somewhere (e.g. from a recent action) the backend only states
    what should end up selected, and the widgets select it as soon as
    their data is loaded, confirming each step.

    Extends the shared hierarchy model with the workfile that should be
    selected once the task is.
    """

    def __init__(self, controller) -> None:
        super().__init__(
            controller,
            handle_project=True,
            handle_folder=True,
            handle_task=True,
        )
        self._workfile_id: Optional[str] = None
        self._workfile_selected: bool = True

    def set_expected_selection(
        self,
        project_name: Optional[str] = None,
        folder_id: Optional[str] = None,
        task_name: Optional[str] = None,
        workfile_id: Optional[str] = None,
    ) -> None:
        self._workfile_id = workfile_id
        self._workfile_selected = False
        super().set_expected_selection(project_name, folder_id, task_name)

    def get_expected_selection_data(self) -> dict[str, dict[str, Any]]:
        data = super().get_expected_selection_data()
        project_folder_task_selected = (
            self._project_selected
            and self._folder_selected
            and self._task_selected
        )
        data["workfile"] = {
            "id": self._workfile_id,
            "current": (
                project_folder_task_selected and not self._workfile_selected
            ),
            "selected": self._workfile_selected,
        }
        return data

    def expected_workfile_selected(self, workfile_id: Optional[str]) -> bool:
        """UI selected requested workfile, or found there is none to select.

        Args:
            workfile_id (Optional[str]): Workfile id.

        """
        if workfile_id != self._workfile_id:
            return False
        self._workfile_selected = True
        self._emit_change()
        return True
