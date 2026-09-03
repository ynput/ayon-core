"""Compact icon-button filter menu for the Browser slicer.

Sits to the right of the slicer's own search toggle rather than as a
visible chip/tag bar: active filters are communicated through the
button's highlighted color and its tooltip, not through stacked
checkboxes or badges in the panel. Offered options are rebuilt for the
active ``BrowserSlicerCategory`` from :data:`SLICER_FILTER_OPTIONS`, so
a filter that only applies to one slicer mode (e.g. "My Tasks" in
Hierarchy) is simply not offered -- and the button hides entirely --
in modes it doesn't apply to.

Built on ``AYButtonMenu`` with plain ``AYCheckBox`` rows -- the same
recipe the toolbar's "Customize" menu uses -- rather than a searchable
list: with only a handful of options there is no need to search, and
a flat checkbox menu avoids both the scroll area's leftover
whitespace and ``AYFilterByCategory``'s heavier popup border.
"""

from __future__ import annotations

from qtpy import QtCore, QtWidgets

from ayon_core.ui.components.buttons import AYButton, AYButtonMenu
from ayon_core.ui.components.check_box import AYCheckBox
from ayon_core.ui.components.layouts import AYVBoxLayout

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
        self._option_checkboxes: dict[str, AYCheckBox] = {}
        self._layout: AYVBoxLayout | None = None
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
                ``AYButtonMenu``; checkbox rows are added directly to
                its layout, then rebuilt in place by
                :meth:`set_category`.
        """
        layout = container.layout()
        assert isinstance(layout, AYVBoxLayout)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(4)
        self._layout = layout

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

        assert self._layout is not None
        for checkbox in self._option_checkboxes.values():
            self._layout.removeWidget(checkbox)
            checkbox.deleteLater()
        self._option_checkboxes = {}
        for option in options:
            checkbox = AYCheckBox(
                option.label,
                checked=option.key in self._selected,
                variant=AYCheckBox.Variants.Menu,
                parent=self,
            )
            if option.tooltip:
                checkbox.setToolTip(option.tooltip)
            checkbox.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            checkbox.toggled.connect(
                lambda checked, key=option.key: self._on_option_toggled(
                    key, checked
                )
            )
            self._option_checkboxes[option.key] = checkbox
            self._layout.addWidget(checkbox, stretch=0)

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
        for key, checkbox in self._option_checkboxes.items():
            checked = key in self._selected
            if checkbox.isChecked() != checked:
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
        self._refresh_state()
