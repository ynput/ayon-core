"""Extensible slicer-level filter menu (e.g. "My Tasks").

This mirrors the tag-bar + checkbox-popup pattern already used for the
table's "Group By" menu (``AYFilterByCategory``) instead of stacking
individual checkboxes into the slicer panel. Its option list is driven
by :data:`SLICER_FILTER_OPTIONS`, and is rebuilt for the active
``BrowserSlicerCategory`` so a filter that only makes sense in one
slicer mode (e.g. "My Tasks" in Hierarchy) is simply absent from the
menu -- and the whole row hides itself -- in modes it does not apply
to.
"""

from __future__ import annotations

from ayon_core.ui.components.filter import AYFilterByCategory, FilterItem

from .browser_types import BrowserSlicerCategory, SLICER_FILTER_OPTIONS


class SlicerFiltersMenu(AYFilterByCategory):
    """Popup checklist of filters applicable to the active slicer mode."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent=parent, label="Filters", items=[])
        self.setVisible(False)

    def set_category(self, category: BrowserSlicerCategory) -> None:
        """Rebuild the option list for *category*.

        Options that do not apply to *category* are dropped -- and, if
        they were selected, silently deselected -- since a filter with
        no visible way to toggle it off should never keep limiting a
        mode the user has switched away from. The row is hidden
        entirely when no options apply.

        Args:
            category: The now-active slicer category.
        """
        selected_keys = set(self.get_selected_keys())
        items = [
            FilterItem(
                key=option.key,
                label=option.label,
                icon=option.icon,
                selected=option.key in selected_keys,
            )
            for option in SLICER_FILTER_OPTIONS
            if category in option.categories
        ]
        self.set_items(items)
        self.setVisible(bool(items))
