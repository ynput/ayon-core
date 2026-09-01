"""Single source of truth for Browser Working View defaults."""

from __future__ import annotations

from dataclasses import dataclass

from ayon_core.ui.components.views.data_models import (
    ColumnState,
    FilterDef,
    GroupingDef,
    ViewSettings,
)


@dataclass(frozen=True)
class BrowserViewDefaults:
    """Default state applied by the Browser Working View."""

    visible_column_keys: frozenset[str]
    sort_by: str
    sort_desc: bool
    row_height: int
    group_by_key: str
    group_sort_desc: bool
    show_empty_groups: bool
    card_width: int
    display_type: str
    featured_version_order: tuple[str, ...]
    latest_per_folder: bool
    include_children: bool

    def create_settings(self, column_keys: list[str]) -> ViewSettings:
        """Create independent view settings for the available columns."""
        return ViewSettings(
            columns=[
                ColumnState(
                    name=key,
                    visible=key in self.visible_column_keys,
                )
                for key in column_keys
            ],
            sort_by=self.sort_by,
            sort_desc=self.sort_desc,
            row_height=self.row_height,
            grouping=GroupingDef(
                group_by=(
                    None
                    if self.group_by_key == "none"
                    else self.group_by_key
                ),
                group_sort_desc=self.group_sort_desc,
                show_empty_groups=self.show_empty_groups,
            ),
            filter=FilterDef(
                conditions=[
                    {
                        "key": "version",
                        "label": "Version",
                        "values": ["Latest"],
                        "useSubstring": False,
                    }
                ]
            ),
            extra={
                "gridHeight": self.card_width,
                "displayType": self.display_type,
                "featuredVersionOrder": list(
                    self.featured_version_order
                ),
                "latestPerFolder": self.latest_per_folder,
                "includeChildren": self.include_children,
            },
        )


BROWSER_VIEW_DEFAULTS = BrowserViewDefaults(
    visible_column_keys=frozenset({
        "thumb",
        "product/version",
        "productType",
        "version",
        "status",
        "createdAt",
        "author",
        "frameStart",
        "frameEnd",
        "handleStart",
        "handleEnd",
        "step",
    }),
    sort_by="product/version",
    sort_desc=False,
    row_height=34,
    group_by_key="none",
    group_sort_desc=False,
    show_empty_groups=False,
    card_width=200,
    display_type="table",
    featured_version_order=("latestDone", "latest", "hero"),
    latest_per_folder=False,
    include_children=False,
)
