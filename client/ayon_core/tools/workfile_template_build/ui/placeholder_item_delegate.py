"""Item delegate of the placeholder list."""

from __future__ import annotations

from ayon_core.ui.components.tree_view import TreeViewItemDelegate

# Horizontal padding inside of a cell, matches the padding of the header
#   labels so the values line up with their column titles.
CELL_PADDING = 8
COLUMN_PADDING = 2 * CELL_PADDING


class _PaddedItemDelegate(TreeViewItemDelegate):
    """Item delegate with more space between a cell edge and its text.

    The AYON tree view style keeps the text 2px from the cell edge, which
    squeezes short values, like the order, against the edge of the list.
    """

    def _tv_styles(self) -> dict[str, dict]:
        if self._styles_cache is None:
            styles = super()._tv_styles()
            base_style = dict(styles.get("base", {}))
            vertical_padding = base_style.get("item-padding", [1, 2])[0]
            base_style["item-padding"] = [vertical_padding, CELL_PADDING]
            self._styles_cache = dict(styles, base=base_style)
        return self._styles_cache
