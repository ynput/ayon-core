""""My Tasks" toggle button for the Browser slicer."""

from __future__ import annotations

from ayon_core.ui.components.buttons import AYButton

from .browser_types import BrowserSlicerCategory


class MyTasksToggleButton(AYButton):
    """Checkable icon button that toggles the "My Tasks" slicer filter."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            variant=AYButton.Variants.Nav,
            icon="assignment_ind",
            checkable=True,
            tooltip="Only show folders that have a task assigned to you.",
            parent=parent,
        )
        self.setVisible(False)

    def set_category(self, category: BrowserSlicerCategory) -> None:
        """Show the toggle only in Hierarchy mode.

        "My Tasks" scopes the folder tree, which only exists in
        Hierarchy mode -- there is nothing for it to filter in
        Reviews, so it is hidden -- and, if it was on, unchecked
        (via the normal ``toggled`` signal, so the filter it drives
        is actually cleared too) -- there.

        Args:
            category: The now-active slicer category.
        """
        applicable = category == BrowserSlicerCategory.HIERARCHY
        if not applicable and self.isChecked():
            self.setChecked(False)
        self.setVisible(applicable)
