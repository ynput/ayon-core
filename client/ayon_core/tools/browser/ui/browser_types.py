"""Type definitions and enums for the review widget."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BrowserSlicerCategory(Enum):
    """Categories for organizing versions in the review widget."""

    HIERARCHY = "Hierarchy"
    REVIEWS = "Reviews"


# Key used by ``BrowserController.set_slicer_filters`` and
# ``BrowserTasksWidget.set_task_id_scope`` to identify the "My Tasks"
# slicer filter.
MY_TASKS_FILTER_KEY = "my_tasks"


@dataclass(frozen=True)
class SlicerFilterOption:
    """A single entry in the slicer's extensible filter menu.

    The slicer's filter menu (``SlicerFiltersMenu``) renders whatever
    options from :data:`SLICER_FILTER_OPTIONS` apply to the active
    ``BrowserSlicerCategory``. Adding a new slicer-scoped filter (e.g.
    a future "linked entities" filter) means appending an entry here
    and handling its key in ``BrowserController``, rather than
    stacking another checkbox widget into the panel.

    Attributes:
        key: Unique identifier, also used as the filter's storage key.
        label: Display text shown in the popup and as a tag.
        icon: Material Symbols icon name shown next to the label.
        categories: Slicer categories this filter is offered in.
        tooltip: Plain-language explanation shown on hover, so artists
            don't need to guess what checking the option will do.
    """

    key: str
    label: str
    icon: str
    categories: tuple[BrowserSlicerCategory, ...]
    tooltip: str = ""


SLICER_FILTER_OPTIONS: list[SlicerFilterOption] = [
    SlicerFilterOption(
        key=MY_TASKS_FILTER_KEY,
        label="My Tasks",
        icon="assignment_ind",
        categories=(BrowserSlicerCategory.HIERARCHY,),
        tooltip=(
            "Only show folders that have a task assigned to you, so "
            "you can jump straight to your work."
        ),
    ),
]
