""""My Tasks" toggle button for the Browser slicer.

Sits to the right of the slicer's own search toggle. There is only
one slicer-level filter today, so this is a plain checkable icon
button rather than a dropdown menu: a menu with a single entry (and,
previously, a lot of dead space around it) was pure clutter. Checking
it scopes the Hierarchy tree -- and the task list under the selected
folder -- down to folders and tasks assigned to the current user;
unchecking it restores the full tree.

If a second slicer-level filter becomes a real, concrete need, this
is a reasonable place to grow a proper menu -- but building that
structure ahead of an actual second filter would just be speculative
complexity for a "extensibility" nothing exercises yet.
"""

from __future__ import annotations

from ayon_core.ui.components.buttons import AYButton

from .browser_types import BrowserSlicerCategory

_TOOLTIP = (
    "Only show folders that have a task assigned to you, so you can "
    "jump straight to your work."
)


class MyTasksToggleButton(AYButton):
    """Checkable icon button that toggles the "My Tasks" slicer filter.

    Checked state is native ``QAbstractButton`` state, so callers use
    the button's own ``toggled``/``isChecked``/``setChecked`` API
    directly rather than a bespoke signal or accessor.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(
            variant=AYButton.Variants.Nav,
            icon="assignment_ind",
            checkable=True,
            tooltip=_TOOLTIP,
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
