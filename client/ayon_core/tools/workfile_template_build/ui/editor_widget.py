"""Editor of placeholder options with a live preview of the outcome."""

from __future__ import annotations

import copy
from typing import Any, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsWidget
from ayon_core.ui.components import (
    AYButton,
    AYComboBox,
    AYContainer,
    AYLabel,
    AYTreeView,
)
from ayon_core.ui.components.scroll_area import AYScrollArea

from ..abstract import (
    AbstractTemplateBuilderController,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from .placeholders_widget import (
    COLUMN_PADDING,
    CREATE_ICON,
    get_placeholder_icon,
)

# Delay between last change of an option and re-calculation of preview and
#   completions. Both may query the AYON server so they are not calculated
#   on every keystroke.
DYNAMIC_UPDATE_DELAY_MS = 400

# Maximum height of the preview entries view
MAX_PREVIEW_HEIGHT = 200

WARNING_COLOR = "#ffc671"

CREATE_MODE = "create"
EDIT_MODE = "edit"


class PreviewWidget(AYContainer):
    """Shows what a placeholder would do when the template is built."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=8,
            layout_spacing=6,
        )

        title_label = AYLabel("Preview", parent=self, bold=True)

        warning_label = AYLabel(
            parent=self,
            icon="warning",
            icon_color=WARNING_COLOR,
            icon_size=16,
        )
        hint_label = AYLabel(parent=self, dim=True)
        hint_label.setWordWrap(True)

        hint_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=6,
        )
        hint_widget.add_widget(warning_label)
        hint_widget.add_widget(hint_label, stretch=1)

        items_model = QtGui.QStandardItemModel()
        items_model.setColumnCount(2)

        items_view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        items_view.setModel(items_model)
        items_view.setHeaderHidden(True)
        items_view.setRootIsDecorated(False)
        items_view.setIndentation(0)
        items_view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        items_view.setFocusPolicy(QtCore.Qt.NoFocus)
        header = items_view.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)

        self.add_widget(title_label)
        self.add_widget(hint_widget)
        self.add_widget(items_view, stretch=1)

        self._title_label = title_label
        self._warning_label = warning_label
        self._hint_label = hint_label
        self._hint_widget = hint_widget
        self._items_model = items_model
        self._items_view = items_view

    def set_calculating(self) -> None:
        """Show that the preview is being re-calculated."""
        self._title_label.setText("Calculating preview...")
        self._set_hint(None, False)

    def set_preview(self, preview: Optional[PlaceholderPreview]) -> None:
        """Show result of a preview calculation.

        Args:
            preview (Optional[PlaceholderPreview]): Preview to show. Widget
                hides itself when None is passed.

        """
        if preview is None:
            self.setVisible(False)
            return

        self.setVisible(True)
        self._title_label.setText(preview.title or "Preview")
        self._set_hint(preview.hint, preview.is_error)

        root_item = self._items_model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        rows = [(item.label, item.detail or "") for item in preview.items]
        if preview.hidden_items_count:
            rows.append(
                ("... and {} more".format(preview.hidden_items_count), "")
            )

        for label, detail in rows:
            label_item = QtGui.QStandardItem(label)
            label_item.setToolTip(label)
            detail_item = QtGui.QStandardItem(detail)
            for item in (label_item, detail_item):
                item.setEditable(False)
            root_item.appendRow([label_item, detail_item])

        self._items_view.setVisible(bool(preview.items))
        # Column size hints are not reliable while the view is not shown
        #   and don't count with padding of the item delegate
        font_metrics = self._items_view.fontMetrics()
        detail_width = max(
            (font_metrics.horizontalAdvance(detail) for _, detail in rows),
            default=0,
        )
        self._items_view.header().resizeSection(
            1, detail_width + (2 * COLUMN_PADDING)
        )
        self._update_items_view_height()

    def _update_items_view_height(self) -> None:
        """Keep the preview only as tall as the entries it shows."""
        rows = self._items_model.rowCount()
        if not rows:
            return

        row_height = self._items_view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 24
        frame = 2 * self._items_view.frameWidth()
        self._items_view.setFixedHeight(
            min(rows * row_height + frame + 4, MAX_PREVIEW_HEIGHT)
        )

    def _set_hint(self, hint: Optional[str], is_error: bool) -> None:
        self._hint_label.setText(hint or "")
        self._warning_label.setVisible(bool(hint) and is_error)
        self._hint_widget.setVisible(bool(hint))


class PlaceholderEditorWidget(AYContainer):
    """Editor of placeholder options.

    Used both to create a new placeholder and to change an existing one.

    Signals:
        create_requested: Create placeholder of plugin identifier (str) with
            options (dict).
        save_requested: Save options (dict) to placeholder scene identifier
            (str).
        cancel_requested: Leave create mode without creating anything.

    """
    create_requested = QtCore.Signal(str, object)
    save_requested = QtCore.Signal(str, object)
    cancel_requested = QtCore.Signal()

    def __init__(
        self,
        controller: AbstractTemplateBuilderController,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=8,
        )

        self._controller = controller

        # --- Header ---
        title_label = AYLabel(
            parent=self,
            icon="extension",
            icon_size=24,
            rel_text_size=3,
            bold=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        subtitle_label = AYLabel(
            parent=self,
            dim=True,
            elide_mode=QtCore.Qt.ElideRight,
        )

        # --- Placeholder type (create mode only) ---
        type_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=8,
        )
        type_label = AYLabel("Placeholder type", parent=type_widget)
        type_combo = AYComboBox(type_widget)
        type_widget.add_widget(type_label)
        type_widget.add_widget(type_combo, stretch=1)

        # --- Options ---
        attrs_scroll = AYScrollArea(self)
        attrs_scroll.setWidgetResizable(True)

        attrs_wrapper = QtWidgets.QWidget(attrs_scroll)
        attrs_wrapper_layout = QtWidgets.QVBoxLayout(attrs_wrapper)
        attrs_wrapper_layout.setContentsMargins(0, 0, 6, 0)
        attrs_wrapper_layout.addStretch(1)
        attrs_scroll.setWidget(attrs_wrapper)

        # --- Preview ---
        preview_widget = PreviewWidget(self)

        # --- Footer ---
        btns_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        cancel_btn = AYButton(
            "Cancel",
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon="close",
        )
        confirm_btn = AYButton(
            "Create placeholder",
            parent=btns_widget,
            variant=AYButton.Variants.Filled,
            icon=CREATE_ICON,
        )
        btns_widget.addStretch(1)
        btns_widget.add_widget(cancel_btn)
        btns_widget.add_widget(confirm_btn)

        self.add_widget(title_label)
        self.add_widget(subtitle_label)
        self.add_widget(type_widget)
        self.add_widget(attrs_scroll, stretch=1)
        self.add_widget(preview_widget)
        self.add_widget(btns_widget)

        dynamic_timer = QtCore.QTimer(self)
        dynamic_timer.setInterval(DYNAMIC_UPDATE_DELAY_MS)
        dynamic_timer.setSingleShot(True)

        dynamic_timer.timeout.connect(self._on_dynamic_timer)
        type_combo.currentIndexChanged.connect(self._on_type_change)
        confirm_btn.clicked.connect(self._on_confirm_click)
        cancel_btn.clicked.connect(self._on_cancel_click)

        self._title_label = title_label
        self._subtitle_label = subtitle_label
        self._type_widget = type_widget
        self._type_combo = type_combo
        self._attrs_wrapper = attrs_wrapper
        self._attrs_wrapper_layout = attrs_wrapper_layout
        self._preview_widget = preview_widget
        self._confirm_btn = confirm_btn
        self._cancel_btn = cancel_btn
        self._dynamic_timer = dynamic_timer

        self._mode = CREATE_MODE
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._plugin_identifier: Optional[str] = None
        self._scene_identifier: Optional[str] = None
        self._attrs_widget: Optional[AttributeDefinitionsWidget] = None
        self._original_values: dict[str, Any] = {}
        self._last_dynamic_values: Optional[dict[str, Any]] = None

    # --- Public API ---------------------------------------------------
    def set_create_mode(
        self,
        plugin_items: list[PlaceholderPluginItem],
        plugin_identifier: Optional[str] = None,
    ) -> None:
        """Show options of a placeholder that is not created yet.

        Args:
            plugin_items (list[PlaceholderPluginItem]): Plugins that can be
                used to create a placeholder.
            plugin_identifier (Optional[str]): Plugin to pre-select.

        """
        self._mode = CREATE_MODE
        self._scene_identifier = None

        self._type_widget.setVisible(True)
        self._title_label.setText("New placeholder")
        self._subtitle_label.setText(
            "Fill in the options and create the placeholder in your scene."
        )
        self._confirm_btn.setText("Create placeholder")
        self._confirm_btn.set_icon(CREATE_ICON)
        self._cancel_btn.setText("Cancel")
        self._cancel_btn.set_icon("close")

        self._fill_plugin_items(plugin_items, plugin_identifier)

    def set_edit_mode(self, placeholder_item: PlaceholderItemInfo) -> None:
        """Show options of an existing placeholder.

        Args:
            placeholder_item (PlaceholderItemInfo): Placeholder to edit.

        """
        self._mode = EDIT_MODE
        self._scene_identifier = placeholder_item.scene_identifier

        self._type_widget.setVisible(False)
        self._title_label.setText(placeholder_item.label)
        self._subtitle_label.setText("{} - {}".format(
            placeholder_item.plugin_label,
            placeholder_item.scene_identifier,
        ))
        self._confirm_btn.setText("Save changes")
        self._confirm_btn.set_icon("save")
        self._cancel_btn.setText("Revert")
        self._cancel_btn.set_icon("undo")

        self._set_header_icon(placeholder_item.icon)
        self._set_plugin(
            placeholder_item.plugin_identifier,
            copy.deepcopy(placeholder_item.data),
        )

    def has_unsaved_changes(self) -> bool:
        """Options were changed since they were last stored.

        Returns:
            bool: There are changes that would be lost.

        """
        if self._mode != EDIT_MODE or self._attrs_widget is None:
            return False
        return self._attrs_widget.current_value() != self._original_values

    def get_scene_identifier(self) -> Optional[str]:
        """Scene identifier of the edited placeholder.

        Returns:
            Optional[str]: Scene identifier, None in create mode.

        """
        return self._scene_identifier

    # --- Implementation -----------------------------------------------
    def _fill_plugin_items(
        self,
        plugin_items: list[PlaceholderPluginItem],
        plugin_identifier: Optional[str],
    ) -> None:
        self._plugin_items = list(plugin_items)

        index = 0
        self._type_combo.blockSignals(True)
        self._type_combo.model().clear()
        for row, plugin_item in enumerate(self._plugin_items):
            self._type_combo.add_item({"text": plugin_item.label})
            # Plugin icons can be of any icon definition type, so they are
            #   set as icons instead of material symbol names
            icon = get_placeholder_icon(plugin_item.icon)
            if icon is not None:
                self._type_combo.setItemIcon(row, icon)
            if plugin_item.identifier == plugin_identifier:
                index = row
        self._type_combo.setCurrentIndex(index)
        self._type_combo.blockSignals(False)

        self._set_plugin_by_index(index)

    def _set_plugin_by_index(self, index: int) -> None:
        plugin_item = None
        if 0 <= index < len(self._plugin_items):
            plugin_item = self._plugin_items[index]

        if plugin_item is None:
            self._set_header_icon(None)
            self._set_plugin(None, None)
            return

        self._set_header_icon(plugin_item.icon)
        self._set_plugin(plugin_item.identifier, None)

    def _set_header_icon(self, icon_def: Optional[dict[str, Any]]) -> None:
        icon = get_placeholder_icon(icon_def)
        if icon is not None:
            self._title_label.set_icon(icon)

    def _set_plugin(
        self,
        plugin_identifier: Optional[str],
        placeholder_data: Optional[dict[str, Any]],
    ) -> None:
        """Build option widgets for a plugin.

        Args:
            plugin_identifier (Optional[str]): Plugin to show options of.
            placeholder_data (Optional[dict[str, Any]]): Values to fill in.

        """
        self._plugin_identifier = plugin_identifier
        self._remove_attrs_widget()

        self._preview_widget.set_preview(None)
        self._last_dynamic_values = None
        self._dynamic_timer.stop()

        if plugin_identifier is None:
            self._confirm_btn.setEnabled(False)
            return

        attr_defs = self._controller.get_placeholder_options(
            plugin_identifier, placeholder_data
        )
        attrs_widget = AttributeDefinitionsWidget(
            attr_defs, self._attrs_wrapper
        )
        if placeholder_data:
            attrs_widget.set_value(placeholder_data)
        attrs_widget.value_changed.connect(self._on_value_change)

        # Keep the stretch at the end of the layout
        self._attrs_wrapper_layout.insertWidget(0, attrs_widget, 0)

        self._attrs_widget = attrs_widget
        self._original_values = attrs_widget.current_value()

        self._update_confirm_state()
        self._request_dynamic_update()

    def _remove_attrs_widget(self) -> None:
        if self._attrs_widget is None:
            return
        self._attrs_wrapper_layout.removeWidget(self._attrs_widget)
        self._attrs_widget.setVisible(False)
        self._attrs_widget.deleteLater()
        self._attrs_widget = None
        self._original_values = {}

    def _update_confirm_state(self) -> None:
        if self._mode == CREATE_MODE:
            self._confirm_btn.setEnabled(self._attrs_widget is not None)
            self._cancel_btn.setEnabled(True)
            return

        has_changes = self.has_unsaved_changes()
        self._confirm_btn.setEnabled(has_changes)
        self._cancel_btn.setEnabled(has_changes)

    def _request_dynamic_update(self) -> None:
        self._dynamic_timer.start()

    def _on_value_change(self, value=None, attr_id=None) -> None:
        self._update_confirm_state()
        self._request_dynamic_update()

    def _on_dynamic_timer(self) -> None:
        if self._attrs_widget is None or self._plugin_identifier is None:
            return

        values = self._attrs_widget.current_value()
        if values == self._last_dynamic_values:
            return
        self._last_dynamic_values = copy.deepcopy(values)

        self._preview_widget.set_calculating()
        completions = self._controller.get_placeholder_completions(
            self._plugin_identifier, values
        )
        if completions and self._attrs_widget is not None:
            self._attrs_widget.set_completions(completions)

        preview = self._controller.get_placeholder_preview(
            self._plugin_identifier, values
        )
        self._preview_widget.set_preview(preview)

    def _on_type_change(self) -> None:
        self._set_plugin_by_index(self._type_combo.currentIndex())

    def _on_confirm_click(self) -> None:
        if self._attrs_widget is None or self._plugin_identifier is None:
            return

        values = self._attrs_widget.current_value()
        if self._mode == CREATE_MODE:
            self.create_requested.emit(self._plugin_identifier, values)
        elif self._scene_identifier is not None:
            self.save_requested.emit(self._scene_identifier, values)

    def _on_cancel_click(self) -> None:
        if self._mode == CREATE_MODE:
            self.cancel_requested.emit()
            return

        if self._attrs_widget is not None:
            self._attrs_widget.set_value(copy.deepcopy(self._original_values))
            self._update_confirm_state()


class PlaceholderHintWidget(AYContainer):
    """Friendly explanation shown when nothing is being edited.

    Signals:
        create_requested: User wants to create a placeholder.

    """
    create_requested = QtCore.Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=0,
        )

        icon_label = AYLabel(parent=self, icon="info", icon_size=96)
        icon_label.setAlignment(QtCore.Qt.AlignCenter)

        title_label = AYLabel(parent=self, rel_text_size=6)
        title_label.setAlignment(QtCore.Qt.AlignCenter)

        message_label = AYLabel(parent=self, dim=True)
        message_label.setAlignment(QtCore.Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setMaximumWidth(460)

        create_btn = AYButton(
            "Add placeholder",
            parent=self,
            variant=AYButton.Variants.Filled,
            icon=CREATE_ICON,
        )

        layout = self.layout()
        layout.addStretch(2)
        layout.addWidget(icon_label, 0, QtCore.Qt.AlignHCenter)
        layout.addSpacing(12)
        layout.addWidget(title_label, 0, QtCore.Qt.AlignHCenter)
        layout.addSpacing(4)
        layout.addLayout(self._centered(message_label, stretch=4), 0)
        layout.addSpacing(16)
        layout.addWidget(create_btn, 0, QtCore.Qt.AlignHCenter)
        layout.addStretch(3)

        create_btn.clicked.connect(self.create_requested)

        self._title_label = title_label
        self._message_label = message_label
        self._create_btn = create_btn

    @staticmethod
    def _centered(
        widget: QtWidgets.QWidget, stretch: int
    ) -> QtWidgets.QHBoxLayout:
        """Keep a word wrapped widget centered with a share of the width."""
        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        layout.addWidget(widget, stretch)
        layout.addStretch(1)
        return layout

    def set_message(
        self, title: str, message: str, create_enabled: bool = True
    ) -> None:
        """Change shown text.

        Args:
            title (str): Heading of the message.
            message (str): Explanation shown under the heading.
            create_enabled (bool): Show the "Add placeholder" button.

        """
        self._title_label.setText(title)
        self._message_label.setText(message)
        self._create_btn.setVisible(create_enabled)
