"""Compact icon-button filter menu for the Browser slicer.

Sits to the right of the slicer's own search toggle rather than as a
visible chip/tag bar: active filters are communicated through the
button's highlighted color and its tooltip, not through stacked
checkboxes or badges in the panel. Offered options are rebuilt for the
active ``BrowserSlicerCategory`` from :data:`SLICER_FILTER_OPTIONS`, so
a filter that only applies to one slicer mode (e.g. "My Tasks" in
Hierarchy) is simply not offered -- and the button hides entirely --
in modes it doesn't apply to.

Built on ``AYButtonMenu`` + ``FilterableList`` -- the same primitives
already used for the Browser toolbar's "Group By" menu -- rather than
``AYFilterByCategory``, since that widget's tag bar has no place to
live once there is no filter row, and its default checkbox popup
carries a heavier border than the rest of the app's dropdowns.
"""

from __future__ import annotations

from qtpy import QtCore

from ayon_core.ui.components.buttons import AYButton, AYButtonMenu
from ayon_core.ui.components.filterable_list import FilterableList

from .browser_types import BrowserSlicerCategory, SLICER_FILTER_OPTIONS


class SlicerFiltersMenu(AYButtonMenu):
    """Icon-button dropdown for the extensible slicer filter set.

    Signals:
        filter_changed: Emitted with the sorted list of selected
            filter keys whenever the user toggles an option.
    """

    filter_changed = QtCore.Signal(list)

    def __init__(self, parent=None) -> None:
        self._category = BrowserSlicerCategory.HIERARCHY
        self._selected: set[str] = set()
        self._option_buttons: dict[str, AYButton] = {}
        self._list: FilterableList | None = None
        super().__init__(
            icon="filter_alt",
            variant=AYButton.Variants.Nav,
            tooltip="Filters",
            populate_callback=self._populate,
            parent=parent,
        )
        self.setVisible(False)

    def _populate(self, container) -> None:
        """Build the (initially empty) popup content once at construction.

        Args:
            container: The ``ButtonMenuDropdown`` page passed in by
                ``AYButtonMenu``; rows are added to its layout, then
                rebuilt in place by :meth:`set_category`.
        """
        self._list = FilterableList(placeholder="Search")
        container.layout().addWidget(self._list)

    def set_category(self, category: BrowserSlicerCategory) -> None:
        """Rebuild the option list for *category*.

        Options that do not apply to *category* are dropped -- and, if
        they were selected, silently deselected -- since a filter with
        no visible way to toggle it off should never keep limiting a
        mode the user has switched away from. The button hides
        entirely when no options apply.

        Args:
            category: The now-active slicer category.
        """
        self._category = category
        options = [
            option
            for option in SLICER_FILTER_OPTIONS
            if category in option.categories
        ]
        self._selected &= {option.key for option in options}

        assert self._list is not None
        self._list.clear_items()
        self._option_buttons = {}
        for option in options:
            btn = AYButton(
                option.label,
                icon=option.icon,
                variant=AYButton.Variants.Text,
                checkable=True,
                label_alignment=QtCore.Qt.AlignmentFlag.AlignLeft,
                fixed_width=False,
            )
            btn.setChecked(option.key in self._selected)
            btn.toggled.connect(
                lambda checked, key=option.key: self._on_option_toggled(
                    key, checked
                )
            )
            self._option_buttons[option.key] = btn
            self._list.add_item(
                btn,
                match_fn=lambda text, label=option.label: (
                    not text.lower().strip()
                    or text.lower().strip() in label.lower()
                ),
            )

        self.setVisible(bool(options))
        self._refresh_state()

    def _on_option_toggled(self, key: str, checked: bool) -> None:
        if checked:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self._refresh_state()
        self.filter_changed.emit(sorted(self._selected))

    def _refresh_state(self) -> None:
        """Sync the trigger button's highlight color and tooltip."""
        active = bool(self._selected)
        self.set_variant(
            AYButton.Variants.Checked if active else AYButton.Variants.Nav
        )
        if active:
            labels = [
                option.label
                for option in SLICER_FILTER_OPTIONS
                if option.key in self._selected
            ]
            self.setToolTip("Active filters: " + ", ".join(labels))
        else:
            self.setToolTip("Filters")

    def get_selected_keys(self) -> list[str]:
        """Return the currently selected filter keys, sorted."""
        return sorted(self._selected)

    def set_selected_keys(self, keys) -> None:
        """Sync selection from an external source (e.g. an applied view).

        Keys that don't apply to the active category are dropped
        silently, same as an explicit category switch. Does not
        re-emit ``filter_changed`` -- callers driving this externally
        already have the authoritative value.

        Args:
            keys: Filter keys that should be selected.
        """
        applicable = {
            option.key
            for option in SLICER_FILTER_OPTIONS
            if self._category in option.categories
        }
        new_selected = set(keys) & applicable
        if new_selected == self._selected:
            return
        self._selected = new_selected
        for key, btn in self._option_buttons.items():
            checked = key in self._selected
            if btn.isChecked() != checked:
                btn.blockSignals(True)
                btn.setChecked(checked)
                btn.blockSignals(False)
        self._refresh_state()
